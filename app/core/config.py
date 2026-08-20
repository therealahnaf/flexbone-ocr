import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OCR_",
        extra="ignore",
    )

    max_file_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=25_000_000, gt=0)
    cache_ttl_seconds: int = Field(default=600, gt=0)
    cache_max_entries: int = Field(default=256, gt=0)
    rate_limit_requests: int = Field(default=30, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    vision_timeout_seconds: float = Field(default=15.0, gt=0)
    batch_max_files: int = Field(default=5, ge=1, le=20)
    batch_concurrency: int = Field(default=3, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    configured_path = os.getenv("OCR_ENV_FILE")

    if configured_path:
        env_file = Path(configured_path)
        try:
            with env_file.open(encoding="utf-8") as file:
                file.read(1)
        except (OSError, UnicodeError):
            raise RuntimeError("Configured OCR settings file is unavailable.") from None

        try:
            return Settings(_env_file=env_file)
        except ValidationError:
            raise RuntimeError("Configured OCR settings are invalid.") from None

    try:
        return Settings()
    except ValidationError:
        raise RuntimeError("Configured OCR settings are invalid.") from None
