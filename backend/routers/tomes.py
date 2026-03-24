from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pathlib import Path
import json
import re
import logging

from ..config import settings

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Tome, Metadata, ReadingProgress, Series
from ..models.schemas import TomeOut, MetadataOut, MetadataIn, ParseFilenameOut, UserDataIn, ReadingProgressOut, ReadingProgressIn, RenameIn, RenameBulkIn, RenameToIn, RenameBulkToIn
from ..services.filename_parser import parse_filename
from ..services.metadata_writer import write_metadata


def apply_pattern(pattern: str, tome: Tome, meta: Metadata | None) -> str:
    p = Path(tome.filepath)
    ext = p.suffix
    name = p.stem
    result = pattern
    result = result.replace("{Fichier}", name)
    result = result.replace("{Filename}", name)
    result = result.replace("{Série}", meta.Series if meta and meta.Series else "")
    result = result.replace("{Series}", meta.Series if meta and meta.Series else "")
    result = result.replace("{Numéro}", meta.Number if meta and meta.Number else "")
    result = result.replace("{Number}", meta.Number if meta and meta.Number else "")
    result = result.replace("{Titre}", meta.Title if meta and meta.Title else "")
    result = result.replace("{Title}", meta.Title if meta and meta.Title else "")
    result = result.replace("{Année}", meta.Year if meta and meta.Year else "")
    result = result.replace("{Year}", meta.Year if meta and meta.Year else "")
    result = result.replace("{Dessinateur}", meta.Penciller if meta and meta.Penciller else "")
    result = result.replace("{Scénariste}", meta.Writer if meta and meta.Writer else "")
    result = result.replace("{Writer}", meta.Writer if meta and meta.Writer else "")
    result = result.replace("{Éditeur}", meta.Publisher if meta and meta.Publisher else "")
    result = result.replace("{Publisher}", meta.Publisher if meta and meta.Publisher else "")
    result = re.sub(r'[<>:"/\\|?*]', '_', result)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    result = re.sub(r'_+', '_', result).strip("_").strip()
    if not result:
        result = name
    return result + ext


router = APIRouter(prefix="/api/tomes", tags=["tomes"], dependencies=[Depends(auth_required)])


def _cover_url(tome_id: int, updated_at=None) -> str:
    if updated_at is not None:
        v = int(updated_at.timestamp()) if hasattr(updated_at, "timestamp") else str(updated_at).replace(" ", "")
        return f"/api/covers/{tome_id}?v={v}"
    return f"/api/covers/{tome_id}"


def _build_tome_out(t: Tome, meta: Metadata | None = None, series_hidden: bool = False) -> TomeOut:
    tags: list[str] = []
    if t.user_tag_list:
        try:
            tags = json.loads(t.user_tag_list)
        except Exception:
            tags = []
    return TomeOut(
        id=t.id, series_id=t.series_id, filename=t.filename,
        filepath=t.filepath, number=t.number, title=t.title,
        file_format=t.file_format, file_size=t.file_size,
        page_count=t.page_count, has_metadata=t.has_metadata,
        cover_cached=t.cover_cached, cover_url=_cover_url(t.id, t.updated_at),
        status=t.status, created_at=t.created_at, updated_at=t.updated_at,
        hidden=t.hidden, series_hidden=series_hidden,
        user_rating=t.user_rating, user_notes=t.user_notes, user_tags=tags,
        writer=meta.Writer if meta else None,
        penciller=meta.Penciller if meta else None,
        publisher=meta.Publisher if meta else None,
    )


@router.get("", response_model=list[TomeOut])
async def list_all_tomes(show_hidden: bool = False, db: AsyncSession = Depends(get_db)):
    from ..models.db_models import Series
    from sqlalchemy import text

    # Récupère le mapping series_id → hidden
    series_rows = (await db.execute(select(Series.id, Series.hidden))).all()
    series_hidden_map: dict[int, bool] = {r[0]: bool(r[1]) for r in series_rows}

    q = (
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .order_by(Tome.series_id, Tome.number)
    )
    if not show_hidden:
        hidden_series_ids = [sid for sid, h in series_hidden_map.items() if h]
        q = q.where(Tome.hidden == False)
        if hidden_series_ids:
            q = q.where(Tome.series_id.notin_(hidden_series_ids))
    result = await db.execute(q)
    rows = result.all()
    return [_build_tome_out(t, m, series_hidden=series_hidden_map.get(t.series_id, False)) for t, m in rows]


@router.get("/in-progress", response_model=list[dict])
async def list_in_progress(db: AsyncSession = Depends(get_db)):
    from ..models.db_models import Series
    result = await db.execute(
        select(ReadingProgress, Tome, Metadata)
        .join(Tome, Tome.id == ReadingProgress.tome_id)
        .join(Series, Series.id == Tome.series_id)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(ReadingProgress.last_page > 0)
        .where(Tome.hidden == False, Series.hidden == False)
        .order_by(ReadingProgress.updated_at.desc())
        .limit(12)
    )
    rows = result.all()
    out = []
    for prog, tome, meta in rows:
        if tome.page_count and prog.last_page >= tome.page_count - 1:
            continue  # terminé
        t = _build_tome_out(tome, meta)
        out.append({
            **t.model_dump(),
            "last_page": prog.last_page,
            "progress_pct": round(prog.last_page / tome.page_count * 100) if tome.page_count else 0,
        })
    return out


@router.get("/tags", response_model=list[str])
async def list_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome.user_tag_list).where(Tome.user_tag_list.isnot(None)))
    all_tags: set[str] = set()
    for (tag_list,) in result.all():
        try:
            all_tags.update(json.loads(tag_list))
        except Exception:
            pass
    return sorted(all_tags)


@router.post("/rename-bulk")
async def rename_bulk(body: RenameBulkIn, db: AsyncSession = Depends(get_db)):
    ok = 0
    errors = []
    for tome_id in body.ids:
        result = await db.execute(
            select(Tome, Metadata)
            .outerjoin(Metadata, Metadata.tome_id == Tome.id)
            .where(Tome.id == tome_id)
        )
        row = result.first()
        if row is None:
            errors.append(f"id={tome_id} : introuvable")
            continue
        tome, meta = row
        try:
            new_name = apply_pattern(body.pattern, tome, meta)
            if new_name == Path(tome.filepath).name:
                continue
            new_path = Path(tome.filepath).parent / new_name
            if new_path.exists():
                errors.append(f"{tome.filename} : fichier cible déjà existant")
                continue
            Path(tome.filepath).rename(new_path)
            tome.filename = new_name
            tome.filepath = str(new_path)
            tome.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(tome)
            ok += 1
        except Exception as e:
            errors.append(f"{tome.filename} : {e}")
    return {"ok": ok, "errors": errors}


@router.post("/{tome_id}/rename", response_model=TomeOut)
async def rename_tome(tome_id: int, body: RenameIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    new_name = apply_pattern(body.pattern, tome, meta)
    if new_name == Path(tome.filepath).name:
        return _build_tome_out(tome, meta)
    new_path = Path(tome.filepath).parent / new_name
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"Fichier cible déjà existant : {new_name}")
    Path(tome.filepath).rename(new_path)
    tome.filename = new_name
    tome.filepath = str(new_path)
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    return _build_tome_out(tome, meta)


def _validate_new_filename(new_filename: str, original_filepath: str):
    if any(c in new_filename for c in ('/', '\\')) or '..' in new_filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    orig_ext = Path(original_filepath).suffix
    new_ext = Path(new_filename).suffix
    if new_ext.lower() != orig_ext.lower():
        raise HTTPException(status_code=400, detail="L'extension ne peut pas changer")


@router.post("/rename-bulk-to")
async def rename_bulk_to(body: RenameBulkToIn, db: AsyncSession = Depends(get_db)):
    ok = 0
    errors = []
    for item in body.renames:
        result = await db.execute(
            select(Tome, Metadata)
            .outerjoin(Metadata, Metadata.tome_id == Tome.id)
            .where(Tome.id == item.id)
        )
        row = result.first()
        if row is None:
            errors.append(f"id={item.id} : introuvable")
            continue
        tome, meta = row
        try:
            _validate_new_filename(item.new_filename, tome.filepath)
            if item.new_filename == Path(tome.filepath).name:
                continue
            new_path = Path(tome.filepath).parent / item.new_filename
            if new_path.exists():
                errors.append(f"{tome.filename} : fichier cible déjà existant")
                continue
            Path(tome.filepath).rename(new_path)
            tome.filename = item.new_filename
            tome.filepath = str(new_path)
            tome.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(tome)
            ok += 1
        except HTTPException as e:
            errors.append(f"{tome.filename} : {e.detail}")
        except Exception as e:
            errors.append(f"{tome.filename} : {e}")
    from ..services.activity import log as activity_log
    series_name = ""
    if body.renames:
        first_row = (await db.execute(select(Tome).where(Tome.id == body.renames[0].id))).scalar_one_or_none()
        if first_row:
            s = (await db.execute(select(Series).where(Series.id == first_row.series_id))).scalar_one_or_none()
            if s: series_name = s.name
    msg = f"Renommage terminé : {ok} album(s) renommé(s)"
    if series_name: msg += f" dans « {series_name} »"
    if errors: msg += f", {len(errors)} erreur(s)"
    await activity_log(db, "rename", msg, status="ok" if not errors else "error")
    await db.commit()
    return {"ok": ok, "errors": errors}


@router.post("/{tome_id}/rename-to", response_model=TomeOut)
async def rename_tome_to(tome_id: int, body: RenameToIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    _validate_new_filename(body.new_filename, tome.filepath)
    if body.new_filename == Path(tome.filepath).name:
        return _build_tome_out(tome, meta)
    new_path = Path(tome.filepath).parent / body.new_filename
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"Fichier cible déjà existant : {body.new_filename}")
    Path(tome.filepath).rename(new_path)
    tome.filename = body.new_filename
    tome.filepath = str(new_path)
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    return _build_tome_out(tome, meta)


@router.get("/{tome_id}", response_model=TomeOut)
async def get_tome(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    return _build_tome_out(tome, meta)


@router.get("/{tome_id}/metadata", response_model=MetadataOut)
async def get_metadata(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome_id))
    meta = meta_result.scalar_one_or_none()
    if meta is None:
        return MetadataOut()
    return MetadataOut.model_validate(meta)


@router.put("/{tome_id}/metadata", response_model=MetadataOut)
async def update_metadata(tome_id: int, body: MetadataIn, silent: bool = False, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    if tome.file_format not in ("cbz",):
        raise HTTPException(
            status_code=400,
            detail="Seuls les fichiers CBZ peuvent être modifiés. Convertissez d'abord en CBZ."
        )

    fields = body.model_dump(exclude_none=True)

    try:
        await write_metadata(tome.filepath, fields)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur écriture: {str(e)}")

    # Update DB metadata row
    meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome_id))
    meta = meta_result.scalar_one_or_none()
    if meta is None:
        meta = Metadata(tome_id=tome_id)
        db.add(meta)

    for key, val in fields.items():
        if hasattr(meta, key):
            setattr(meta, key, val)

    tome.has_metadata = True
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(meta)

    if not silent:
        from ..services.activity import log as activity_log
        title = fields.get("Title") or tome.title or tome.filename
        series_row = (await db.execute(select(Series).where(Series.id == tome.series_id))).scalar_one_or_none()
        series_name = series_row.name if series_row else ""
        msg = f"Métadonnées éditées : « {title} »"
        if series_name: msg += f" ({series_name})"
        await activity_log(db, "edit_metadata", msg)
        await db.commit()

    return MetadataOut.model_validate(meta)


@router.post("/{tome_id}/parse-filename", response_model=ParseFilenameOut)
async def parse_tome_filename(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    parsed = parse_filename(tome.filename.rsplit(".", 1)[0])
    return ParseFilenameOut(**parsed)


@router.patch("/{tome_id}/user-data", response_model=TomeOut)
async def update_user_data(tome_id: int, body: UserDataIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row

    if body.user_rating is not None:
        tome.user_rating = max(1, min(5, body.user_rating))
    if body.user_notes is not None:
        tome.user_notes = body.user_notes
    if body.user_tags is not None:
        tome.user_tag_list = json.dumps(body.user_tags, ensure_ascii=False)

    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    return _build_tome_out(tome, meta)


@router.get("/{tome_id}/progress", response_model=ReadingProgressOut)
async def get_progress(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReadingProgress).where(ReadingProgress.tome_id == tome_id))
    prog = result.scalar_one_or_none()
    if prog is None:
        return ReadingProgressOut(tome_id=tome_id, last_page=0)
    return ReadingProgressOut(tome_id=prog.tome_id, last_page=prog.last_page, updated_at=prog.updated_at)


@router.put("/{tome_id}/progress", response_model=ReadingProgressOut)
async def save_progress(tome_id: int, body: ReadingProgressIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReadingProgress).where(ReadingProgress.tome_id == tome_id))
    prog = result.scalar_one_or_none()
    if prog is None:
        prog = ReadingProgress(tome_id=tome_id, last_page=body.last_page)
        db.add(prog)
    else:
        prog.last_page = body.last_page
        prog.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(prog)
    return ReadingProgressOut(tome_id=prog.tome_id, last_page=prog.last_page, updated_at=prog.updated_at)


@router.patch("/{tome_id}/hidden", response_model=TomeOut)
async def toggle_tome_hidden(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    tome.hidden = not tome.hidden
    await db.commit()
    await db.refresh(tome)
    from ..services.activity import log as activity_log
    action = "Album masqué" if tome.hidden else "Album affiché"
    await activity_log(db, "edit_metadata", f"{action} : « {tome.title or tome.filename} »")
    await db.commit()
    return _build_tome_out(tome, meta)


@router.get("/{tome_id}/file-info")
async def get_tome_file_info(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    p = Path(tome.filepath)
    file_size = p.stat().st_size if p.exists() else None

    width, height = None, None
    try:
        if tome.file_format in ("cbz",):
            import zipfile
            with zipfile.ZipFile(tome.filepath) as zf:
                images = sorted([n for n in zf.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
                if images:
                    import io
                    from PIL import Image
                    with zf.open(images[0]) as f:
                        img = Image.open(io.BytesIO(f.read()))
                        width, height = img.size
        elif tome.file_format == "cbr":
            import subprocess, io
            from PIL import Image
            result_rar = subprocess.run(["unrar", "lb", tome.filepath], capture_output=True, text=True)
            files = sorted([l.strip() for l in result_rar.stdout.splitlines() if l.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            if files:
                result_rar2 = subprocess.run(["unrar", "p", "-inul", tome.filepath, files[0]], capture_output=True)
                img = Image.open(io.BytesIO(result_rar2.stdout))
                width, height = img.size
        elif tome.file_format == "pdf":
            import fitz
            doc = fitz.open(tome.filepath)
            page = doc[0]
            width, height = int(page.rect.width), int(page.rect.height)
            doc.close()
    except Exception:
        pass

    return {
        "filepath": tome.filepath,
        "file_size": file_size,
        "image_width": width,
        "image_height": height,
    }


@router.delete("/{tome_id}/file", status_code=200)
async def delete_tome_file(tome_id: int, db: AsyncSession = Depends(get_db)):
    """Supprime le fichier sur disque, l'entrée DB, et le cache cover.
    Si c'était le dernier tome de la série, supprime aussi la série."""
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    series_id = tome.series_id

    # Supprimer le fichier sur disque
    try:
        Path(tome.filepath).unlink(missing_ok=True)
    except Exception as e:
        logging.warning(f"Could not delete file {tome.filepath}: {e}")

    # Supprimer le cache cover
    cover_dir = Path(settings.COVER_CACHE_DIR)
    for f in [cover_dir / f"{tome_id}.jpg", cover_dir / f"{tome_id}_thumb.jpg"]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    tome_name = tome.title or tome.filename
    series_name_for_log = None
    # Supprimer l'entrée DB (cascade supprime metadata, progress)
    await db.delete(tome)
    await db.commit()

    # Vérifier si la série est maintenant vide → la supprimer aussi
    remaining = (await db.execute(
        select(Tome).where(Tome.series_id == series_id)
    )).scalars().first()

    from ..services.activity import log as activity_log
    series_deleted = False
    if remaining is None:
        series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if series:
            series_name_for_log = series.name
            try:
                folder = Path(series.folder_path)
                if folder.exists() and not any(folder.iterdir()):
                    folder.rmdir()
            except Exception as e:
                logging.warning(f"Could not delete folder {series.folder_path}: {e}")
            await db.delete(series)
            await db.commit()
            series_deleted = True

    if series_deleted:
        await activity_log(db, "delete_series", f"Album supprimé : « {tome_name} » (série « {series_name_for_log} » supprimée car vide)")
    else:
        await activity_log(db, "delete_tome", f"Album supprimé : « {tome_name} »")
    await db.commit()

    return {"series_deleted": series_deleted, "series_id": series_id}
