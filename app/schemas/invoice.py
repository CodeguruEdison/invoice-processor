from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.invoice import ProcessingStatus


class InvoiceUploadResponse(BaseModel):
    message: str
    filename: str
    file_path: str
    size_mb: float
    status: ProcessingStatus


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_path: str
    size_mb: float
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    line_items: dict | None = None
    validation_errors: dict | None = None
    anomaly_flags: dict | None = None
    status: ProcessingStatus
    confidence_score: float = 0.0
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    total: int
    invoices: list[InvoiceResponse]
