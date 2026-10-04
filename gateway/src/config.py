from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, Field

DEFAULT_DATA_DIR = Path(
    os.getenv(
        "CUSTOM_DATA_PATH",
        r"D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data"
        if Path(r"D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data").exists()
        else str(Path(__file__).resolve().parents[2] / "data"),
    )
)


class Settings(BaseModel):
    """Configuration settings for Wilco AI Gateway application."""
    GEMINI_API_KEY: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    CUSTOM_DATA_PATH: str = Field(default_factory=lambda: str(DEFAULT_DATA_DIR))
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    MODEL_NAME: str = Field(default_factory=lambda: os.getenv("MODEL_NAME", "gemini-2.0-flash-exp"))
    DEFAULT_ICAO: str = Field(default_factory=lambda: os.getenv("DEFAULT_ICAO", "WAHI"))

    # Property aliases for lowercase compatibility
    @property
    def gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY

    @property
    def custom_data_path(self) -> str:
        return self.CUSTOM_DATA_PATH

    @property
    def host(self) -> str:
        return self.HOST

    @property
    def port(self) -> int:
        return self.PORT

    @property
    def model_name(self) -> str:
        return self.MODEL_NAME

    @property
    def default_icao(self) -> str:
        return self.DEFAULT_ICAO


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
