import logging
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.db_models import Tome, Series

logger = logging.getLogger(__name__)


async def delete_tome_and_cleanup(db: AsyncSession, tome: Tome) -> dict:
    """Supprime le fichier sur disque, le cache cover, l'entrée DB, et la série si elle
    devient vide (sinon recalcule son tome_count). Réutilisé par la suppression manuelle
    d'un album (routers/tomes.py) et par le nettoyage d'un import annulé (routers/import_router.py)."""
    series_id = tome.series_id
    tome_id = tome.id

    try:
        Path(tome.filepath).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Could not delete file {tome.filepath}: {e}")

    cover_dir = Path(settings.COVER_CACHE_DIR)
    for f in [cover_dir / f"{tome_id}.jpg", cover_dir / f"{tome_id}_thumb.jpg"]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    tome_name = tome.title or tome.filename
    await db.delete(tome)
    await db.commit()

    remaining = (await db.execute(select(func.count()).select_from(Tome).where(Tome.series_id == series_id))).scalar()
    series_deleted = False
    series_name = None
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if series:
        if not remaining:
            series_name = series.name
            try:
                folder = Path(series.folder_path)
                if folder.exists() and not any(folder.iterdir()):
                    folder.rmdir()
            except Exception as e:
                logger.warning(f"Could not delete folder {series.folder_path}: {e}")
            await db.delete(series)
            await db.commit()
            series_deleted = True
        else:
            series.tome_count = remaining
            await db.commit()

    return {
        "series_deleted": series_deleted,
        "tome_name": tome_name,
        "series_id": series_id,
        "series_name": series_name,
    }
