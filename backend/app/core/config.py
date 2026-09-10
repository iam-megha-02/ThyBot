from pathlib import Path
from pydantic_settings import BaseSettings

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"  # core/config.py -> up to project root

class Settings(BaseSettings):
    groq_api_key: str = ""

    class Config:
        env_file = ENV_PATH

settings = Settings()