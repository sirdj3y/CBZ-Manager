import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import require_admin, require_permission
from ..models.db_models import DuplicateScanJob, Tome, Series, User
from ..models.schemas import DuplicateScanStartOut, DuplicateScanStatusOut
from ..config import settings
from ..services.storage_check import check_media_identity
from ..services.duplicates import scan_duplicates, get_duplicate_groups
from .auth import get_client_ip

# La suppression d'un tome orphelin (DELETE /tome/{id}) exige explicitement library.delete
# en plus, voir plus bas — sans quoi elle deviendrait accessible à n'importe qui ayant juste
# library.settings, en contradiction avec le fait que ce droit soit justement exclu du
# profil de test évoqué par l'utilisateur.
router = APIRouter(prefix="/api/health-check", tags=["health-check"], dependencies=[Depends(require_permission("library.settings"))])

# Réutilise le job de hashing déjà construit pour la détection de doublons (DuplicateScanJob,
# services/duplicates.py) — la page Diagnostic est maintenant le seul déclencheur de cette
# analyse, fusionnée avec le reste des vérifications de bibliothèque plutôt que sur sa propre
# page (l'app avait deux outils qui se recoupaient : cette page faisait déjà une détection de
# doublons faible, par taille+nom — remplacée ci-dessous par la vraie, par contenu).
_scan_progress: dict[int, dict] = {}


async def _get_running_job(db: AsyncSession) -> DuplicateScanJob | None:
    result = await db.execute(
        select(DuplicateScanJob).where(DuplicateScanJob.status.in_(("pending", "running"))).limit(1)
    )
    return result.scalar_one_or_none()


async def cleanup_stale_scan_jobs(db: AsyncSession) -> None:
    """Un job encore "pending"/"running" au démarrage n'a pas pu se terminer normalement — sa
    tâche de fond (in-memory, _scan_progress) tournait dans le process précédent et a été
    tuée avec lui (redémarrage/mise à jour du conteneur). Sans ce nettoyage, la page
    Diagnostic le signale "en cours" indéfiniment : plus aucun process ne le fera jamais
    progresser."""
    await db.execute(
        update(DuplicateScanJob)
        .where(DuplicateScanJob.status.in_(("pending", "running")))
        .values(status="error", error_msg="Analyse interrompue par un redémarrage du serveur", finished_at=datetime.utcnow())
    )
    await db.commit()


@router.get("/storage")
async def storage_identity_check():
    mismatch = check_media_identity()
    return {"ok": mismatch is None, "mismatch": mismatch}


@router.get("/scan/last", response_model=DuplicateScanStatusOut)
async def last_scan(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DuplicateScanJob).order_by(DuplicateScanJob.id.desc()).limit(1))
    job = result.scalar_one_or_none()
    if job is None:
        return DuplicateScanStatusOut(job_id=0, status="never", processed=0, total=0)
    return DuplicateScanStatusOut(
        job_id=job.id, status=job.status, processed=job.processed, total=job.total,
        error_msg=job.error_msg, finished_at=job.finished_at,
    )


@router.get("/scan/{job_id}", response_model=DuplicateScanStatusOut)
async def scan_status(job_id: int, db: AsyncSession = Depends(get_db)):
    progress = _scan_progress.get(job_id)
    if progress and progress["status"] in ("pending", "running"):
        return DuplicateScanStatusOut(job_id=job_id, **progress)
    result = await db.execute(select(DuplicateScanJob).where(DuplicateScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return DuplicateScanStatusOut(
        job_id=job.id, status=job.status, processed=job.processed, total=job.total,
        error_msg=job.error_msg, finished_at=job.finished_at,
    )


@router.post("/scan", response_model=DuplicateScanStartOut)
async def start_scan(background_tasks: BackgroundTasks, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("library.settings"))):
    """Partie lourde de l'analyse complète (lecture du contenu de chaque fichier pas encore
    haché) — le reste (fichiers manquants, métadonnées absentes, etc.) est bon marché et
    recalculé à chaque appel de GET /api/health-check, pas ici."""
    running = await _get_running_job(db)
    if running:
        return DuplicateScanStartOut(job_id=running.id)

    job = DuplicateScanJob(status="pending", started_at=datetime.utcnow())
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
                await scan_duplicates(scan_db, progress_cb)
                _scan_progress[job.id]["status"] = "done"
                p = _scan_progress[job.id]
                await scan_db.execute(
                    update(DuplicateScanJob)
                    .where(DuplicateScanJob.id == job.id)
                    .values(status="done", processed=p.get("processed", 0), total=p.get("total", 0), finished_at=datetime.utcnow())
                )
                await activity_log(scan_db, "scan", f"Analyse complète de la bibliothèque terminée — {p.get('processed', 0)} fichier(s) analysé(s)", user=scan_user, ip=scan_ip)
            except Exception as e:
                _scan_progress[job.id]["status"] = "error"
                _scan_progress[job.id]["error_msg"] = str(e)
                await scan_db.execute(
                    update(DuplicateScanJob)
                    .where(DuplicateScanJob.id == job.id)
                    .values(status="error", error_msg=str(e), finished_at=datetime.utcnow())
                )
                await activity_log(scan_db, "scan", f"Analyse complète de la bibliothèque échouée : {e}", status="error", user=scan_user, ip=scan_ip)
            await scan_db.commit()

    background_tasks.add_task(run_scan)
    return DuplicateScanStartOut(job_id=job.id)


@router.get("")
async def run_health_check(db: AsyncSession = Depends(get_db)):
    tomes = (await db.execute(select(Tome))).scalars().all()
    series_rows = (await db.execute(select(Series.id, Series.name))).all()
    series_map: dict[int, str] = {r.id: r.name for r in series_rows}
    series_ids = set(series_map.keys())
    cover_dir = Path(settings.COVER_CACHE_DIR)

    issues = []

    KNOWN_FORMATS = {"cbz", "cbr", "pdf"}

    for tome in tomes:
        p = Path(tome.filepath)
        series_title = series_map.get(tome.series_id, "")

        # Fichier introuvable OU illisible (permission refusée) — p.exists() lève
        # PermissionError plutôt que de renvoyer False dans ce cas, donc distingué ici.
        try:
            found = p.exists()
        except PermissionError:
            issues.append({
                "type": "unreadable_file",
                "severity": "error",
                "label": "Fichier illisible (permission refusée)",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": tome.filepath,
            })
            continue
        if not found:
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

        # p.exists() (donc "found" ci-dessus) ne vérifie que la traversée des dossiers
        # parents, pas la permission de lecture du fichier lui-même — un fichier avec des
        # droits restrictifs (copié/déplacé hors de l'app avec un autre propriétaire, par
        # ex.) passe "found=True" mais échoue réellement à l'ouverture (téléchargement OPDS,
        # lecteur web, etc.). os.access vérifie spécifiquement ce bit.
        if not os.access(p, os.R_OK):
            issues.append({
                "type": "unreadable_file",
                "severity": "error",
                "label": "Fichier illisible (permission refusée)",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": tome.filepath,
            })
            continue

        # Intégrité réelle de l'archive (CRC de chaque entrée) — bien trop coûteux pour
        # tourner ici, sur un chemin rechargé à chaque ouverture de Diagnostic : cette
        # vérification lourde vit dans scan_duplicates (services/duplicates.py), lancée
        # uniquement à la demande via "Lancer une analyse complète", et pose tome.status en
        # conséquence. Ici on se contente de LIRE ce résultat déjà calculé, sans toucher au
        # fichier — page_count=0/has_metadata=False seuls (voir plus bas) sont trop ambigus
        # pour ça (bénin la plupart du temps : album réellement sans image, métadonnées
        # jamais renseignées).
        if tome.status == "error" and tome.error_msg:
            issues.append({
                "type": "corrupted_file",
                "severity": "error",
                "label": "Fichier corrompu (archive invalide)",
                "tome_id": tome.id,
                "tome_title": tome.title or tome.filename,
                "series_id": tome.series_id,
                "series_title": series_title,
                "file_format": tome.file_format,
                "detail": tome.error_msg,
            })
            continue

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

    # Doublons réels (même contenu, pas juste même nom+taille) — nécessite d'avoir lancé
    # "Analyser la bibliothèque" au moins une fois (bouton ci-dessus) pour que content_hash
    # soit renseigné ; sinon ce groupe est simplement vide, pas une erreur.
    for group in await get_duplicate_groups(db):
        n = len(group["tomes"])
        for t in group["tomes"]:
            issues.append({
                "type": "duplicate",
                "severity": "warning",
                "label": "Doublon (contenu identique)",
                "tome_id": t["tome_id"],
                "tome_title": t["filename"],
                "series_id": t["series_id"],
                "series_title": t["series_name"],
                "file_format": None,
                "detail": f"Même contenu que {n - 1} autre(s) fichier(s)",
            })

    summary = {
        "error": sum(1 for i in issues if i["severity"] == "error"),
        "warning": sum(1 for i in issues if i["severity"] == "warning"),
        "info": sum(1 for i in issues if i["severity"] == "info"),
        "total": len(issues),
    }

    return {"summary": summary, "issues": issues}


@router.delete("/tome/{tome_id}")
async def delete_orphan_tome(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("library.delete"))):
    """Supprime uniquement l'entrée DB (pas le fichier disque)."""
    tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    await db.delete(tome)
    await db.commit()
    return {"ok": True}
