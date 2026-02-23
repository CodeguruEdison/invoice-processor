from fastapi import UploadFile, HTTPException
from app.repositories.invoice_repository_interface import IInvoiceRepository
from app.repositories.whitelist_repository_interface import IWhitelistRepository
from app.services.docling_service import DoclingService
from app.models.invoice import Invoice, ProcessingStatus
from app.core.config import settings
from app.core.file_validation import content_matches_extension
from app.schemas.invoice import (
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceTaxExemptUpdate,
)
from app.ml.pipeline import process_invoice
from app.ml.state import PipelineStatus
import asyncio
import uuid
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _delete_file_sync(file_path: str) -> None:
    """Remove file from disk. Safe if missing (e.g. already deleted)."""
    Path(file_path).unlink(missing_ok=True)


class InvoiceService:
    """
    WHY WE INJECT TWO REPOSITORIES:
    The service needs both invoice data and whitelist data.
    By injecting both we keep the service layer clean
    and testable — we can mock both repositories in tests.

    DoclingService is injected for OCR; when OCR_USE_DOCLING is True
    the pipeline uses Docling for document text extraction.
    """

    def __init__(
        self,
        invoice_repository: IInvoiceRepository,
        whitelist_repository: IWhitelistRepository,
        docling_service: DoclingService,
    ) -> None:
        self.invoice_repository = invoice_repository
        self.whitelist_repository = whitelist_repository
        self.docling_service = docling_service

    async def upload_and_process_invoice(
        self,
        file: UploadFile,
    ) -> InvoiceResponse:
        """
        WHY THIS IS A SINGLE METHOD:
        Upload + process is an atomic operation from the
        business perspective. The user uploads a file and
        expects it to be processed immediately — not two
        separate API calls.
        """

        # ── Validation ────────────────────────────────────
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No filename provided",
            )

        ext: str = file.filename.split(".")[-1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '.{ext}' not allowed. "
                f"Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        contents: bytes = await file.read()
        size_mb: float = len(contents) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {size_mb:.1f}MB. "
                f"Max: {settings.MAX_UPLOAD_SIZE_MB}MB",
            )

        if len(contents) == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty",
            )

        if not content_matches_extension(contents, ext):
            raise HTTPException(
                status_code=400,
                detail="File content does not match extension. "
                "The file may be corrupted or mislabeled.",
            )

        # ── Save File ─────────────────────────────────────
        unique_filename: str = f"{uuid.uuid4()}_{file.filename}"
        file_path = settings.UPLOAD_DIR / unique_filename

        def _write_file() -> None:
            with open(file_path, "wb") as f:
                f.write(contents)

        await asyncio.to_thread(_write_file)

        # ── Save to DB (PENDING) ──────────────────────────
        # WHY WE SAVE BEFORE PROCESSING:
        # If processing takes 30 seconds and crashes halfway,
        # we still have a record of the uploaded file.
        # The user can retry or we can process it later.
        invoice = Invoice(
            filename=unique_filename,
            file_path=str(file_path),
            size_mb=round(size_mb, 2),
            status=ProcessingStatus.PENDING,
        )
        invoice = await self.invoice_repository.create(invoice)
        logger.info(f"Invoice saved to DB: {invoice.id}")

        # ── Load Whitelist ────────────────────────────────
        # WHY LOAD HERE NOT IN NODE:
        # Nodes should be pure functions with no DB access.
        # Service layer handles all DB operations.
        whitelisted = await self.whitelist_repository.get_all_active()
        whitelisted_names = [v.vendor_name.lower() for v in whitelisted]
        logger.info(f"Loaded {len(whitelisted_names)} whitelisted vendors")

        # ── Run Pipeline ──────────────────────────────────
        # Run in thread pool so the event loop is not blocked by sync OCR/LLM.
        try:
            result = await asyncio.to_thread(
                process_invoice,
                file_path=str(file_path),
                whitelisted_vendors=whitelisted_names,
                is_tax_exempt=invoice.is_tax_exempt,
                tax_exempt_reason=invoice.tax_exempt_reason,
                docling_service=self.docling_service,
            )
            logger.info(
                f"Pipeline completed for {invoice.id}: "
                f"{result['status']}"
            )

        except Exception as e:
            # ── Pipeline Failed ───────────────────────────
            # WHY WE CATCH HERE:
            # If the pipeline crashes we still want to
            # update the DB status so the user knows
            # what happened to their invoice.
            logger.error(f"Pipeline failed for {invoice.id}: {e}", exc_info=True)
            invoice.status = ProcessingStatus.FAILED
            invoice.validation_errors = [f"Pipeline error: {str(e)}"]
            await self.invoice_repository.update(invoice)
            detail = (
                str(e)
                if settings.DEBUG
                else "Invoice processing failed. Please try again or contact support."
            )
            raise HTTPException(status_code=500, detail=detail)

        # ── Update DB with Results ────────────────────────
        # WHY WE MAP PIPELINE STATUS TO DB STATUS:
        # PipelineStatus and ProcessingStatus are slightly
        # different enums. Pipeline has more granular states
        # but DB only needs the final business status.
        invoice.vendor_name = result.get("vendor_name")
        invoice.invoice_number = result.get("invoice_number")
        invoice.invoice_date = result.get("invoice_date")
        invoice.subtotal = result.get("subtotal")
        invoice.tax_amount = result.get("tax_amount")
        invoice.total_amount = result.get("total_amount")
        # Coerce None to 0.0 so DB NOT NULL is satisfied when LLM returns null
        confidence = result.get("confidence_score")
        invoice.confidence_score = confidence if confidence is not None else 0.0
        invoice.retry_count = result.get("retry_count", 0)

        # Store as JSON (lists for API response compatibility)
        invoice.line_items = result.get("line_items", [])
        invoice.validation_errors = result.get("validation_errors", [])
        invoice.anomaly_flags = result.get("anomaly_flags", [])

        # Map pipeline status to DB status
        status_map = {
            PipelineStatus.COMPLETED: ProcessingStatus.COMPLETED,
            PipelineStatus.ANOMALY_FLAGGED: ProcessingStatus.ANOMALY_FLAGGED,
            PipelineStatus.FAILED: ProcessingStatus.FAILED,
        }
        invoice.status = status_map.get(
            result["status"],
            ProcessingStatus.FAILED,
        )

        invoice = await self.invoice_repository.update(invoice)
        logger.info(f"Invoice {invoice.id} updated with results")

        return InvoiceResponse.model_validate(invoice)

    async def reprocess_invoice(self, invoice_id: str) -> InvoiceResponse:
        """
        Re-run the pipeline for an existing invoice (e.g. after whitelist or prompt change).
        File at invoice.file_path must still exist.
        """
        invoice = await self.invoice_repository.get_by_id(invoice_id)
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        if not Path(invoice.file_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Invoice file no longer exists on disk; cannot reprocess",
            )
        whitelisted = await self.whitelist_repository.get_all_active()
        whitelisted_names = [v.vendor_name.lower() for v in whitelisted]
        try:
            result = await asyncio.to_thread(
                process_invoice,
                file_path=invoice.file_path,
                whitelisted_vendors=whitelisted_names,
                is_tax_exempt=invoice.is_tax_exempt,
                tax_exempt_reason=invoice.tax_exempt_reason,
                docling_service=self.docling_service,
            )
        except Exception as e:
            logger.error(f"Reprocess failed for {invoice.id}: {e}", exc_info=True)
            invoice.status = ProcessingStatus.FAILED
            invoice.validation_errors = [f"Pipeline error: {str(e)}"]
            await self.invoice_repository.update(invoice)
            detail = (
                str(e)
                if settings.DEBUG
                else "Invoice processing failed. Please try again or contact support."
            )
            raise HTTPException(status_code=500, detail=detail)
        invoice.vendor_name = result.get("vendor_name")
        invoice.invoice_number = result.get("invoice_number")
        invoice.invoice_date = result.get("invoice_date")
        invoice.subtotal = result.get("subtotal")
        invoice.tax_amount = result.get("tax_amount")
        invoice.total_amount = result.get("total_amount")
        confidence = result.get("confidence_score")
        invoice.confidence_score = confidence if confidence is not None else 0.0
        invoice.retry_count = result.get("retry_count", 0)
        invoice.line_items = result.get("line_items", [])
        invoice.validation_errors = result.get("validation_errors", [])
        invoice.anomaly_flags = result.get("anomaly_flags", [])
        status_map = {
            PipelineStatus.COMPLETED: ProcessingStatus.COMPLETED,
            PipelineStatus.ANOMALY_FLAGGED: ProcessingStatus.ANOMALY_FLAGGED,
            PipelineStatus.FAILED: ProcessingStatus.FAILED,
        }
        invoice.status = status_map.get(result["status"], ProcessingStatus.FAILED)
        invoice = await self.invoice_repository.update(invoice)
        logger.info(f"Invoice {invoice.id} reprocessed")
        return InvoiceResponse.model_validate(invoice)

    async def get_all_invoices(
        self,
        skip: int = 0,
        limit: int = 50,
        status: ProcessingStatus | None = None,
        vendor_name: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
    ) -> InvoiceListResponse:
        invoices, total = await self.invoice_repository.get_paginated(
            skip=skip,
            limit=min(limit, 100),
            status=status,
            vendor_name_contains=vendor_name,
            created_after=created_after,
            created_before=created_before,
        )
        return InvoiceListResponse(
            total=total,
            invoices=[InvoiceResponse.model_validate(inv) for inv in invoices],
        )

    async def get_invoice_by_id(self, invoice_id: str) -> InvoiceResponse:
        invoice = await self.invoice_repository.get_by_id(invoice_id)
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        return InvoiceResponse.model_validate(invoice)

    async def update_tax_exemption(
        self,
        invoice_id: str,
        data: InvoiceTaxExemptUpdate,
    ) -> InvoiceResponse:
        """
        WHY A SEPARATE ENDPOINT FOR THIS:
        Tax exemption status might need to be updated
        after initial processing. For instance, accounting
        discovers the vendor is actually tax-exempt and
        needs to update the record without re-processing
        the entire invoice.
        """
        invoice = await self.invoice_repository.get_by_id(invoice_id)
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )

        invoice.is_tax_exempt = data.is_tax_exempt
        invoice.tax_exempt_reason = data.tax_exempt_reason
        invoice = await self.invoice_repository.update(invoice)

        logger.info(
            f"Updated tax exemption for {invoice_id}: "
            f"{data.is_tax_exempt}"
        )

        return InvoiceResponse.model_validate(invoice)

    async def delete_invoice(self, invoice_id: str) -> dict[str, str]:
        invoice = await self.invoice_repository.get_by_id(invoice_id)
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        file_path = invoice.file_path
        await asyncio.to_thread(_delete_file_sync, file_path)
        deleted = await self.invoice_repository.delete(invoice_id)
        assert deleted, "Invoice should exist after get_by_id"
        return {"message": f"Invoice {invoice_id} deleted successfully"}