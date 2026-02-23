from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, Body
from app.core.dependencies import get_invoice_service
from app.models.invoice import ProcessingStatus
from app.schemas.invoice import (
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceTaxExemptUpdate,
)
from app.services.invoice_service import InvoiceService

router = APIRouter()


@router.post(
    "/upload",
    response_model=InvoiceResponse,
    summary="Upload and process an invoice",
    status_code=201,
)
async def upload_and_process_invoice(
    file: UploadFile = File(...),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    """
    Upload an invoice file (PDF or image) and process it
    through the AI pipeline automatically.

    The pipeline will:
    1. Extract text via OCR
    2. Extract structured fields via LLM
    3. Validate data integrity
    4. Detect anomalies and fraud patterns
    5. Return the fully processed invoice
    """
    return await service.upload_and_process_invoice(file)


@router.get(
    "/",
    response_model=InvoiceListResponse,
    summary="List invoices with pagination and filters",
)
async def list_invoices(
    service: InvoiceService = Depends(get_invoice_service),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    status: Optional[ProcessingStatus] = Query(
        None, description="Filter by processing status"
    ),
    vendor_name: Optional[str] = Query(
        None, description="Filter by vendor name (case-insensitive contains)"
    ),
    created_after: Optional[date] = Query(
        None, description="Invoices created on or after this date (YYYY-MM-DD)"
    ),
    created_before: Optional[date] = Query(
        None, description="Invoices created on or before this date (YYYY-MM-DD)"
    ),
) -> InvoiceListResponse:
    return await service.get_all_invoices(
        skip=skip,
        limit=limit,
        status=status,
        vendor_name=vendor_name,
        created_after=created_after,
        created_before=created_before,
    )


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get a single invoice",
)
async def get_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    return await service.get_invoice_by_id(invoice_id)


@router.post(
    "/{invoice_id}/reprocess",
    response_model=InvoiceResponse,
    summary="Re-run the pipeline for an existing invoice",
)
async def reprocess_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    """
    Re-process an invoice (OCR, extraction, validation, anomaly) using the current
    whitelist and tax-exemption settings. Use after updating whitelist or extraction prompt.
    """
    return await service.reprocess_invoice(invoice_id)


@router.patch(
    "/{invoice_id}/tax-exemption",
    response_model=InvoiceResponse,
    summary="Update tax exemption status",
)
async def update_tax_exemption(
    invoice_id: str,
    data: InvoiceTaxExemptUpdate = Body(...),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    return await service.update_tax_exemption(invoice_id, data)


@router.delete(
    "/{invoice_id}",
    summary="Delete an invoice",
)
async def delete_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, str]:
    return await service.delete_invoice(invoice_id)