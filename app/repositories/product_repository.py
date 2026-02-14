from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.repositories.product_repository_interface import IProductRepository
from app.models.product import Product
import logging

logger = logging.getLogger(__name__)


class ProductRepository(IProductRepository):

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, entity: Product) -> Product:
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Created {entity.__class__.__name__}: {entity.id}")
        return entity

    async def get_by_id(
        self,
        entity_id: str,
    ) -> Optional[Product]:
        result = await self.db.execute(
            select(Product).where(Product.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Product]:
        result = await self.db.execute(select(Product))
        return list(result.scalars().all())

    async def get_all_active(self) -> list[Product]:
        result = await self.db.execute(
            select(Product).where(Product.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def update(
        self,
        entity: Product,
    ) -> Product:
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def deactivate(
        self,
        entity_id: str,
    ) -> Optional[Product]:
        entity = await self.get_by_id(entity_id)
        if not entity:
            return None
        entity.is_active = False
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Deactivated {entity.__class__.__name__}: {entity.id}")
        return entity

    async def delete(self, entity_id: str) -> bool:
        entity = await self.get_by_id(entity_id)
        if not entity:
            return False
        await self.db.delete(entity)
        await self.db.commit()
        return True
