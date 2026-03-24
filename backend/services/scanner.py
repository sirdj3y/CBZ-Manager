import asyncio
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ..models.db_models import Series, Tome, Metadata, ScanJob
from ..database import AsyncSessionLocal
from ..config import settings
from .filename_parser import parse_filename
from .cover_cache import ensure_cover

COMIC_EXTS = {".cbz", ".cbr", ".pdf", ".zip", ".rar"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _parse_comicinfo_xml(xml_bytes: bytes) -> dict:
    """Parse ComicInfo.xml and return a dict of fields."""
    try:
        root = ET.fromstring(xml_bytes)
        result = {}
        for child in root:
            if child.text and child.text.strip():
                result[child.tag] = child.text.strip()
        return result
    except Exception:
        return {}


def _read_comic_info(filepath: Path) -> tuple[int, dict]:
    """Read page count and ComicInfo.xml metadata from a comic file."""
    ext = filepath.suffix.lower()
    page_count = 0
    metadata = {}

    if ext in (".cbz", ".zip"):
        try:
            with zipfile.ZipFile(str(filepath), "r") as zf:
                names = zf.namelist()
                pages = [n for n in names if Path(n).suffix.lower() in IMAGE_EXTS and not n.startswith("__MACOSX")]
                page_count = len(pages)
                # Try to read ComicInfo.xml
                ci_names = [n for n in names if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    metadata = _parse_comicinfo_xml(zf.read(ci_names[0]))
        except Exception:
            pass

    elif ext in (".cbr", ".rar"):
        try:
            import rarfile
            with rarfile.RarFile(str(filepath), "r") as rf:
                names = rf.namelist()
                pages = [n for n in names if Path(n).suffix.lower() in IMAGE_EXTS]
                page_count = len(pages)
                ci_names = [n for n in names if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    metadata = _parse_comicinfo_xml(rf.read(ci_names[0]))
        except Exception:
            pass

    elif ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(filepath))
            page_count = doc.page_count
            doc.close()
        except Exception:
            pass

    return page_count, metadata


async def get_running_scan(db: AsyncSession) -> Optional[ScanJob]:
    result = await db.execute(
        select(ScanJob).where(ScanJob.status == "running").limit(1)
    )
    return result.scalar_one_or_none()


async def create_scan_job(db: AsyncSession) -> ScanJob:
    job = ScanJob(status="pending", started_at=datetime.utcnow())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def scan_library(
    library_path: str,
    db: AsyncSession,
    job_id: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """
    Walk library_path, group files by parent folder (= series name),
    upsert Series/Tome/Metadata rows, update scan job status.
    """
    lib = Path(library_path)

    # Mark job running
    await db.execute(
        update(ScanJob)
        .where(ScanJob.id == job_id)
        .values(status="running", started_at=datetime.utcnow())
    )
    await db.commit()

    try:
        # Collect all comic files
        all_files: list[Path] = []
        for ext in COMIC_EXTS:
            all_files.extend(lib.rglob(f"*{ext}"))

        # Filter out files at library root (no series folder)
        def get_series_name(filepath: Path) -> str:
            rel = filepath.relative_to(lib)
            parts = rel.parts
            if len(parts) == 1:
                return lib.name
            return parts[0]

        total = len(all_files)
        await db.execute(
            update(ScanJob).where(ScanJob.id == job_id).values(total=total)
        )
        await db.commit()

        # Remove tomes whose files no longer exist on disk OR are outside library_path
        all_paths = {str(f) for f in all_files}
        lib_prefix = str(lib.resolve())
        existing_tomes = (await db.execute(select(Tome))).scalars().all()
        for tome in existing_tomes:
            if tome.filepath not in all_paths or not tome.filepath.startswith(lib_prefix):
                await db.delete(tome)
        await db.commit()

        # Remove series whose folder is outside library_path OR have no remaining tomes
        all_series = (await db.execute(select(Series))).scalars().all()
        for series in all_series:
            outside = not series.folder_path.startswith(lib_prefix)
            count = (await db.execute(
                select(Tome).where(Tome.series_id == series.id)
            )).scalars().first()
            if outside or count is None:
                await db.delete(series)
        await db.commit()

        processed = 0
        for filepath in sorted(all_files):
            # Use a fresh session per file to avoid session corruption on error
            async with AsyncSessionLocal() as file_db:
                try:
                    tome = await _process_file(filepath, lib, file_db)
                    await file_db.commit()
                    # Pre-generate cover for new/updated tomes
                    if tome is not None:
                        await ensure_cover(tome.id, tome.filepath)
                except Exception as e:
                    import logging
                    logging.warning(f"FILE ERROR {filepath}: {e}")
                    await file_db.rollback()
            processed += 1
            if progress_cb:
                progress_cb(processed, total)

        # Update tome_count for all series
        result = await db.execute(select(Series))
        for series in result.scalars().all():
            count_result = await db.execute(
                select(Tome).where(Tome.series_id == series.id)
            )
            count = len(count_result.scalars().all())
            series.tome_count = count
            series.updated_at = datetime.utcnow()

        await db.commit()

        # Cleanup orphan covers
        await _cleanup_orphan_covers(db)

        # Mark done
        await db.execute(
            update(ScanJob)
            .where(ScanJob.id == job_id)
            .values(status="done", processed=processed, total=total, finished_at=datetime.utcnow())
        )
        await db.commit()

    except Exception as e:
        await db.execute(
            update(ScanJob)
            .where(ScanJob.id == job_id)
            .values(status="error", error_msg=str(e), finished_at=datetime.utcnow())
        )
        await db.commit()
        raise


async def _cleanup_orphan_covers(db: AsyncSession) -> None:
    """Delete cover files whose tome_id no longer exists in DB."""
    cover_dir = Path(settings.COVER_CACHE_DIR)
    if not cover_dir.exists():
        return

    result = await db.execute(select(Tome.id))
    valid_ids = {row[0] for row in result.fetchall()}

    for cover_file in cover_dir.glob("*.jpg"):
        stem = cover_file.stem  # e.g. "42" or "42_thumb"
        try:
            tome_id = int(stem.split("_")[0])
        except ValueError:
            continue
        if tome_id not in valid_ids:
            cover_file.unlink()


async def _process_file(filepath: Path, lib: Path, db: AsyncSession) -> Optional[Tome]:
    """Upsert a single comic file into the DB."""

    rel = filepath.relative_to(lib)
    parts = rel.parts
    if len(parts) > 1:
        series_name = parts[0]
        series_folder = lib / series_name
    else:
        # File is directly in the library root → use the library folder name as series
        series_name = lib.name
        series_folder = lib

    # Upsert series
    result = await db.execute(select(Series).where(Series.name == series_name))
    series = result.scalar_one_or_none()
    if series is None:
        series = Series(name=series_name, folder_path=str(series_folder))
        db.add(series)
        await db.flush()

    # Parse filename
    stem = filepath.stem
    parsed = parse_filename(stem)

    # Detect format
    ext = filepath.suffix.lower()
    fmt_map = {".cbz": "cbz", ".zip": "cbz", ".cbr": "cbr", ".rar": "cbr", ".pdf": "pdf"}
    file_format = fmt_map.get(ext, "unknown")

    file_size = filepath.stat().st_size

    # Check if tome already exists
    result = await db.execute(select(Tome).where(Tome.filepath == str(filepath)))
    tome = result.scalar_one_or_none()

    if tome is None:
        tome = Tome(
            series_id=series.id,
            filename=filepath.name,
            filepath=str(filepath),
            file_format=file_format,
            file_size=file_size,
            number=parsed.get("number"),
            title=parsed.get("title"),
        )
        db.add(tome)
        await db.flush()
    else:
        tome.file_size = file_size
        tome.number = parsed.get("number")
        tome.title = parsed.get("title")
        tome.updated_at = datetime.utcnow()

    # Read comic metadata in thread pool (blocking I/O)
    try:
        page_count, metadata_dict = await asyncio.to_thread(_read_comic_info, filepath)
        tome.page_count = page_count
        tome.status = "ok"

        if metadata_dict:
            has_data = any(metadata_dict.get(f) for f in ("Title", "Series", "Number", "Writer", "Publisher"))
            tome.has_metadata = has_data
            meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
            meta = meta_result.scalar_one_or_none()
            if meta is None:
                meta = Metadata(tome_id=tome.id)
                db.add(meta)
            for field in Metadata.__table__.columns.keys():
                if field in ("id", "tome_id"):
                    continue
                val = metadata_dict.get(field)
                if val is not None and str(val).strip():
                    setattr(meta, field, str(val))
        else:
            tome.has_metadata = False

    except Exception as e:
        tome.status = "error"
        tome.error_msg = str(e)[:500]

    await db.flush()
    return tome
