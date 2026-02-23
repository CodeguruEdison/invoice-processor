import logging
import sys
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.endpoints import invoice as invoice_endpoints
from app.core.config import settings
from app.core.database import Base, engine  # noqa: F401

# Send app logs (including Docling) to the terminal; uvicorn often doesn't show them otherwise
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
if not _app_log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    _app_log.addHandler(_handler)

from app.models import invoice  # noqa: F401 - registers models
from app.models import whitelist  # noqa: F401 - registers models
from app.models import product  # noqa: F401 - registers models

from app.api.v1.endpoints import whitelist as whitelist_endpoints


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.create_all)
        print("✅ Database connected successfully")
    yield
    await engine.dispose()
    print("Disconnected from the database")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

if settings.CORS_ORIGINS.strip():
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(
    invoice_endpoints.router,
    prefix="/api/v1/invoices",
    tags=["invoices"],
)

app.include_router(
    whitelist_endpoints.router,
    prefix="/api/v1/whitelist",
    tags=["whitelist"],
)

@app.get("/")
def root():
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
    }


@app.get("/health")
async def health():
    """
    Health check for load balancers and containers.
    Returns 200 with database status; 503 if database is unreachable.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        logging.getLogger(__name__).warning("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "error", "detail": str(e)},
        )


def start():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
