from fastapi import APIRouter, Depends
from app.core.dependencies import get_whitelist_service
from app.services.whitelist_service import WhitelistService
from app.schemas.whitelist import (
    WhitelistedVendorCreate,
    WhitelistedVendorResponse,
    WhitelistedVendorListResponse,
)

router = APIRouter()


@router.post(
    "/",
    response_model=WhitelistedVendorResponse,
    summary="Add vendor to whitelist",
    status_code=201,
)
async def add_vendor(
    data: WhitelistedVendorCreate,
    service: WhitelistService = Depends(get_whitelist_service),
) -> WhitelistedVendorResponse:
    return await service.add_vendor(data)


@router.get(
    "/",
    response_model=WhitelistedVendorListResponse,
    summary="List all whitelisted vendors",
)
async def list_vendors(
    service: WhitelistService = Depends(get_whitelist_service),
) -> WhitelistedVendorListResponse:
    return await service.get_all_vendors()


@router.delete(
    "/{vendor_id}",
    response_model=WhitelistedVendorResponse,
    summary="Deactivate a whitelisted vendor",
)
async def deactivate_vendor(
    vendor_id: str,
    service: WhitelistService = Depends(get_whitelist_service),
) -> WhitelistedVendorResponse:
    return await service.deactivate_vendor(vendor_id)