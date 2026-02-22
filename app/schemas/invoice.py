from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, Any
from app.models.invoice import ProcessingStatus


class LineItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    quantity: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    total: float = Field(ge=0)


class InvoiceUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    filename: str
    file_path: str
    size_mb: float = Field(gt=0)
    status: ProcessingStatus


def _normalize_json_list(
    value: Any, dict_key: str
) -> Optional[list]:
    """Accept list or dict with a single key (e.g. {'items': [...]}) for DB backward compatibility."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and dict_key in value:
        return value[dict_key] if value[dict_key] is not None else []
    return None


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    size_mb: float
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    line_items: Optional[list[LineItemSchema]] = None
    validation_errors: Optional[list[str]] = None
    anomaly_flags: Optional[list[str]] = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    retry_count: int = Field(default=0, ge=0)
    status: ProcessingStatus
    is_tax_exempt: bool = False
    tax_exempt_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("line_items", mode="before")
    @classmethod
    def normalize_line_items(cls, v: Any) -> Optional[list]:
        return _normalize_json_list(v, "items")

    @field_validator("validation_errors", mode="before")
    @classmethod
    def normalize_validation_errors(cls, v: Any) -> Optional[list]:
        return _normalize_json_list(v, "errors")

    @field_validator("anomaly_flags", mode="before")
    @classmethod
    def normalize_anomaly_flags(cls, v: Any) -> Optional[list]:
        return _normalize_json_list(v, "flags")


class InvoiceListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int = Field(ge=0)
    invoices: list[InvoiceResponse]


class InvoiceTaxExemptUpdate(BaseModel):
    """Schema for updating tax exemption status."""
    is_tax_exempt: bool
    tax_exempt_reason: Optional[str] = Field(
        None,
        description="Reason for tax exemption e.g. 'Government entity' or 'Reseller'",
    )