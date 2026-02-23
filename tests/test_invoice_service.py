"""Service-layer tests for InvoiceService with mocked dependencies."""
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.models.invoice import Invoice, ProcessingStatus
from app.services.invoice_service import InvoiceService


def _make_mock_upload(
    filename: str = "test.pdf",
    content: bytes = b"%PDF-1.4 minimal",
    content_type: str = "application/pdf",
) -> UploadFile:
    f = MagicMock(spec=UploadFile)
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


@pytest.fixture
def mock_invoice_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_all = AsyncMock(return_value=[])
    repo.get_paginated = AsyncMock(return_value=([], 0))
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_whitelist_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_all_active = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_docling() -> MagicMock:
    return MagicMock()


@pytest.fixture
def invoice_service(
    mock_invoice_repo: MagicMock,
    mock_whitelist_repo: MagicMock,
    mock_docling: MagicMock,
) -> InvoiceService:
    return InvoiceService(
        mock_invoice_repo,
        mock_whitelist_repo,
        mock_docling,
    )


@pytest.mark.asyncio
async def test_upload_rejects_empty_filename(invoice_service: InvoiceService) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.upload_and_process_invoice(_make_mock_upload(filename=""))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension(invoice_service: InvoiceService) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.upload_and_process_invoice(
            _make_mock_upload(filename="file.exe", content=b"MZ")
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(invoice_service: InvoiceService) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.upload_and_process_invoice(
            _make_mock_upload(filename="test.pdf", content=b"")
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_content_mismatch(invoice_service: InvoiceService) -> None:
    """PDF extension but non-PDF content should be rejected."""
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.upload_and_process_invoice(
            _make_mock_upload(filename="fake.pdf", content=b"not a pdf at all")
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_pipeline_failure_updates_invoice_and_raises(
    invoice_service: InvoiceService,
    mock_invoice_repo: MagicMock,
    tmp_path: Path,
) -> None:
    """When process_invoice raises, invoice is updated to FAILED and 500 is raised."""
    created = Invoice(
        id="inv-1",
        filename="x.pdf",
        file_path=str(tmp_path / "x.pdf"),
        size_mb=0.01,
        status=ProcessingStatus.PENDING,
    )
    mock_invoice_repo.create = AsyncMock(return_value=created)
    mock_invoice_repo.get_by_id = AsyncMock(return_value=created)

    with (
        patch("app.services.invoice_service.settings") as mock_settings,
        patch("app.services.invoice_service.process_invoice") as mock_pipeline,
    ):
        mock_settings.UPLOAD_DIR = tmp_path
        mock_settings.ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
        mock_settings.MAX_UPLOAD_SIZE_MB = 10.0
        mock_settings.DEBUG = True
        mock_pipeline.side_effect = RuntimeError("Ollama unavailable")

        with pytest.raises(HTTPException) as exc_info:
            await invoice_service.upload_and_process_invoice(
                _make_mock_upload(filename="test.pdf")
            )

        assert exc_info.value.status_code == 500
        mock_invoice_repo.update.assert_called_once()
        updated = mock_invoice_repo.update.call_args[0][0]
        assert updated.status == ProcessingStatus.FAILED
        assert "Ollama unavailable" in (updated.validation_errors or [""])[0]


@pytest.mark.asyncio
async def test_get_all_invoices_pagination(
    invoice_service: InvoiceService,
    mock_invoice_repo: MagicMock,
) -> None:
    inv = Invoice(
        id="i1",
        filename="a.pdf",
        file_path="/u/a.pdf",
        size_mb=1.0,
        status=ProcessingStatus.COMPLETED,
        confidence_score=0.0,
        retry_count=0,
        is_tax_exempt=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mock_invoice_repo.get_paginated = AsyncMock(return_value=([inv], 1))

    result = await invoice_service.get_all_invoices(skip=10, limit=5)

    assert result.total == 1
    assert len(result.invoices) == 1
    mock_invoice_repo.get_paginated.assert_called_once()
    call_kw = mock_invoice_repo.get_paginated.call_args[1]
    assert call_kw["skip"] == 10
    assert call_kw["limit"] == 5


@pytest.mark.asyncio
async def test_get_invoice_by_id_not_found(
    invoice_service: InvoiceService,
    mock_invoice_repo: MagicMock,
) -> None:
    mock_invoice_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.get_invoice_by_id("nonexistent")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_invoice_not_found(
    invoice_service: InvoiceService,
    mock_invoice_repo: MagicMock,
) -> None:
    mock_invoice_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.delete_invoice("nonexistent")

    assert exc_info.value.status_code == 404
    mock_invoice_repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_invoice_removes_file(
    invoice_service: InvoiceService,
    mock_invoice_repo: MagicMock,
    tmp_path: Path,
) -> None:
    """Delete should unlink file on disk then delete from DB."""
    file_path = tmp_path / "to_delete.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    inv = Invoice(
        id="inv-del",
        filename="to_delete.pdf",
        file_path=str(file_path),
        size_mb=0.01,
        status=ProcessingStatus.COMPLETED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mock_invoice_repo.get_by_id = AsyncMock(return_value=inv)
    mock_invoice_repo.delete = AsyncMock(return_value=True)

    result = await invoice_service.delete_invoice("inv-del")

    assert result["message"] == "Invoice inv-del deleted successfully"
    assert not file_path.exists()
    mock_invoice_repo.delete.assert_called_once_with("inv-del")
