# Invoice Processor

FastAPI app for uploading, storing, and managing invoices with PostgreSQL and optional Redis.

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
| `GET`  | `/` | Health/info |
| `POST` | `/api/v1/invoices/upload` | Upload an invoice (PDF, PNG, JPG) |
| `GET`  | `/api/v1/invoices/` | List all invoices |
| `GET`  | `/api/v1/invoices/{id}` | Get one invoice |
| `DELETE` | `/api/v1/invoices/{id}` | Delete an invoice |

Uploaded files are stored under the `uploads/` directory (configurable via `UPLOAD_DIR` in config).

## Development

- **Format code:** `poetry run ruff format app migrations`
- **Lint:** `poetry run ruff check app migrations`

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
