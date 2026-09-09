from pathlib import Path
from pydantic_settings import BaseSettings

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"  # core/config.py -> up to backend/

class Settings(BaseSettings):
    app_name: str = "ThyroidCare"
    app_version: str = "0.1.0"
    groq_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8501"]

    class Config:
        env_file = ENV_PATH

settings = Settings()