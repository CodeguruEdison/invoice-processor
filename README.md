# Invoice Processor

FastAPI app for uploading, storing, and managing invoices with PostgreSQL and optional Redis.

## Architecture

![Architecture diagram](docs/architecture.png)

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart TB
    subgraph Client["Client"]
        User[User / API Client]
    end

    subgraph API["API Layer"]
        FastAPI[FastAPI App]
        InvoiceRouter["/api/v1/invoices"]
        WhitelistRouter["/api/v1/whitelist"]
    end

    subgraph Services["Service Layer"]
        InvoiceService[InvoiceService]
        WhitelistService[WhitelistService]
        DoclingService[DoclingService]
    end

    subgraph DataAccess["Data Access"]
        InvoiceRepo[InvoiceRepository]
        WhitelistRepo[WhitelistRepository]
    end

    subgraph Pipeline["ML Pipeline (LangGraph)"]
        direction LR
        OCR[OCR Node]
        Extract[Extract Node]
        Validate[Validate Node]
        Retry[Retry Node]
        Anomaly[Anomaly Node]
        Failed[Failed Node]
        OCR --> Extract --> Validate
        Validate -->|proceed| Anomaly
        Validate -->|retry| Retry --> Extract
        Validate -->|failed| Failed
        Anomaly --> END
        Failed --> END
    end

    subgraph External["External / Storage"]
        Postgres[(PostgreSQL)]
        Redis[(Redis)]
        Ollama[Ollama LLM]
        DoclingLib[Docling]
        Uploads[Uploads Dir]
    end

    User --> FastAPI
    FastAPI --> InvoiceRouter
    FastAPI --> WhitelistRouter
    InvoiceRouter --> InvoiceService
    WhitelistRouter --> WhitelistService
    InvoiceService --> InvoiceRepo
    InvoiceService --> WhitelistRepo
    InvoiceService --> DoclingService
    InvoiceService --> Pipeline
    Pipeline --> DoclingLib
    Pipeline --> Ollama
    InvoiceRepo --> Postgres
    WhitelistRepo --> Postgres
    InvoiceService --> Uploads
```

</details>

**Request flow (upload):** Client → FastAPI → Invoice router → InvoiceService (file validation, save to disk) → ML pipeline (OCR → Extract → Validate → Anomaly / Retry / Failed) → InvoiceRepository persists to PostgreSQL. OCR uses Docling when `OCR_USE_DOCLING` is true, otherwise PyMuPDF/pdfplumber/Tesseract or an Ollama vision model. Extraction and anomaly detection use Ollama.

## Prerequisites

- **Python 3.11+**
- **Poetry** ([install](https://python-poetry.org/docs/#installation))
- **Docker & Docker Compose** (optional, for Postgres and Redis)

## Setup

### 1. Clone and enter the project

```bash
cd invoice-processor
```

### 2. Environment variables

Create a `.env` file in the project root (see `.env.example` if present, or use):

```env
APP_NAME="Invoice Processor"
APP_VERSION="1.0.0"
DEBUG=True
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/invoice_db
REDIS_URL=redis://localhost:6379/0
```

Adjust `DATABASE_URL` if your Postgres user, password, host, or database name differ.

### 3. Start PostgreSQL (and Redis) with Docker

```bash
docker compose up -d
```

This starts:

- **Postgres** on `localhost:5432` (user `postgres`, password `postgres`, DB `invoice_db`)
- **Redis** on `localhost:6379`
- **pgAdmin** on `http://localhost:5050` (optional; login: `admin@admin.com` / `admin`)

If you use a different Postgres setup, ensure `DATABASE_URL` in `.env` matches it.

### 4. Install dependencies

```bash
poetry install
```

### 5. Run migrations

Apply all pending migrations (creates/updates tables):

```bash
poetry run migrate
```

Or use the Alembic CLI directly:

```bash
poetry run alembic upgrade head
```

**Create a new migration** after changing models in `app/models/`:

```bash
poetry run migration 'describe your change'
```

Example:

```bash
poetry run migration 'add vendor_email to invoices'
```

Then apply it:

```bash
poetry run migrate
```

**Rollback one migration:**

```bash
poetry run downgrade
```

**Create a new API resource** (model, schema, repository, service, router + README):

```bash
poetry run new-resource <name> [--fields "field:type,..."]
```

Example:

```bash
poetry run new-resource product --fields "name:str,description:str|None"
```

Then create and apply a migration for the new table (see step 5 above). The project README is updated automatically with the new endpoints.

### 6. Run the app

```bash
poetry run dev
```

The API runs at **http://localhost:8000**.

- **API docs (Swagger):** http://localhost:8000/docs  
- **ReDoc:** http://localhost:8000/redoc  

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | App info (name, version, debug) |
| `GET`  | `/health` | Health check (DB, optional Redis) |
| `POST` | `/api/v1/invoices/upload` | Upload and process an invoice (PDF, PNG, JPG) |
| `GET`  | `/api/v1/invoices/` | List invoices (supports `skip`, `limit`, `status`, `vendor_name`, `created_after`, `created_before`) |
| `GET`  | `/api/v1/invoices/{id}` | Get one invoice |
| `PATCH` | `/api/v1/invoices/{id}/tax-exemption` | Update tax exemption status |
| `POST` | `/api/v1/invoices/{id}/reprocess` | Re-run the pipeline for an existing invoice |
| `DELETE` | `/api/v1/invoices/{id}` | Delete an invoice (and its file from disk) |
| `POST` | `/api/v1/whitelist/` | Add a whitelisted vendor |
| `GET`  | `/api/v1/whitelist/` | List whitelisted vendors |
| `DELETE` | `/api/v1/whitelist/{id}` | Deactivate a whitelisted vendor |

Uploaded files are stored under the `uploads/` directory (configurable via `UPLOAD_DIR` in config).

### Optional environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama API base URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model used for extraction and anomaly | `llama3.2:8b` |
| `OLLAMA_VISION_MODEL` | Vision model for OCR (if using vision LLM) | (empty) |
| `OCR_USE_VISION_LLM` | Use vision LLM for OCR when set | `False` |
| `OCR_USE_DOCLING` | Use Docling for document parsing | `True` |
| `EXTRACTION_PROMPT_FILE` | Path to custom extraction prompt file | (none) |
| `MAX_UPLOAD_SIZE_MB` | Max upload size in MB | `10.0` |
| `UPLOAD_DIR` | Directory for uploaded files | `uploads` |
| `CORS_ORIGINS` | Comma-separated allowed origins for CORS (empty = same-origin only) | (empty) |

## Development

- **Format code:** `poetry run ruff format app migrations`
- **Lint:** `poetry run ruff check app migrations`
- **Tests:** `poetry run pytest tests/ -v`

## Project structure

```
app/
├── api/v1/endpoints/   # API routes
├── core/                # Config, database, dependencies, CLI
├── models/              # SQLAlchemy models
├── repositories/         # Data access
├── schemas/             # Pydantic request/response models
├── services/            # Business logic
└── main.py              # FastAPI app
migrations/              # Alembic migrations
```
