from abc import abstractmethod
from typing import Optional
from app.repositories.base_repository import BaseRepository
from app.models.product import Product


class IProductRepository(BaseRepository[Product]):

    @abstractmethod
    async def get_all_active(self) -> list[Product]:
        raise NotImplementedError

    @abstractmethod
    async def deactivate(self, entity_id: str) -> Optional[Product]:
        raise NotImplementedError
