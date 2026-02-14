from app.repositories.product_repository_interface import IProductRepository
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductListResponse,
)
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


class ProductService:

    def __init__(self, repository: IProductRepository) -> None:
        self.repository = repository

    async def create(
        self,
        data: ProductCreate,
    ) -> ProductResponse:
        entity = Product(
            data.name, data.description,
        )
        saved = await self.repository.create(entity)
        return ProductResponse.model_validate(saved)

    async def get_by_id(
        self,
        entity_id: str,
    ) -> ProductResponse:
        entity = await self.repository.get_by_id(entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Product not found",
            )
        return ProductResponse.model_validate(entity)

    async def get_all(self) -> ProductListResponse:
        items = await self.repository.get_all_active()
        return ProductListResponse(
            total=len(items),
            items=[ProductResponse.model_validate(i) for i in items],
        )

    async def deactivate(
        self,
        entity_id: str,
    ) -> ProductResponse:
        entity = await self.repository.deactivate(entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Product not found",
            )
        return ProductResponse.model_validate(entity)
