from abc import abstractmethod
from typing import Optional
from app.repositories.base_repository import BaseRepository
from app.models.invoice import Invoice, ProcessingStatus


class IInvoiceRepository(BaseRepository[Invoice]):

    @abstractmethod
    async def get_by_invoice_number(
        self,
        invoice_number: str,
    ) -> Optional[Invoice]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_status(
        self,
        status: ProcessingStatus,
    ) -> list[Invoice]:
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self,
        invoice_id: str,
        status: ProcessingStatus,
    ) -> Optional[Invoice]:
        raise NotImplementedError