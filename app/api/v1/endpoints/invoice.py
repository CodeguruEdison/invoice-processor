from fastapi import APIRouter, UploadFile, File, Depends
from app.core.dependencies import get_invoice_service
from app.services.invoice_service import InvoiceService
from app.schemas.invoice import (
    InvoiceUploadResponse,
    InvoiceListResponse,
    InvoiceResponse,
)

router = APIRouter()


@router.post(
    "/upload",
    response_model=InvoiceUploadResponse,
    summary="Upload an invoice",
    status_code=201,
)
async def upload_invoice(
    file: UploadFile = File(...),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceUploadResponse:
    return await service.upload_invoice(file)


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


@router.delete(
    "/{invoice_id}",
    summary="Delete an invoice",
)
async def delete_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> dict[str, str]:
    return await service.delete_invoice(invoice_id)