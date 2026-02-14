from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    total: int
    items: list[ProductResponse]
    
class InvoiceTaxExemptUpdate(BaseModel):
    is_tax_exempt: bool
    tax_exempt_reason: Optional[str] = Field(
        None,
        description="Reason for tax exemption e.g. 'Government entity' or 'Reseller'"
    )