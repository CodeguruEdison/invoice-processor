from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.repositories.whitelist_repository_interface import IWhitelistRepository
from app.models.whitelist import WhitelistedVendor
import logging

logger = logging.getLogger(__name__)


class WhitelistRepository(IWhitelistRepository):

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, entity: WhitelistedVendor) -> WhitelistedVendor:
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Created whitelisted vendor: {entity.vendor_name}")
        return entity

    async def get_by_id(
        self,
        entity_id: str,
    ) -> Optional[WhitelistedVendor]:
        result = await self.db.execute(
            select(WhitelistedVendor).where(
                WhitelistedVendor.id == entity_id
            )
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[WhitelistedVendor]:
        result = await self.db.execute(select(WhitelistedVendor))
        return list(result.scalars().all())

    async def get_all_active(self) -> list[WhitelistedVendor]:
        result = await self.db.execute(
            select(WhitelistedVendor).where(
                WhitelistedVendor.is_active == True  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_by_vendor_name(
        self,
        vendor_name: str,
    ) -> Optional[WhitelistedVendor]:
        # Exact match (case-insensitive) for duplicate check; avoids MultipleResultsFound
        result = await self.db.execute(
            select(WhitelistedVendor).where(
                WhitelistedVendor.vendor_name.ilike(vendor_name.strip())
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        entity: WhitelistedVendor,
    ) -> WhitelistedVendor:
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def deactivate(
        self,
        vendor_id: str,
    ) -> Optional[WhitelistedVendor]:
        vendor = await self.get_by_id(vendor_id)
        if not vendor:
            return None
        vendor.is_active = False
        await self.db.commit()
        await self.db.refresh(vendor)
        logger.info(f"Deactivated vendor: {vendor.vendor_name}")
        return vendor

    async def delete(self, entity_id: str) -> bool:
        vendor = await self.get_by_id(entity_id)
        if not vendor:
            return False
        await self.db.delete(vendor)
        await self.db.commit()
        return True