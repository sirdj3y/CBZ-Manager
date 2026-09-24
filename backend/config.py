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
    # Vide = pas de renommage automatique à l'import
    RENAME_PATTERN: str = "{Série} - T{Numéro} - {Titre}"
    # IP/CIDR de confiance pour X-Forwarded-For/-Proto (voir routers/auth.py) — loopback par
    # défaut (le proxy tourne sur le même hôte, cas le plus courant : reverse proxy intégré
    # Synology, ou Traefik/nginx dans le même réseau réseau `network_mode: host`). À élargir
    # explicitement (ex. "127.0.0.1,::1,172.20.0.5") si le proxy tourne ailleurs (autre
    # conteneur/VM) — jamais tout un LAN entier par défaut, un autre appareil du même réseau
    # pourrait sinon usurper ces en-têtes tout autant qu'un vrai reverse proxy.
    TRUSTED_PROXY_IPS: str = "127.0.0.1,::1"

    @property
    def LIBRARY_PATH(self) -> str:
        if self.LIBRARY_SUBDIR:
            return str(Path(self.MEDIA_ROOT) / self.LIBRARY_SUBDIR.strip("/"))
        return self.MEDIA_ROOT

    def ensure_dirs(self):
        Path(self.COVER_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.DB_PATH).parent.mkdir(parents=True, exist_ok=True)


_PERSISTED_KEYS = ("LIBRARY_SUBDIR", "GOOGLE_BOOKS_API_KEY", "COMICVINE_API_KEY", "RENAME_PATTERN")


@lru_cache
def get_settings() -> Settings:
    s = Settings()

    # /data/.env holds settings persisted at runtime from the UI (Settings page — see
    # routers/settings.py:_rewrite_env). It must win over plain OS env vars, since Docker
    # Compose's `env_file: .env` injects the *host* .env as real environment variables,
    # which pydantic-settings otherwise prioritizes over any env_file it reads itself.
    persisted = Path("/data/.env")
    if persisted.is_file():
        from dotenv import dotenv_values
        overrides = dotenv_values(persisted)
        for key in _PERSISTED_KEYS:
            if overrides.get(key) is not None:
                setattr(s, key, overrides[key])

    return s


settings = get_settings()
