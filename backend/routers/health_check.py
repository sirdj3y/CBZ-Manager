from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Tome, Series
from ..config import settings

router = APIRouter(prefix="/api/health-check", tags=["health-check"], dependencies=[Depends(auth_required)])


@router.get("")
async def run_health_check(db: AsyncSession = Depends(get_db)):
    tomes = (await db.execute(select(Tome))).scalars().all()
    series_rows = (await db.execute(select(Series.id, Series.name))).all()
    series_map: dict[int, str] = {r.id: r.name for r in series_rows}
    series_ids = set(series_map.keys())
    cover_dir = Path(settings.COVER_CACHE_DIR)

    issues = []
    hash_map: dict[str, list] = {}

    KNOWN_FORMATS = {"cbz", "cbr", "pdf"}

    for tome in tomes:
        p = Path(tome.filepath)
        series_title = series_map.get(tome.series_id, "")

        # Fichier introuvable
        if not p.exists():
            issues.append({
                "type": "missing_file",
                "severity": "error",
                "label": "Fichier introuvable",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": tome.filepath,
            })
            continue  # Les autres checks nécessitent le fichier

        # Format non reconnu
        if tome.file_format not in KNOWN_FORMATS:
            issues.append({
                "type": "unknown_format",
                "severity": "error",
                "label": "Format non reconnu",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": f"Format : {tome.file_format}",
            })

        # Sans pages
        if not tome.page_count:
            issues.append({
                "type": "no_pages",
                "severity": "warning",
                "label": "Aucune page",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": "page_count = 0 ou non renseigné",
            })

        # Sans métadonnées
        if not tome.has_metadata:
            issues.append({
                "type": "no_metadata",
                "severity": "info",
                "label": "Sans métadonnées",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": None,
            })

        # Cover manquante (uniquement si marquée comme cachée)
        if tome.cover_cached:
            cover_path = cover_dir / f"{tome.id}.jpg"
            if not cover_path.exists():
                issues.append({
                    "type": "missing_cover",
                    "severity": "info",
                    "label": "Cover manquante",
                    "tome_id": tome.id,
                    "tome_title": tome.title or tome.filename,
                    "series_id": tome.series_id,
                    "series_title": series_title,
                    "file_format": tome.file_format,
                    "detail": str(cover_path),
                })

        # Tome orphelin
        if tome.series_id not in series_ids:
            issues.append({
                "type": "orphan",
                "severity": "error",
                "label": "Tome orphelin",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": "",
                "file_format": tome.file_format,
                "detail": f"series_id={tome.series_id} introuvable",
            })

        # Clé de doublon : taille + nom de fichier (rapide, sans lecture du contenu)
        key = f"{p.stat().st_size}:{p.name}"
        hash_map.setdefault(key, []).append(tome)

    # Doublons détectés par taille+nom identiques
    for key, dupes in hash_map.items():
        if len(dupes) > 1:
            for tome in dupes:
                issues.append({
                    "type": "duplicate",
                    "severity": "warning",
                    "label": "Doublon probable",
                    "tome_id": tome.id,
                    "tome_title": tome.title or tome.filename,
                    "series_id": tome.series_id,
                    "series_title": series_map.get(tome.series_id, ""),
                    "file_format": tome.file_format,
                    "detail": f"Même nom et taille que {len(dupes) - 1} autre(s) fichier(s)",
                })

    summary = {
        "error": sum(1 for i in issues if i["severity"] == "error"),
        "warning": sum(1 for i in issues if i["severity"] == "warning"),
        "info": sum(1 for i in issues if i["severity"] == "info"),
        "total": len(issues),
    }

    return {"summary": summary, "issues": issues}


@router.delete("/tome/{tome_id}")
async def delete_orphan_tome(tome_id: int, db: AsyncSession = Depends(get_db)):
    """Supprime uniquement l'entrée DB (pas le fichier disque)."""
    tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
    if tome is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tome introuvable")
    await db.delete(tome)
    await db.commit()
    return {"ok": True}
