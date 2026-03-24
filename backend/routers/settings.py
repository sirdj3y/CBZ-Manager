import re
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sql_update

from ..dependencies import auth_required
from ..models.schemas import SettingsOut, SettingsIn
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(auth_required)])


def _rewrite_env(key: str, value: str) -> None:
    env_path = Path(".env")
    content = env_path.read_text() if env_path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(content)


@router.get("/browse")
async def browse_folders(path: str = ""):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    target = (media_root / path).resolve() if path else media_root
    if not str(target).startswith(str(media_root)):
        raise HTTPException(status_code=403, detail="Accès refusé : chemin hors de MEDIA_ROOT")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Dossier introuvable : {path}")
    folders = sorted(
        [
            {
                "name": item.name,
                "path": str(item.relative_to(media_root)),
                "has_children": any(child.is_dir() for child in item.iterdir()),
            }
            for item in target.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ],
        key=lambda f: f["name"].lower(),
    )
    return {
        "current_path": str(target.relative_to(media_root)) if target != media_root else "",
        "parent_path": str(target.parent.relative_to(media_root)) if target != media_root else None,
        "media_root_name": media_root.name,
        "folders": folders,
    }


@router.get("/about")
async def about():
    from ..config import settings as cfg
    cover_dir = Path(cfg.COVER_CACHE_DIR)
    cover_size = sum(f.stat().st_size for f in cover_dir.rglob("*") if f.is_file()) if cover_dir.exists() else 0
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "0.0.0"
    return {
        "version": version,
        "cover_cache_size": cover_size,
    }


@router.delete("/reset-db")
async def reset_database(db: AsyncSession = Depends(get_db)):
    from ..services.activity import log as activity_log
    await activity_log(db, "delete_series", "Base de données réinitialisée (toutes les données supprimées)", status="ok")
    await db.commit()

    db_path = Path(settings.DB_PATH)
    cover_dir = Path(settings.COVER_CACHE_DIR)

    if db_path.exists():
        db_path.unlink()

    if cover_dir.exists():
        shutil.rmtree(cover_dir)
    cover_dir.mkdir(parents=True, exist_ok=True)

    return {"ok": True}


@router.get("", response_model=SettingsOut)
async def get_current_settings():
    return SettingsOut(
        library_subdir=settings.LIBRARY_SUBDIR,
        media_root_name=Path(settings.MEDIA_ROOT).name,
        google_books_configured=bool(settings.GOOGLE_BOOKS_API_KEY),
        comicvine_configured=bool(settings.COMICVINE_API_KEY),
    )


@router.put("", response_model=SettingsOut)
async def update_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    if body.library_subdir is not None:
        subdir = body.library_subdir.strip().strip("/")
        if subdir:
            p = Path(settings.MEDIA_ROOT) / subdir
            if not p.exists() or not p.is_dir():
                raise HTTPException(status_code=400, detail=f"Sous-dossier introuvable : {subdir}")
        if subdir != settings.LIBRARY_SUBDIR:
            # Vider le cache covers quand le dossier change
            cover_dir = Path(settings.COVER_CACHE_DIR)
            if cover_dir.exists():
                for f in cover_dir.glob("*.jpg"):
                    f.unlink(missing_ok=True)
            # Reset cover_cached flag in DB so covers get regenerated
            from ..models.db_models import Tome
            await db.execute(sql_update(Tome).values(cover_cached=False))
            await db.commit()
        _rewrite_env("LIBRARY_SUBDIR", subdir)
        settings.LIBRARY_SUBDIR = subdir

    if body.google_books_api_key is not None:
        _rewrite_env("GOOGLE_BOOKS_API_KEY", body.google_books_api_key)
        settings.GOOGLE_BOOKS_API_KEY = body.google_books_api_key

    if body.comicvine_api_key is not None:
        _rewrite_env("COMICVINE_API_KEY", body.comicvine_api_key)
        settings.COMICVINE_API_KEY = body.comicvine_api_key

    return SettingsOut(
        library_subdir=settings.LIBRARY_SUBDIR,
        google_books_configured=bool(settings.GOOGLE_BOOKS_API_KEY),
        comicvine_configured=bool(settings.COMICVINE_API_KEY),
    )
