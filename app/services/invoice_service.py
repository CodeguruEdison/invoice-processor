from fastapi import UploadFile, HTTPException
from app.repositories.invoice_repository_interface import IInvoiceRepository
from app.models.invoice import Invoice, ProcessingStatus
from app.core.config import settings
from app.schemas.invoice import (
    InvoiceUploadResponse,
    InvoiceListResponse,
    InvoiceResponse,
)
import uuid
import logging

logger = logging.getLogger(__name__)


class InvoiceService:

    def __init__(self, repository: IInvoiceRepository) -> None:
        self.repository = repository

    async def upload_invoice(self, file: UploadFile) -> InvoiceUploadResponse:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No filename provided",
            )

        ext: str = file.filename.split(".")[-1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '.{ext}' not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        contents: bytes = await file.read()
        size_mb: float = len(contents) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {size_mb:.1f}MB. Max: {settings.MAX_UPLOAD_SIZE_MB}MB",
            )

        unique_filename: str = f"{uuid.uuid4()}_{file.filename}"
        file_path = settings.UPLOAD_DIR / unique_filename
        with open(file_path, "wb") as f:
            f.write(contents)

        invoice = Invoice(
            filename=unique_filename,
            file_path=str(file_path),
            size_mb=round(size_mb, 2),
            status=ProcessingStatus.PENDING,
        )
        saved_invoice = await self.repository.create(invoice)
        logger.info(f"Invoice uploaded: {saved_invoice.id}")

        return InvoiceUploadResponse(
            message="Invoice uploaded successfully",
            filename=saved_invoice.filename,
            file_path=saved_invoice.file_path,
            size_mb=saved_invoice.size_mb,
            status=saved_invoice.status,
        )

    async def get_all_invoices(self) -> InvoiceListResponse:
        invoices = await self.repository.get_all()
        return InvoiceListResponse(
            total=len(invoices),
            invoices=[InvoiceResponse.model_validate(inv) for inv in invoices],
        )

    async def get_invoice_by_id(self, invoice_id: str) -> InvoiceResponse:
        invoice = await self.repository.get_by_id(invoice_id)
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        return InvoiceResponse.model_validate(invoice)

    async def delete_invoice(self, invoice_id: str) -> dict[str, str]:
        deleted = await self.repository.delete(invoice_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )
        return {"message": f"Invoice {invoice_id} deleted successfully"}
