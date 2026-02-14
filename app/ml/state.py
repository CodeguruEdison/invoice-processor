from typing import TypedDict, Optional
from enum import Enum


class PipelineStatus(str, Enum):
    """
    Represents where the invoice is in the pipeline.
    We use str Enum so it serializes cleanly to JSON
    and works nicely with SQLAlchemy and Pydantic.
    """
    PENDING = "pending"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    FAILED = "failed"
    ANOMALY_FLAGGED = "anomaly_flagged"
    COMPLETED = "completed"


class PipelineState(TypedDict):
    file_path: str
    raw_text: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    line_items: Optional[list[dict]] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    confidence_score: float = 0.0
    validation_errors: Optional[dict] = None
    retry_count: int = 0
    anomaly_flags: list[str] = []
    status: PipelineStatus 
    
    
