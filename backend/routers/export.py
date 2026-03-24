import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Tome, Metadata, ReadingProgress

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(auth_required)])

METADATA_FIELDS = [
    "Title", "Series", "Number", "Volume", "AlternateSeries", "AlternateNumber",
    "StoryArc", "SeriesGroup", "Publisher", "Year", "Month", "Day", "LanguageISO",
    "Format", "Web", "Writer", "Penciller", "Inker", "Colorist", "Letterer",
    "CoverArtist", "Editor", "Translator", "Genre", "Tags", "AgeRating",
    "Characters", "Teams", "Locations", "Summary", "Notes", "PageCount",
    "BlackAndWhite", "Manga", "ScanInformation", "GTIN", "ISBN",
]


async def _build_export(db: AsyncSession) -> dict:
    result = await db.execute(
        select(Tome)
        .options(
            selectinload(Tome.series),
            selectinload(Tome.metadata_),
            selectinload(Tome.reading_progress),
        )
        .order_by(Tome.series_id, Tome.number)
    )
    tomes = result.scalars().all()

    entries = []
    for t in tomes:
        m = t.metadata_
        rp = t.reading_progress
        entry = {
            "filepath": t.filepath,
            "filename": t.filename,
            "serie": t.series.name if t.series else "",
            "numero": t.number,
            "titre": t.title,
            "format": t.file_format,
            "taille_octets": t.file_size,
            "pages": t.page_count,
            # Annotations utilisateur
            "user_rating": t.user_rating,
            "user_notes": t.user_notes,
            "user_tag_list": t.user_tag_list,
            # Progression de lecture
            "last_page": rp.last_page if rp else None,
            # Métadonnées ComicInfo.xml
            "metadata": {field: getattr(m, field, None) for field in METADATA_FIELDS} if m else {},
        }
        entries.append(entry)

    return {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(),
        "tome_count": len(entries),
        "tomes": entries,
    }


@router.get("")
async def export_library(db: AsyncSession = Depends(get_db)):
    data = await _build_export(db)
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=cbzmanager-backup.json"},
    )


@router.post("/import")
async def import_library(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    raw = await file.read()
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier JSON invalide")

    if not isinstance(data, dict) or "tomes" not in data:
        raise HTTPException(status_code=400, detail="Format de fichier non reconnu")

    entries = data["tomes"]
    updated = 0
    not_found = 0

    for entry in entries:
        filepath = entry.get("filepath")
        filename = entry.get("filename")

        # Cherche d'abord par filepath, puis par filename
        tome = None
        if filepath:
            result = await db.execute(select(Tome).where(Tome.filepath == filepath).options(
                selectinload(Tome.metadata_), selectinload(Tome.reading_progress)
            ))
            tome = result.scalar_one_or_none()

        if tome is None and filename:
            result = await db.execute(select(Tome).where(Tome.filename == filename).options(
                selectinload(Tome.metadata_), selectinload(Tome.reading_progress)
            ))
            tome = result.scalar_one_or_none()

        if tome is None:
            not_found += 1
            continue

        # Restaure annotations utilisateur
        if entry.get("user_rating") is not None:
            tome.user_rating = entry["user_rating"]
        if entry.get("user_notes") is not None:
            tome.user_notes = entry["user_notes"]
        if entry.get("user_tag_list") is not None:
            tome.user_tag_list = entry["user_tag_list"]

        # Restaure progression de lecture
        if entry.get("last_page") is not None:
            if tome.reading_progress:
                tome.reading_progress.last_page = entry["last_page"]
            else:
                db.add(ReadingProgress(tome_id=tome.id, last_page=entry["last_page"]))

        # Restaure métadonnées ComicInfo.xml
        meta_data = entry.get("metadata") or {}
        if any(v for v in meta_data.values()):
            if tome.metadata_ is None:
                meta = Metadata(tome_id=tome.id)
                db.add(meta)
                await db.flush()
                tome.metadata_ = meta
            for field in METADATA_FIELDS:
                val = meta_data.get(field)
                if val is not None:
                    setattr(tome.metadata_, field, val)
            tome.has_metadata = True

        updated += 1

    await db.commit()

    return {
        "updated": updated,
        "not_found": not_found,
        "total": len(entries),
    }
