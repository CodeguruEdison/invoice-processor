from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
    APP_NAME: str = "Invoice Processor"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/invoice_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: Path = Path("uploads")
    ALLOWED_EXTENSIONS: set[str] = {"pdf", "png", "jpg", "jpeg"}
    MAX_UPLOAD_SIZE_MB: float = 10.0
    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:8b"
    # Optional vision model for OCR (e.g. llava:7b, llama3.2-vision:11b)
    OLLAMA_VISION_MODEL: str = ""
    # Use vision LLM for OCR instead of Tesseract when set and OLLAMA_VISION_MODEL is set
    OCR_USE_VISION_LLM: bool = False
    # Use Docling for document parsing (PDF/images) when True and DoclingService is injected
    OCR_USE_DOCLING: bool = True
    # Optional path to extraction prompt file. If set and file exists, use it instead of built-in prompt.
    # File must contain {raw_text}. Edit this file to adapt to different invoice formats without code changes.
    EXTRACTION_PROMPT_FILE: str | None = None
    # CORS: comma-separated list of allowed origins (e.g. "http://localhost:3000,https://app.example.com"). Empty = same-origin only.
    CORS_ORIGINS: str = ""


settings = Settings()
