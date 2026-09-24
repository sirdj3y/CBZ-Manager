from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Series, MissingAlbum, MissingAlbumsScanJob, IgnoredMissingAlbum, User
from .auth import get_client_ip
from ..models.schemas import (
    MissingAlbumOut, NotFoundSeriesOut, MissingAlbumsScanStartOut, MissingAlbumsScanStatusOut,
    TrackedSeriesOut, TrackToggleIn, MissingAlbumsCountOut, IgnoredAlbumOut, BedethequeUrlIn, BedethequeStatusIn,
)
from ..services.missing_albums import scan_all, scan_series
from ..services.scraper_bedetheque import is_bedetheque_url

router = APIRouter(prefix="/api/missing-albums", tags=["missing-albums"], dependencies=[Depends(require_permission("library.missing_albums"))])

_scan_progress: dict[int, dict] = {}


async def _get_running_job(db: AsyncSession) -> MissingAlbumsScanJob | None:
    result = await db.execute(
        select(MissingAlbumsScanJob).where(MissingAlbumsScanJob.status.in_(("pending", "running"))).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("", response_model=dict)
async def list_missing_albums(db: AsyncSession = Depends(get_db)):
    # Exclure les séries dont le suivi est désactivé — sans ce filtre, des albums manquants
    # détectés avant l'exclusion (ou par tout autre biais) restaient affichés indéfiniment,
    # contrairement à la liste "séries non trouvées" juste en dessous qui filtrait déjà bien.
    result = await db.execute(
        select(MissingAlbum, Series.name)
        .join(Series, Series.id == MissingAlbum.series_id)
        .where(Series.track_new_albums.is_(True))
        .order_by(Series.name)
    )
    # Tri numérique du numéro de tome en Python — colonne texte, un ORDER BY SQL trierait
    # lexicographiquement ("1", "10", "11"… "2") plutôt que "1", "2", "3"…
    rows = sorted(result.all(), key=lambda row: (row.name, int(row.MissingAlbum.number)))
    missing = [
        MissingAlbumOut(
            id=row.MissingAlbum.id,
            series_id=row.MissingAlbum.series_id,
            series_name=row.name,
            number=row.MissingAlbum.number,
            title=row.MissingAlbum.title,
            cover_url=row.MissingAlbum.cover_url,
            year=row.MissingAlbum.year,
            bedetheque_url=row.MissingAlbum.bedetheque_url,
            detected_at=row.MissingAlbum.detected_at,
            writer=row.MissingAlbum.writer,
            penciller=row.MissingAlbum.penciller,
            publisher=row.MissingAlbum.publisher,
        )
        for row in rows
    ]

    not_found_result = await db.execute(
        select(Series)
        .where(Series.track_new_albums.is_(True), Series.bedetheque_match_status == "not_found")
        .order_by(Series.name)
    )
    not_found = [NotFoundSeriesOut(id=s.id, name=s.name) for s in not_found_result.scalars().all()]

    return {"missing": missing, "not_found": not_found}


@router.get("/count", response_model=MissingAlbumsCountOut)
async def missing_albums_count(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count(MissingAlbum.id))
        .join(Series, Series.id == MissingAlbum.series_id)
        .where(Series.track_new_albums.is_(True))
    )
    return MissingAlbumsCountOut(count=result.scalar_one())


@router.post("/{missing_album_id}/ignore")
async def ignore_missing_album(missing_album_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MissingAlbum).where(MissingAlbum.id == missing_album_id))
    album = result.scalar_one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="Album introuvable")

    existing = await db.execute(
        select(IgnoredMissingAlbum).where(
            IgnoredMissingAlbum.series_id == album.series_id,
            IgnoredMissingAlbum.number == album.number,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(IgnoredMissingAlbum(series_id=album.series_id, number=album.number, title=album.title))
    await db.execute(delete(MissingAlbum).where(MissingAlbum.id == missing_album_id))
    await db.commit()
    return {"ok": True}


@router.post("/{missing_album_id}/fulfilled")
async def fulfill_missing_album(missing_album_id: int, db: AsyncSession = Depends(get_db)):
    """Supprime directement cette entrée, sans passer par 'ignoré' (voir /ignore) — utilisé
    juste après l'upload d'un fichier pour cet album précis (voir MissingAlbumUploadModal.vue),
    en garantie fiable et immédiate en plus de la revérification Bedetheque (best-effort,
    dépend du réseau — voir /series/{series_id}/recheck) : contrairement à celle-ci, ne
    dépend d'aucune requête externe et ne peut donc pas échouer silencieusement."""
    result = await db.execute(select(MissingAlbum).where(MissingAlbum.id == missing_album_id))
    album = result.scalar_one_or_none()
    if album is None:
        return {"ok": True}  # déjà supprimée (ex: recheck concurrent) — pas une erreur ici
    await db.execute(delete(MissingAlbum).where(MissingAlbum.id == missing_album_id))
    await db.commit()
    return {"ok": True}


@router.get("/ignored", response_model=list[IgnoredAlbumOut])
async def list_ignored_albums(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(IgnoredMissingAlbum, Series.name)
        .join(Series, Series.id == IgnoredMissingAlbum.series_id)
        .order_by(Series.name)
    )
    rows = sorted(result.all(), key=lambda row: (row.name, int(row.IgnoredMissingAlbum.number)))
    return [
        IgnoredAlbumOut(
            id=row.IgnoredMissingAlbum.id,
            series_id=row.IgnoredMissingAlbum.series_id,
            series_name=row.name,
            number=row.IgnoredMissingAlbum.number,
            title=row.IgnoredMissingAlbum.title,
        )
        for row in rows
    ]


@router.delete("/ignored/{ignored_id}")
async def unignore_album(ignored_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IgnoredMissingAlbum).where(IgnoredMissingAlbum.id == ignored_id))
    ignored = result.scalar_one_or_none()
    if ignored is None:
        raise HTTPException(status_code=404, detail="Introuvable")

    series_result = await db.execute(select(Series).where(Series.id == ignored.series_id))
    series = series_result.scalar_one_or_none()

    await db.execute(delete(IgnoredMissingAlbum).where(IgnoredMissingAlbum.id == ignored_id))
    await db.commit()

    if series is not None:
        # Revérifier tout de suite cette série, sinon l'album réaffiché reste invisible
        # jusqu'au prochain scan complet (même logique que la réactivation d'une série).
        try:
            await scan_series(db, series)
        except Exception:
            pass
    return {"ok": True}


@router.get("/series", response_model=list[TrackedSeriesOut])
async def list_tracked_series(db: AsyncSession = Depends(get_db)):
    counts_result = await db.execute(
        select(MissingAlbum.series_id, func.count(MissingAlbum.id)).group_by(MissingAlbum.series_id)
    )
    counts = dict(counts_result.all())

    result = await db.execute(select(Series).order_by(Series.name))
    return [
        TrackedSeriesOut(
            id=s.id,
            name=s.name,
            track_new_albums=s.track_new_albums,
            bedetheque_match_status=s.bedetheque_match_status,
            missing_count=counts.get(s.id, 0),
        )
        for s in result.scalars().all()
    ]


@router.put("/series/{series_id}/track")
async def toggle_series_tracking(series_id: int, body: TrackToggleIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    series.track_new_albums = body.track_new_albums
    if not body.track_new_albums:
        await db.execute(delete(MissingAlbum).where(MissingAlbum.series_id == series_id))
        await db.commit()
    else:
        # Réactivation : re-vérifier tout de suite cette série plutôt que d'attendre le
        # prochain scan complet, sinon ses albums manquants restent invisibles jusque-là.
        await db.commit()
        try:
            await scan_series(db, series)
        except Exception:
            pass
    return {"ok": True}


@router.put("/series/{series_id}/bedetheque-url")
async def set_series_bedetheque_url(
    series_id: int, body: BedethequeUrlIn, db: AsyncSession = Depends(get_db)
):
    """Corrige/saisit manuellement l'URL Bedetheque d'une série. Une fois définie, le scan
    ne tente plus jamais de la re-deviner par nom (voir _scan_one_series) — pour revenir à
    la détection automatique, il suffit d'envoyer une URL vide."""
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    url = (body.url or "").strip() or None
    if url and not is_bedetheque_url(url):
        raise HTTPException(status_code=400, detail="URL invalide (doit être une page bedetheque.com)")

    series.bedetheque_url = url
    series.bedetheque_match_status = "found" if url else None
    if not url:
        await db.execute(delete(MissingAlbum).where(MissingAlbum.series_id == series_id))
    await db.commit()
    await db.refresh(series)

    # Ré-analyse immédiate avec cette URL (sans le délai de courtoisie du scan en masse —
    # voir _scan_one_series(delay=...)) : une seule requête HTTP + parsing, la réponse reste
    # rapide et le client obtient directement l'état à jour (statut, albums manquants) sans
    # avoir à rafraîchir la page pour le voir apparaître.
    if url and series.track_new_albums:
        try:
            await scan_series(db, series)
        except Exception:
            pass

    return {
        "ok": True,
        "bedetheque_url": series.bedetheque_url,
        "bedetheque_match_status": series.bedetheque_match_status,
        "bedetheque_status": series.bedetheque_status,
    }


@router.put("/series/{series_id}/bedetheque-status")
async def set_series_bedetheque_status(series_id: int, body: BedethequeStatusIn, db: AsyncSession = Depends(get_db)):
    """Corrige/saisit manuellement le statut ("Série en cours"/"Série finie") — le scan le
    réécrit automatiquement à chaque analyse s'il trouve une valeur sur Bedetheque, cette
    correction manuelle peut donc être reprise au scan suivant si Bedetheque dit autre chose."""
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    status = (body.status or "").strip() or None
    if status and status not in ("Série en cours", "Série finie"):
        raise HTTPException(status_code=400, detail="Statut invalide")

    series.bedetheque_status = status
    await db.commit()
    return {"ok": True, "bedetheque_status": series.bedetheque_status}


@router.post("/series/{series_id}/recheck")
async def recheck_series(series_id: int, db: AsyncSession = Depends(get_db)):
    """Revérifie immédiatement une seule série — utilisé après l'ajout d'un album (upload
    depuis la page "Albums manquants") pour faire disparaître l'entrée correspondante sans
    attendre le prochain scan complet. Même logique que la réactivation du suivi/correction
    d'URL Bedetheque : scan_series() recalcule les albums manquants à partir des tomes
    réellement présents, l'entrée nouvellement possédée disparaît donc d'elle-même."""
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    try:
        await scan_series(db, series)
    except Exception:
        pass
    return {"ok": True}


@router.get("/scan/last", response_model=MissingAlbumsScanStatusOut)
async def last_scan(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MissingAlbumsScanJob).order_by(MissingAlbumsScanJob.id.desc()).limit(1))
    job = result.scalar_one_or_none()
    if job is None:
        return MissingAlbumsScanStatusOut(job_id=0, status="never", processed=0, total=0)
    return MissingAlbumsScanStatusOut(
        job_id=job.id, status=job.status, processed=job.processed, total=job.total,
        error_msg=job.error_msg, finished_at=job.finished_at,
    )


@router.get("/scan/{job_id}", response_model=MissingAlbumsScanStatusOut)
async def scan_status(job_id: int, db: AsyncSession = Depends(get_db)):
    progress = _scan_progress.get(job_id)
    if progress and progress["status"] in ("pending", "running"):
        return MissingAlbumsScanStatusOut(job_id=job_id, **progress)
    result = await db.execute(select(MissingAlbumsScanJob).where(MissingAlbumsScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return MissingAlbumsScanStatusOut(
        job_id=job.id, status=job.status, processed=job.processed, total=job.total,
        error_msg=job.error_msg, finished_at=job.finished_at,
    )


@router.post("/scan", response_model=MissingAlbumsScanStartOut)
async def start_scan(background_tasks: BackgroundTasks, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    running = await _get_running_job(db)
    if running:
        return MissingAlbumsScanStartOut(job_id=running.id)

    job = MissingAlbumsScanJob(status="pending", started_at=datetime.utcnow())
    db.add(job)
    await db.commit()
    await db.refresh(job)

    _scan_progress[job.id] = {"processed": 0, "total": 0, "status": "pending", "error_msg": None}
    scan_user_id, scan_ip = current_user.id, get_client_ip(request)

    def progress_cb(processed: int, total: int):
        _scan_progress[job.id] = {"processed": processed, "total": total, "status": "running", "error_msg": None}

    async def run_scan():
        from ..database import AsyncSessionLocal
        from ..services.activity import log as activity_log
        from ..models.db_models import User as _User
        async with AsyncSessionLocal() as scan_db:
            scan_user = await scan_db.get(_User, scan_user_id)
            try:
                await scan_all(scan_db, progress_cb)
                _scan_progress[job.id]["status"] = "done"
                p = _scan_progress[job.id]
                await scan_db.execute(
                    __import__("sqlalchemy").update(MissingAlbumsScanJob)
                    .where(MissingAlbumsScanJob.id == job.id)
                    .values(status="done", processed=p.get("processed", 0), total=p.get("total", 0), finished_at=datetime.utcnow())
                )
                await activity_log(scan_db, "scan", f"Recherche d'albums manquants terminée — {p.get('processed', 0)} série(s) analysée(s)", user=scan_user, ip=scan_ip)
            except Exception as e:
                _scan_progress[job.id]["status"] = "error"
                _scan_progress[job.id]["error_msg"] = str(e)
                await scan_db.execute(
                    __import__("sqlalchemy").update(MissingAlbumsScanJob)
                    .where(MissingAlbumsScanJob.id == job.id)
                    .values(status="error", error_msg=str(e), finished_at=datetime.utcnow())
                )
                await activity_log(scan_db, "scan", f"Recherche d'albums manquants échouée : {e}", status="error", user=scan_user, ip=scan_ip)
            await scan_db.commit()

    background_tasks.add_task(run_scan)
    return MissingAlbumsScanStartOut(job_id=job.id)
