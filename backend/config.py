from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MEDIA_ROOT: str = "/media"
    LIBRARY_SUBDIR: str = ""
    DB_PATH: str = "/data/cbzmanager.db"
    COVER_CACHE_DIR: str = "/data/covers"
    GOOGLE_BOOKS_API_KEY: str = ""
    COMICVINE_API_KEY: str = ""
    DEV_MODE: bool = False
    PORT: int = 32123

    @property
    def LIBRARY_PATH(self) -> str:
        if self.LIBRARY_SUBDIR:
            return str(Path(self.MEDIA_ROOT) / self.LIBRARY_SUBDIR.strip("/"))
        return self.MEDIA_ROOT

    def ensure_dirs(self):
        Path(self.COVER_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
