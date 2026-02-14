from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.invoice_service import InvoiceService
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.invoice_repository_interface import IInvoiceRepository
from app.repositories.whitelist_repository_interface import IWhitelistRepository


def get_invoice_repository(
    db: AsyncSession = Depends(get_db),
) -> IInvoiceRepository:
    return InvoiceRepository(db)


def get_invoice_service(
    repository: IInvoiceRepository = Depends(get_invoice_repository),
) -> InvoiceService:
    return InvoiceService(repository)


def get_whitelist_repository(
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.whitelist_repository import WhitelistRepository
    return WhitelistRepository(db)


def get_whitelist_service(
    repository: IWhitelistRepository = Depends(get_whitelist_repository),
):
    from app.services.whitelist_service import WhitelistService
    return WhitelistService(repository)