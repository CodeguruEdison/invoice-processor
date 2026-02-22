from fastapi import APIRouter, UploadFile, File, Depends, Body
from app.core.dependencies import get_invoice_service
from app.services.invoice_service import InvoiceService
from app.schemas.invoice import (
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceTaxExemptUpdate,
)

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
    summary="List all invoices",
)
async def list_invoices(
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceListResponse:
    return await service.get_all_invoices()


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