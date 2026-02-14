from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.invoice_service import InvoiceService
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.invoice_repository_interface import IInvoiceRepository


def get_invoice_repository(
    db: AsyncSession = Depends(get_db),
) -> IInvoiceRepository:
    return InvoiceRepository(db)


def get_invoice_service(
    repository: IInvoiceRepository = Depends(get_invoice_repository),
) -> InvoiceService:
    return InvoiceService(repository)