import asyncio
import io
import json
import shutil
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import auth_required
from ..database import get_db
from ..models.db_models import Series, Tome
from ..config import settings
from ..services.filename_parser import parse_filename
from ..services import activity as activity_svc

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(auth_required)])

ALLOWED_EXTS = {".cbz", ".cbr", ".pdf", ".zip", ".rar"}


class ParseIn(BaseModel):
    filename: str

@router.post("/parse")
async def parse_file(body: ParseIn):
    """Parse un nom de fichier et retourne série, numéro, titre."""
    stem = body.filename.rsplit(".", 1)[0]
    return parse_filename(stem)


@router.get("/series")
async def list_series(db: AsyncSession = Depends(get_db)):
    """Liste les séries existantes pour le dropdown de destination."""
    result = await db.execute(select(Series).order_by(Series.name))
    return [{"id": s.id, "name": s.name} for s in result.scalars().all()]


@router.post("/check")
async def check_file(
    filename: str = Form(...),
    series_id: int | None = Form(None),
    new_series_name: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Vérifie si un fichier existe déjà dans la destination."""
    dest_dir = await _resolve_dest(series_id, new_series_name, db)
    if dest_dir is None:
        return {"duplicate": False}
    return {"duplicate": (dest_dir / filename).exists()}


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    filename: str = Form(...),
    series_id: int | None = Form(None),
    new_series_name: str | None = Form(None),
    metadata: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Copie un fichier vers la destination dans MEDIA_ROOT, puis écrit les métadonnées si CBZ."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Format non supporté : {ext}")

    if not series_id and not new_series_name:
        raise HTTPException(status_code=400, detail="Destination manquante")

    dest_dir = await _resolve_dest(series_id, new_series_name, db)
    if dest_dir is None:
        raise HTTPException(status_code=400, detail="Destination invalide")

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Impossible de créer le dossier destination : {e}")

    dest_file = dest_dir / filename
    duplicate = dest_file.exists()

    try:
        with open(dest_file, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Impossible d'écrire le fichier : {e}")
    finally:
        await file.close()

    # Écrire les métadonnées dans le CBZ si fournies
    if metadata and ext in (".cbz", ".zip"):
        try:
            meta_dict = {k: v for k, v in json.loads(metadata).items() if v}
            if meta_dict:
                from ..services.metadata_writer import write_metadata
                await write_metadata(str(dest_file), meta_dict)
        except Exception:
            pass  # Ne pas bloquer l'import si l'écriture des métadonnées échoue

    await activity_svc.log(db, "import", f"Importé : {filename}", "ok")
    await db.commit()

    return {"ok": True, "path": str(dest_file), "duplicate": duplicate}


class LookupIn(BaseModel):
    filepaths: list[str]

@router.post("/lookup-tomes")
async def lookup_tomes(body: LookupIn, db: AsyncSession = Depends(get_db)):
    """Retourne {filepath: tome_id} pour une liste de chemins absolus."""
    result = await db.execute(select(Tome).where(Tome.filepath.in_(body.filepaths)))
    return {t.filepath: t.id for t in result.scalars().all()}


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

@router.post("/image-size")
async def get_image_size(file: UploadFile = File(...)):
    """Retourne la résolution (width x height) de la 1ère image d'un CBZ/CBR/PDF."""
    def _extract_size(data: bytes, ext: str) -> dict:
        try:
            from PIL import Image
            if ext in (".cbz", ".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    names = sorted([n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
                    if not names:
                        return {}
                    img_data = zf.read(names[0])
                    img = Image.open(io.BytesIO(img_data))
                    return {"width": img.width, "height": img.height}
            elif ext in (".cbr", ".rar"):
                import rarfile
                with rarfile.RarFile(io.BytesIO(data)) as rf:
                    names = sorted([n for n in rf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
                    if not names:
                        return {}
                    img_data = rf.read(names[0])
                    img = Image.open(io.BytesIO(img_data))
                    return {"width": img.width, "height": img.height}
        except Exception:
            pass
        return {}

    data = await file.read()
    ext = Path(file.filename or "").suffix.lower()
    result = await asyncio.to_thread(_extract_size, data, ext)
    return result


class CancelCleanupIn(BaseModel):
    paths: list[str]
    is_new_series: bool = False
    new_series_name: str | None = None


@router.post("/cancel-cleanup")
async def cancel_cleanup(body: CancelCleanupIn):
    """Supprime les fichiers uploadés lors d'une annulation.
    Si is_new_series=True et que le dossier est vide après suppression, le supprime aussi."""
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"[cancel-cleanup] paths={body.paths} is_new_series={body.is_new_series}")

    deleted = []
    dirs_to_check = set()

    for path_str in body.paths:
        p = Path(path_str)
        logger.warning(f"[cancel-cleanup] checking {p} exists={p.exists()} is_file={p.is_file() if p.exists() else 'N/A'}")
        if p.exists() and p.is_file():
            try:
                p.unlink()
                deleted.append(str(p))
                dirs_to_check.add(p.parent)
                logger.warning(f"[cancel-cleanup] deleted {p}")
            except OSError as e:
                logger.warning(f"[cancel-cleanup] unlink error {p}: {e}")

    if body.is_new_series:
        for d in dirs_to_check:
            try:
                contents = list(d.iterdir()) if d.exists() else []
                logger.warning(f"[cancel-cleanup] dir {d} exists={d.exists()} contents={contents}")
                if d.exists() and not contents:
                    d.rmdir()
                    logger.warning(f"[cancel-cleanup] rmdir {d}")
            except OSError as e:
                logger.warning(f"[cancel-cleanup] rmdir error {d}: {e}")

    logger.warning(f"[cancel-cleanup] done deleted={deleted}")
    return {"deleted": deleted}


async def _resolve_dest(series_id: int | None, new_series_name: str | None, db: AsyncSession) -> Path | None:
    import logging
    logger = logging.getLogger(__name__)

    if series_id is not None:
        result = await db.execute(select(Series).where(Series.id == series_id))
        series = result.scalar_one_or_none()
        if series:
            logger.warning(f"[import] resolve_dest series_id={series_id} -> folder_path={series.folder_path!r}")
            return Path(series.folder_path)

    if new_series_name:
        name = new_series_name.strip().strip("/")
        if not name:
            return None
        media_root = Path(settings.MEDIA_ROOT)
        if settings.LIBRARY_SUBDIR:
            media_root = media_root / settings.LIBRARY_SUBDIR.strip("/")
        dest = media_root / name
        logger.warning(f"[import] resolve_dest new_series={new_series_name!r} MEDIA_ROOT={settings.MEDIA_ROOT!r} -> dest={dest!r}")
        return dest

    return None
