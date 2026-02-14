from app.repositories.whitelist_repository_interface import IWhitelistRepository
from app.models.whitelist import WhitelistedVendor
from app.schemas.whitelist import (
    WhitelistedVendorCreate,
    WhitelistedVendorResponse,
    WhitelistedVendorListResponse,
)
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


class WhitelistService:

    def __init__(self, repository: IWhitelistRepository) -> None:
        self.repository = repository

    async def is_vendor_whitelisted(
        self,
        vendor_name: str,
    ) -> bool:
        """
        WHY WE FETCH ALL ACTIVE VENDORS:
        Instead of querying per vendor name we load
        all active vendors into memory and check locally.
        This is faster for small lists and avoids
        multiple DB round trips per invoice.
        """
        if not vendor_name:
            return False

        vendors = await self.repository.get_all_active()
        vendor_lower = vendor_name.lower().strip()

        for vendor in vendors:
            whitelisted = vendor.vendor_name.lower().strip()

            # Exact match
            if vendor_lower == whitelisted:
                logger.info(f"Vendor exact match: {vendor_name}")
                return True

            # Partial match
            if whitelisted in vendor_lower or vendor_lower in whitelisted:
                logger.info(f"Vendor partial match: {vendor_name}")
                return True

        return False

    async def filter_anomalies(
        self,
        anomalies: list[str],
        vendor_name: str | None,
    ) -> list[str]:
        if not vendor_name:
            return anomalies

        is_whitelisted = await self.is_vendor_whitelisted(vendor_name)
        if not is_whitelisted:
            return anomalies

        filtered = [
            anomaly for anomaly in anomalies
            if not any(
                keyword in anomaly.lower()
                for keyword in [
                    "vendor",
                    "vendor name",
                    "company name",
                    "generic name",
                    "suspicious name",
                ]
            )
        ]

        if len(filtered) < len(anomalies):
            logger.info(
                f"Filtered {len(anomalies) - len(filtered)} "
                f"vendor anomalies for: {vendor_name}"
            )

        return filtered

    async def add_vendor(
        self,
        data: WhitelistedVendorCreate,
    ) -> WhitelistedVendorResponse:
        # Check if already exists
        existing = await self.repository.get_by_vendor_name(
            data.vendor_name
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Vendor '{data.vendor_name}' already whitelisted",
            )

        vendor = WhitelistedVendor(
            vendor_name=data.vendor_name,
            added_by=data.added_by,
            notes=data.notes,
        )
        saved = await self.repository.create(vendor)
        return WhitelistedVendorResponse.model_validate(saved)

    async def get_all_vendors(self) -> WhitelistedVendorListResponse:
        vendors = await self.repository.get_all_active()
        return WhitelistedVendorListResponse(
            total=len(vendors),
            vendors=[
                WhitelistedVendorResponse.model_validate(v)
                for v in vendors
            ],
        )

    async def deactivate_vendor(
        self,
        vendor_id: str,
    ) -> WhitelistedVendorResponse:
        vendor = await self.repository.deactivate(vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor {vendor_id} not found",
            )
        return WhitelistedVendorResponse.model_validate(vendor)
