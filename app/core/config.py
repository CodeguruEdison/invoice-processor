from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
   model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
   APP_NAME:str = "Invoice Processor"
   APP_VERSION:str = "0.1.0"
   DEBUG:bool = True
   DATABASE_URL:str = "postgresql://postgres:postgres@localhost:5432/invoice_db"
   REDIS_URL:str = "redis://localhost:6379/0"
  

settings = Settings()