"""
Conversion job management.
Converts CBR/PDF to CBZ with image recompression.
"""
import asyncio
import ctypes
import zipfile
import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models.db_models import ConvertJob, ConvertJobTome, Tome
from ..database import AsyncSessionLocal

# In-memory progress store: {job_id: {tome_id: {progress, total, status}}}
_progress: dict[int, dict] = {}
# Abort flags: {job_id: ctypes.c_bool}
_abort_flags: dict[int, ctypes.c_bool] = {}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

QUALITY_PRESETS = {
    "Light":    {"quality": 60, "max_width": 1200},
    "Medium":   {"quality": 75, "max_width": 1600},
    "HQ":       {"quality": 85, "max_width": 2048},
    "Original": {"quality": 95, "max_width": 9999},
}


def _extract_images(src: Path) -> list[tuple[str, bytes]]:
    """Extract (name, bytes) image pairs from CBR, CBZ or PDF."""
    ext = src.suffix.lower()
    images = []

    if ext in (".cbz", ".zip"):
        with zipfile.ZipFile(str(src), "r") as zf:
            names = sorted([
                n for n in zf.namelist()
                if Path(n).suffix.lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX")
            ])
            for name in names:
                images.append((name, zf.read(name)))

    elif ext in (".cbr", ".rar"):
        import rarfile
        with rarfile.RarFile(str(src), "r") as rf:
            names = sorted([
                n for n in rf.namelist()
                if Path(n).suffix.lower() in IMAGE_EXTS
            ])
            for name in names:
                images.append((name, rf.read(name)))

    elif ext == ".pdf":
        import fitz
        doc = fitz.open(str(src))
        for i in range(doc.page_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            images.append((f"page_{i+1:04d}.jpg", pix.tobytes("jpeg")))
        doc.close()

    return images


def _recompress_image(img_bytes: bytes, quality: int, max_width: int) -> bytes:
    """Recompress image bytes to JPEG with given quality and max width."""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # Always resize if above max_width
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        # After resize, always save recompressed (smaller by definition)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        return out.getvalue()
    # No resize needed — recompress and return smallest
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    result = out.getvalue()
    return result if len(result) < len(img_bytes) else img_bytes


def _convert_sync(src: str, dest: str, preset: str, progress_cb: Callable, abort_flag) -> None:
    """Convert src file to CBZ at dest with given quality preset."""
    import logging, shutil
    src_path = Path(src)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Preset Original sur un CBZ source : copie directe, pas de recompression
    if preset == "Original" and src_path.suffix.lower() in (".cbz", ".zip"):
        if src_path != dest_path:
            shutil.copy2(str(src_path), str(dest_path))
        progress_cb(1, 1)
        return

    params = QUALITY_PRESETS.get(preset, QUALITY_PRESETS["Original"])
    quality = params["quality"]
    max_width = params["max_width"]

    images = _extract_images(src_path)
    total = len(images)

    with zipfile.ZipFile(str(dest_path), "w", zipfile.ZIP_STORED) as zout:
        for i, (name, img_bytes) in enumerate(images):
            if abort_flag.value:
                break
            try:
                recompressed = _recompress_image(img_bytes, quality, max_width)
            except Exception:
                recompressed = img_bytes
            out_name = Path(name).stem + ".jpg"
            zout.writestr(out_name, recompressed)
            progress_cb(i + 1, total)


def estimate_size(src: Path, preset: str) -> int:
    """Estimate output size based on empirical ratios per preset."""
    # Empirical ratios measured on real manga/comic files (JPEG ~q80, 1920px source)
    # ratio = (max_width / src_width)^2 * quality_factor
    EMPIRICAL_RATIOS = {
        "Light":    0.32,  # 1200px, q60 → ~32% of original
        "Medium":   0.58,  # 1600px, q75 → ~58% of original
        "HQ":       0.80,  # 2048px, q85 → ~80% of original
        "Original": 1.00,  # copy
    }
    try:
        original = src.stat().st_size
        if preset == "Original" and src.suffix.lower() in (".cbz", ".zip"):
            return original
        ratio = EMPIRICAL_RATIOS.get(preset, 1.0)
        return int(original * ratio)
    except Exception:
        return 0


async def create_convert_job(
    tome_ids: list[int],
    preset: str,
    dest_path: Optional[str],
    db: AsyncSession,
    delete_source: bool = False,
) -> int:
    job = ConvertJob(preset=preset, dest_path=dest_path, delete_source=delete_source, total=len(tome_ids))
    db.add(job)
    await db.flush()

    for tome_id in tome_ids:
        db.add(ConvertJobTome(job_id=job.id, tome_id=tome_id))

    await db.commit()
    await db.refresh(job)

    _progress[job.id] = {}
    for tome_id in tome_ids:
        _progress[job.id][tome_id] = {"progress": 0, "total": 0, "status": "pending"}

    return job.id


async def run_convert_job(job_id: int) -> None:
    """Background task: run all conversion jobs sequentially."""
    import logging
    logging.warning(f"RUN_CONVERT_JOB start job_id={job_id}")
    abort_flag = ctypes.c_bool(False)
    _abort_flags[job_id] = abort_flag

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ConvertJob).where(ConvertJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logging.warning(f"RUN_CONVERT_JOB job not found job_id={job_id}")
            return

        tomes_result = await db.execute(
            select(ConvertJobTome).where(ConvertJobTome.job_id == job_id)
        )
        job_tomes = tomes_result.scalars().all()
        logging.warning(f"RUN_CONVERT_JOB job_id={job_id} preset={job.preset} tomes_count={len(job_tomes)}")

        await db.execute(
            update(ConvertJob).where(ConvertJob.id == job_id).values(status="running")
        )
        await db.commit()

        for jt in job_tomes:
            if abort_flag.value:
                break

            tome_result = await db.execute(select(Tome).where(Tome.id == jt.tome_id))
            tome = tome_result.scalar_one_or_none()
            if tome is None:
                continue

            _progress[job_id][jt.tome_id] = {"progress": 0, "total": 0, "status": "running"}

            src = Path(tome.filepath)
            if job.dest_path:
                dest = Path(job.dest_path) / (src.stem + ".cbz")
            else:
                dest = src.parent / (src.stem + ".cbz")

            def progress_cb(current: int, total: int):
                _progress[job_id][jt.tome_id] = {
                    "progress": current,
                    "total": total,
                    "status": "running",
                }

            try:
                await asyncio.to_thread(
                    _convert_sync,
                    str(src), str(dest), job.preset, progress_cb, abort_flag
                )
                _progress[job_id][jt.tome_id]["status"] = "done"
                jt.status = "done"
                jt.progress = _progress[job_id][jt.tome_id].get("total", 0)
                jt.total = jt.progress
                if job.delete_source and src != dest and src.exists():
                    src.unlink()

            except Exception as e:
                import logging
                logging.warning(f"CONVERT ERROR tome={jt.tome_id}: {e}")
                _progress[job_id][jt.tome_id] = {
                    "progress": 0, "total": 0,
                    "status": "error",
                    "error": str(e),
                }
                jt.status = "error"

            await db.commit()

        final_status = "error" if abort_flag.value else "done"
        await db.execute(
            update(ConvertJob)
            .where(ConvertJob.id == job_id)
            .values(status=final_status, finished_at=datetime.utcnow())
        )
        await db.commit()

        from .activity import log as activity_log
        done_count = sum(1 for v in _progress.get(job_id, {}).values() if v.get("status") == "done")
        err_count  = sum(1 for v in _progress.get(job_id, {}).values() if v.get("status") == "error")
        msg = f"Conversion terminée — {done_count} fichier(s) convertis"
        if err_count: msg += f", {err_count} erreur(s)"
        await activity_log(db, "convert", msg, status="ok" if final_status == "done" else "error")
        await db.commit()

    _abort_flags.pop(job_id, None)


def abort_job(job_id: int) -> bool:
    flag = _abort_flags.get(job_id)
    if flag is not None:
        flag.value = True
        return True
    return False


def get_progress(job_id: int) -> dict:
    return _progress.get(job_id, {})
