from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, ProcessingStatus
from app.repositories.invoice_repository_interface import IInvoiceRepository
import logging

logger = logging.getLogger(__name__)


class InvoiceRepository(IInvoiceRepository):

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, entity: Invoice) -> Invoice:
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Created invoice: {entity.id}")
        return entity

    async def get_by_id(self, entity_id: str) -> Optional[Invoice]:
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Invoice]:
        result = await self.db.execute(select(Invoice))
        return list(result.scalars().all())

    async def get_paginated(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[ProcessingStatus] = None,
        vendor_name_contains: Optional[str] = None,
        created_after: Optional[date] = None,
        created_before: Optional[date] = None,
    ) -> tuple[list[Invoice], int]:
        conditions = []
        if status is not None:
            conditions.append(Invoice.status == status)
        if vendor_name_contains is not None and vendor_name_contains.strip():
            conditions.append(
                Invoice.vendor_name.ilike(f"%{vendor_name_contains.strip()}%")
            )
        if created_after is not None:
            conditions.append(
                func.date(Invoice.created_at) >= created_after
            )
        if created_before is not None:
            conditions.append(
                func.date(Invoice.created_at) <= created_before
            )
        base = select(Invoice)
        count_stmt = select(func.count()).select_from(Invoice)
        if conditions:
            base = base.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        stmt = base.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def update(self, entity: Invoice) -> Invoice:
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Updated invoice: {entity.id}")
        return entity

    async def delete(self, entity_id: str) -> bool:
        invoice = await self.get_by_id(entity_id)
        if not invoice:
            return False
        await self.db.delete(invoice)
        await self.db.commit()
        logger.info(f"Deleted invoice: {entity_id}")
        return True

    async def get_by_invoice_number(
        self,
        invoice_number: str,
    ) -> Optional[Invoice]:
        result = await self.db.execute(
            select(Invoice).where(Invoice.invoice_number == invoice_number)
        )
        return result.scalar_one_or_none()

    async def get_by_status(
        self,
        status: ProcessingStatus,
    ) -> list[Invoice]:
        result = await self.db.execute(
            select(Invoice).where(Invoice.status == status)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        invoice_id: str,
        status: ProcessingStatus,
    ) -> Optional[Invoice]:
        invoice = await self.get_by_id(invoice_id)
        if not invoice:
            return None
        invoice.status = status
        await self.db.commit()
        await self.db.refresh(invoice)
        logger.info(f"Updated invoice {invoice_id} status to {status}")
        return invoice