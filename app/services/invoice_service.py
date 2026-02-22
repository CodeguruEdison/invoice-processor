from fastapi import UploadFile, HTTPException
from app.repositories.invoice_repository_interface import IInvoiceRepository
from app.repositories.whitelist_repository_interface import IWhitelistRepository
from app.models.invoice import Invoice, ProcessingStatus
from app.core.config import settings
from app.schemas.invoice import (
    InvoiceUploadResponse,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceTaxExemptUpdate,
)
from app.ml.pipeline import process_invoice
from app.ml.state import PipelineStatus
import uuid
import logging

logger = logging.getLogger(__name__)


class InvoiceService:
    """
    WHY WE INJECT TWO REPOSITORIES:
    The service needs both invoice data and whitelist data.
    By injecting both we keep the service layer clean
    and testable — we can mock both repositories in tests.
    """

    def __init__(
        self,
        invoice_repository: IInvoiceRepository,
        whitelist_repository: IWhitelistRepository,
    ) -> None:
        self.invoice_repository = invoice_repository
        self.whitelist_repository = whitelist_repository

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

        # ── Save File ─────────────────────────────────────
        unique_filename: str = f"{uuid.uuid4()}_{file.filename}"
        file_path = settings.UPLOAD_DIR / unique_filename
        with open(file_path, "wb") as f:
            f.write(contents)

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
        try:
            result = process_invoice(
                file_path=str(file_path),
                whitelisted_vendors=whitelisted_names,
                is_tax_exempt=invoice.is_tax_exempt,
                tax_exempt_reason=invoice.tax_exempt_reason,
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
            logger.error(f"Pipeline failed for {invoice.id}: {e}")
            invoice.status = ProcessingStatus.FAILED
            invoice.validation_errors = [f"Pipeline error: {str(e)}"]
            await self.invoice_repository.update(invoice)
            raise HTTPException(
                status_code=500,
                detail=f"Invoice processing failed: {str(e)}",
            )

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
        invoice.confidence_score = result.get("confidence_score", 0.0)
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

    async def get_all_invoices(self) -> InvoiceListResponse:
        invoices = await self.invoice_repository.get_all()
        return InvoiceListResponse(
            total=len(invoices),
            invoices=[
                InvoiceResponse.model_validate(inv) for inv in invoices
            ],
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
        deleted = await self.invoice_repository.delete(invoice_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        return {"message": f"Invoice {invoice_id} deleted successfully"}