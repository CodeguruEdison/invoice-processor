import uvicorn
from fastapi import FastAPI
from app.core.config import settings
from app.core.database import engine
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        print("✅ Database connected successfully")
    yield
    await engine.dispose()
    print("Disconnected from the database")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
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