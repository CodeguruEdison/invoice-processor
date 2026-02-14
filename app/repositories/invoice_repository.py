from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.repositories.invoice_repository_interface import IInvoiceRepository
from app.models.invoice import Invoice, ProcessingStatus
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