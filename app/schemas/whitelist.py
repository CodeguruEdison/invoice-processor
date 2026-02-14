from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional


class WhitelistedVendorCreate(BaseModel):
    vendor_name: str = Field(min_length=2)
    added_by: Optional[str] = None
    notes: Optional[str] = None


class WhitelistedVendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_name: str
    added_by: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WhitelistedVendorListResponse(BaseModel):
    total: int
    vendors: list[WhitelistedVendorResponse]