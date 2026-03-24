import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import ConvertJob
from ..models.schemas import ConvertIn, ConvertStartOut, ConvertStatusOut
from ..services.converter_service import (
    create_convert_job, run_convert_job, abort_job, get_progress,
    estimate_size, QUALITY_PRESETS
)

router = APIRouter(prefix="/api/convert", tags=["converter"], dependencies=[Depends(auth_required)])


@router.post("", response_model=ConvertStartOut)
async def start_convert(body: ConvertIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if not body.tome_ids:
        raise HTTPException(status_code=400, detail="Aucun tome sélectionné")

    presets = {"Light", "Medium", "HQ", "Original"}
    if body.preset not in presets:
        raise HTTPException(status_code=400, detail=f"Preset invalide. Valeurs: {', '.join(presets)}")

    job_id = await create_convert_job(body.tome_ids, body.preset, body.dest_path, db, delete_source=body.delete_source)
    background_tasks.add_task(run_convert_job, job_id)
    return ConvertStartOut(job_id=job_id)


@router.get("/{job_id}", response_model=ConvertStatusOut)
async def convert_status(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConvertJob).where(ConvertJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")

    # Utiliser la progression en mémoire si le job est en cours
    live = get_progress(job_id)
    if live and job.status not in ("done", "error"):
        total    = sum(v.get("total", 0)    for v in live.values())
        progress = sum(v.get("progress", 0) for v in live.values())
        status   = "done" if all(v.get("status") == "done" for v in live.values()) \
                   else "error" if any(v.get("status") == "error" for v in live.values()) \
                   else "running"
    else:
        total    = job.total
        progress = job.progress
        status   = job.status

    return ConvertStatusOut(
        job_id=job.id,
        status=status,
        progress=progress,
        total=total,
        error_msg=job.error_msg,
    )


@router.get("/{job_id}/stream")
async def convert_stream(job_id: int, _=Depends(auth_required)):
    async def event_gen():
        while True:
            progress = get_progress(job_id)
            # Check if all done
            all_statuses = [v.get("status") for v in progress.values()]
            overall = "running"
            # Only mark done when statuses exist, all are terminal, and at least one ran
            if (all_statuses
                    and all(s in ("done", "error") for s in all_statuses)
                    and any(s != "pending" for s in all_statuses)):
                overall = "done"

            payload = {
                "job_id": job_id,
                "status": overall,
                "tomes": progress,
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if overall in ("done", "error"):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{job_id}", status_code=204)
async def cancel_convert(job_id: int):
    if not abort_job(job_id):
        raise HTTPException(status_code=404, detail="Job introuvable ou déjà terminé")


class PathCheckIn(BaseModel):
    path: str

@router.post("/check-path")
async def check_path(body: PathCheckIn, _=Depends(auth_required)):
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail="Ce chemin n'existe pas")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="Ce chemin n'est pas un dossier")
    return {"valid": True}


class EstimateIn(BaseModel):
    tome_ids: list[int]
    preset: str

@router.post("/estimate")
async def estimate_conversion(body: EstimateIn, db: AsyncSession = Depends(get_db)):
    from ..models.db_models import Tome
    if body.preset not in QUALITY_PRESETS:
        raise HTTPException(status_code=400, detail="Preset invalide")
    total = 0
    for tome_id in body.tome_ids:
        result = await db.execute(select(Tome).where(Tome.id == tome_id))
        tome = result.scalar_one_or_none()
        if tome is None:
            continue
        est = await asyncio.to_thread(estimate_size, Path(tome.filepath), body.preset)
        if est > 0:
            total += est
    return {"estimated_bytes": total}
