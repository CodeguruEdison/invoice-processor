import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.endpoints import invoice as invoice_endpoints
from app.core.config import settings
from app.core.database import Base, engine
from app.models import invoice  # noqa: F401 - registers models
from app.models import whitelist  # noqa: F401 - registers models
from app.models import product  # noqa: F401 - registers models

from app.api.v1.endpoints import whitelist as whitelist_endpoints
from app.api.v1.endpoints import product as product_endpoints

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
app.include_router(
    product_endpoints.router,
    prefix="/api/v1/product",
    tags=["product"],
)

@app.get("/")
def root():
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
    }


def start():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
