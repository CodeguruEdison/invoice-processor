from abc import abstractmethod
from datetime import date
from typing import Optional
from app.repositories.base_repository import BaseRepository
from app.models.invoice import Invoice, ProcessingStatus


class IInvoiceRepository(BaseRepository[Invoice]):

    @abstractmethod
    async def get_paginated(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[ProcessingStatus] = None,
        vendor_name_contains: Optional[str] = None,
        created_after: Optional[date] = None,
        created_before: Optional[date] = None,
    ) -> tuple[list[Invoice], int]:
        """Return (invoices, total_count) with optional filters."""
        raise NotImplementedError

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