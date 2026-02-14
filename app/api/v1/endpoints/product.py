from fastapi import APIRouter, Depends
from app.core.dependencies import get_product_service
from app.services.product_service import ProductService
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductListResponse,
)

router = APIRouter()


@router.post(
    "/",
    response_model=ProductResponse,
    summary=f"Create product",
    status_code=201,
)
async def create(
    data: ProductCreate,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.create(data)


@router.get(
    "/",
    response_model=ProductListResponse,
    summary=f"List all products",
)
async def list_all(
    service: ProductService = Depends(get_product_service),
) -> ProductListResponse:
    return await service.get_all()


@router.get(
    "/{entity_id}",
    response_model=ProductResponse,
    summary=f"Get product by ID",
)
async def get_one(
    entity_id: str,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.get_by_id(entity_id)


@router.delete(
    "/{entity_id}",
    response_model=ProductResponse,
    summary=f"Deactivate product",
)
async def deactivate(
    entity_id: str,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.deactivate(entity_id)
