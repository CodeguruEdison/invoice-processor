import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import enum


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    FAILED = "failed"
    ANOMALY_FLAGGED = "anomaly_flagged"
    COMPLETED = "completed"


class Invoice(Base):
    __tablename__ = "invoices"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # File info
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    size_mb: Mapped[float] = mapped_column(Float, nullable=False)

    # Extracted fields
    vendor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String, nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String, nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # JSON fields
    line_items: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    anomaly_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Processing metadata
    status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number} - {self.vendor_name} - {self.status}>"