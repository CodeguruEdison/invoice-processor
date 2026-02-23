"""API endpoint tests using TestClient.

Note: TestClient runs the app in a thread with its own event loop. With async DB
(asyncpg), only one request that touches the DB should be made per test run to avoid
"another operation in progress" / "Future attached to a different loop" errors.
We keep a single list_invoices test that hits the DB; 404 and pagination are
covered by service-layer tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_root_returns_app_info(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "app_version" in data


def test_list_invoices_returns_200_and_structure(client: TestClient) -> None:
    """Single DB request: list invoices with pagination params; check response shape."""
    response = client.get("/api/v1/invoices/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "invoices" in data
    assert isinstance(data["invoices"], list)
    assert data["total"] >= 0
    assert len(data["invoices"]) <= 10


def test_upload_rejects_bad_extension(client: TestClient) -> None:
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("bad.exe", b"MZ binary content", "application/octet-stream")},
    )
    assert response.status_code == 422 or response.status_code == 400


def test_upload_requires_file(client: TestClient) -> None:
    response = client.post("/api/v1/invoices/upload")
    assert response.status_code == 422
