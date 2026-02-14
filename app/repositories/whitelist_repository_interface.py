from abc import abstractmethod
from typing import Optional
from app.repositories.base_repository import BaseRepository
from app.models.whitelist import WhitelistedVendor


class IWhitelistRepository(BaseRepository[WhitelistedVendor]):

    @abstractmethod
    async def get_by_vendor_name(
        self,
        vendor_name: str,
    ) -> Optional[WhitelistedVendor]:
        raise NotImplementedError

    @abstractmethod
    async def get_all_active(self) -> list[WhitelistedVendor]:
        raise NotImplementedError

    @abstractmethod
    async def deactivate(self, vendor_id: str) -> Optional[WhitelistedVendor]:
        raise NotImplementedError