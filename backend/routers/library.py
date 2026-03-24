import asyncio
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Series, Tome, ScanJob, Metadata
from ..models.schemas import SeriesOut, SeriesDetailOut, TomeOut, ScanStartOut, ScanStatusOut
from ..services.scanner import create_scan_job, scan_library, get_running_scan
from ..config import settings

router = APIRouter(prefix="/api", tags=["library"], dependencies=[Depends(auth_required)])

# In-memory scan progress store {job_id: {processed, total, status}}
_scan_progress: dict[int, dict] = {}


def _cover_url(tome_id: int, cached: bool, updated_at=None) -> str:
    if updated_at is not None:
        v = int(updated_at.timestamp()) if hasattr(updated_at, "timestamp") else str(updated_at).replace(" ", "")
        return f"/api/covers/{tome_id}?v={v}"
    return f"/api/covers/{tome_id}"


@router.get("/series", response_model=list[SeriesOut])
async def list_series(show_hidden: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(Series).order_by(Series.name)
    if not show_hidden:
        q = q.where(Series.hidden == False)
    result = await db.execute(q)
    series_list = result.scalars().all()
    if not series_list:
        return []

    # Agrégation des métadonnées par série en une seule requête
    series_ids = [s.id for s in series_list]
    meta_rows = (await db.execute(
        select(Tome.series_id, Tome.has_metadata, Metadata.Writer, Metadata.Penciller, Metadata.Publisher, Metadata.Tags)  # type: ignore[attr-defined]
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.series_id.in_(series_ids))
    )).all() if series_ids else []

    # Couverture par série (premier tome)
    cover_rows = (await db.execute(
        select(Tome.series_id, Tome.id, Tome.cover_cached, Tome.updated_at)
        .where(Tome.series_id.in_(series_ids))
        .order_by(Tome.series_id, Tome.number)
    )).all() if series_ids else []
    # Build default cover map (first tome per series)
    cover_map: dict[int, str] = {}
    for series_id, tid, cached, updated in cover_rows:
        if series_id not in cover_map:
            cover_map[series_id] = _cover_url(tid, cached, updated)
    # Override with custom cover_tome_id when set
    for s in series_list:
        if s.cover_tome_id:
            cover_map[s.id] = _cover_url(s.cover_tome_id, True)

    # Agrégation
    from collections import defaultdict
    agg: dict[int, dict] = defaultdict(lambda: {
        "writers": set(), "pencillers": set(), "publishers": set(),
        "tags": set(), "has_no_meta": False,
    })
    for series_id, has_meta, writer, penciller, publisher, tags in meta_rows:
        a = agg[series_id]
        if not has_meta:
            a["has_no_meta"] = True
        if writer:
            a["writers"].add(writer)
        if penciller:
            a["pencillers"].add(penciller)
        if publisher:
            a["publishers"].add(publisher)
        if tags:
            for tag in tags.split(","):
                t = tag.strip()
                if t:
                    a["tags"].add(t)

    out = []
    for s in series_list:
        a = agg[s.id]
        out.append(SeriesOut(
            id=s.id,
            name=s.name,
            tome_count=s.tome_count,
            cover_url=cover_map.get(s.id),
            hidden=s.hidden,
            created_at=s.created_at,
            updated_at=s.updated_at,
            writers=sorted(a["writers"]),
            pencillers=sorted(a["pencillers"]),
            publishers=sorted(a["publishers"]),
            tags=sorted(a["tags"]),
            has_tomes_without_meta=a["has_no_meta"],
        ))
    return out


@router.get("/library/authors")
async def list_authors(db: AsyncSession = Depends(get_db)):
    """Retourne writers/pencillers/publishers avec nb de tomes et séries."""
    rows = (await db.execute(
        select(Metadata.Writer, Metadata.Penciller, Metadata.Publisher, Tome.series_id)
        .join(Tome, Tome.id == Metadata.tome_id)
        .where(Metadata.Writer.isnot(None) | Metadata.Penciller.isnot(None) | Metadata.Publisher.isnot(None))
    )).all()

    def norm(s): return s.strip()

    # {name: {tomes: set(tome_id via row index), series: set(series_id)}}
    from collections import defaultdict
    authors:    dict[str, dict] = defaultdict(lambda: {"tomes": 0, "series": set()})
    publishers: dict[str, dict] = defaultdict(lambda: {"tomes": 0, "series": set()})

    for writer, penciller, publisher, series_id in rows:
        for field in [writer, penciller]:
            if field:
                for v in field.split(","):
                    v = norm(v)
                    if v:
                        authors[v]["tomes"] += 1
                        authors[v]["series"].add(series_id)
        if publisher:
            for v in publisher.split(","):
                v = norm(v)
                if v:
                    publishers[v]["tomes"] += 1
                    publishers[v]["series"].add(series_id)

    def fmt(d: dict) -> list:
        return sorted([
            {"name": k, "tomes": v["tomes"], "series": len(v["series"])}
            for k, v in d.items()
        ], key=lambda x: x["name"].lower())

    return {
        "authors":    fmt(authors),
        "publishers": fmt(publishers),
    }


@router.patch("/series/{series_id}/hidden", response_model=SeriesOut)
async def toggle_series_hidden(series_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    series.hidden = not series.hidden
    await db.commit()
    await db.refresh(series)
    from ..services.activity import log as activity_log
    action = "Série masquée" if series.hidden else "Série affichée"
    await activity_log(db, "edit_metadata", f"{action} : « {series.name} »")
    await db.commit()
    # Get cover url
    first_tome = await db.execute(
        select(Tome).where(Tome.series_id == series.id).order_by(Tome.number).limit(1)
    )
    ft = first_tome.scalar_one_or_none()
    return SeriesOut(
        id=series.id,
        name=series.name,
        tome_count=series.tome_count,
        cover_url=_cover_url(ft.id, ft.cover_cached, ft.updated_at) if ft else None,
        hidden=series.hidden,
        updated_at=series.updated_at,
    )


class SetCoverIn(BaseModel):
    tome_id: int | None = None  # None = reset to first tome


@router.patch("/series/{series_id}/cover")
async def set_series_cover(series_id: int, body: SetCoverIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    if body.tome_id is not None:
        # Validate that the tome belongs to this series
        tome_res = await db.execute(select(Tome).where(Tome.id == body.tome_id, Tome.series_id == series_id))
        if tome_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Tome introuvable dans cette série")

    series.cover_tome_id = body.tome_id
    await db.commit()
    from ..services.activity import log as activity_log
    cover_msg = f"Cover personnalisée : tome #{body.tome_id}" if body.tome_id else "Cover réinitialisée (auto)"
    await activity_log(db, "edit_metadata", f"Série « {series.name} » — {cover_msg}")
    await db.commit()

    # Return the new cover url
    if body.tome_id is not None:
        cover_url = _cover_url(body.tome_id, True)
    else:
        first = (await db.execute(
            select(Tome).where(Tome.series_id == series_id).order_by(Tome.number).limit(1)
        )).scalar_one_or_none()
        cover_url = _cover_url(first.id, first.cover_cached, first.updated_at) if first else None

    return {"cover_url": cover_url, "cover_tome_id": body.tome_id}


@router.get("/series/{series_id}", response_model=SeriesDetailOut)
async def get_series(series_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Series).where(Series.id == series_id)
    )
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    tomes_result = await db.execute(
        select(Tome)
        .where(Tome.series_id == series_id)
        .order_by(Tome.number)
    )
    tomes = tomes_result.scalars().all()

    # Use custom cover tome if set, otherwise first tome
    cover_tome = None
    if series.cover_tome_id:
        cover_tome = next((t for t in tomes if t.id == series.cover_tome_id), None)
    if cover_tome is None:
        cover_tome = tomes[0] if tomes else None
    cover_url = _cover_url(cover_tome.id, cover_tome.cover_cached, cover_tome.updated_at) if cover_tome else None

    tomes_out = [
        TomeOut(
            id=t.id,
            series_id=t.series_id,
            filename=t.filename,
            number=t.number,
            title=t.title,
            file_format=t.file_format,
            file_size=t.file_size,
            page_count=t.page_count,
            has_metadata=t.has_metadata,
            cover_cached=t.cover_cached,
            cover_url=_cover_url(t.id, t.cover_cached, t.updated_at),
            status=t.status,
        )
        for t in tomes
    ]

    return SeriesDetailOut(
        id=series.id,
        name=series.name,
        tome_count=series.tome_count,
        cover_url=cover_url,
        cover_tome_id=series.cover_tome_id,
        hidden=series.hidden,
        tomes=tomes_out,
    )


@router.put("/series/{series_id}/metadata")
async def update_series_metadata(series_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    from ..models.db_models import Metadata
    from ..services.metadata_writer import write_metadata
    from ..services.activity import log as activity_log

    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    tomes_result = await db.execute(select(Tome).where(Tome.series_id == series_id))
    tomes = tomes_result.scalars().all()

    errors = 0
    for tome in tomes:
        if tome.file_format != "cbz":
            continue
        try:
            await write_metadata(tome.filepath, body)
            meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
            meta = meta_result.scalar_one_or_none()
            if meta is None:
                meta = Metadata(tome_id=tome.id)
                db.add(meta)
            for key, val in body.items():
                if hasattr(meta, key):
                    setattr(meta, key, val)
            tome.has_metadata = True
            tome.updated_at = datetime.utcnow()
        except Exception:
            errors += 1

    if "Series" in body and body["Series"]:
        series.name = body["Series"]

    await db.commit()

    cbz_count = sum(1 for t in tomes if t.file_format == "cbz")
    msg = f"Métadonnées éditées : série « {series.name} » ({cbz_count} album(s))"
    if errors:
        msg += f", {errors} erreur(s)"
    await activity_log(db, "edit_metadata", msg, status="ok" if not errors else "error")
    await db.commit()

    return {"ok": cbz_count - errors, "errors": errors}


@router.delete("/series/{series_id}", status_code=200)
async def delete_series(series_id: int, db: AsyncSession = Depends(get_db)):
    """Supprime la série : tous les fichiers sur disque, le dossier si vide, et les entrées DB."""
    import logging, shutil
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    # Récupérer tous les tomes pour supprimer les fichiers et covers
    tomes = (await db.execute(select(Tome).where(Tome.series_id == series_id))).scalars().all()
    cover_dir = Path(settings.COVER_CACHE_DIR)

    for tome in tomes:
        # Fichier du tome
        try:
            Path(tome.filepath).unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"Could not delete file {tome.filepath}: {e}")
        # Cache cover
        for f in [cover_dir / f"{tome.id}.jpg", cover_dir / f"{tome.id}_thumb.jpg"]:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    # Supprimer le dossier de la série si vide
    try:
        folder = Path(series.folder_path)
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    except Exception as e:
        logging.warning(f"Could not delete folder {series.folder_path}: {e}")

    # Supprimer la série (cascade supprime les tomes et leurs métadonnées)
    series_name = series.name
    await db.delete(series)
    await db.commit()
    from ..services.activity import log as activity_log
    await activity_log(db, "delete_series", f"Série supprimée : « {series_name} » ({len(tomes)} album(s))")
    await db.commit()
    return {"deleted": True}


@router.get("/scan/last")
async def last_scan(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanJob).order_by(ScanJob.id.desc()).limit(1))
    job = result.scalar_one_or_none()
    if job is None:
        return {"status": "never", "finished_at": None, "processed": 0, "total": 0}
    return {
        "status": job.status,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "processed": job.processed,
        "total": job.total,
        "error_msg": job.error_msg,
    }


@router.post("/scan", response_model=ScanStartOut)
async def start_scan(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Return existing running job if any
    running = await get_running_scan(db)
    if running:
        return ScanStartOut(job_id=running.id)

    job = await create_scan_job(db)
    _scan_progress[job.id] = {"processed": 0, "total": 0, "status": "pending"}

    def progress_cb(processed: int, total: int):
        _scan_progress[job.id] = {"processed": processed, "total": total, "status": "running"}

    async def run_scan():
        import logging
        from ..database import AsyncSessionLocal
        from ..services.activity import log as activity_log
        async with AsyncSessionLocal() as scan_db:
            try:
                await scan_library(settings.LIBRARY_PATH, scan_db, job.id, progress_cb)
                _scan_progress[job.id]["status"] = "done"
                p = _scan_progress[job.id]
                await activity_log(scan_db, "scan", f"Scan terminé — {p.get('processed', 0)} fichiers traités")
            except Exception as e:
                _scan_progress[job.id]["status"] = "error"
                await activity_log(scan_db, "scan", f"Scan échoué : {e}", status="error")
            await scan_db.commit()

    background_tasks.add_task(run_scan)
    return ScanStartOut(job_id=job.id)


@router.get("/scan/{job_id}", response_model=ScanStatusOut)
async def scan_status(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanJob).where(ScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return ScanStatusOut(
        job_id=job.id,
        status=job.status,
        processed=job.processed,
        total=job.total,
        error_msg=job.error_msg,
    )


@router.get("/scan/{job_id}/stream")
async def scan_stream(job_id: int, _=Depends(auth_required)):
    async def event_gen():
        while True:
            data = _scan_progress.get(job_id, {"processed": 0, "total": 0, "status": "unknown"})
            yield f"data: {json.dumps(data)}\n\n"
            if data["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
