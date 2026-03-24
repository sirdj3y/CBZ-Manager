import asyncio
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Tome

router = APIRouter(prefix="/api/reader", tags=["reader"], dependencies=[Depends(auth_required)])

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _get_cbz_pages(filepath: str) -> list[str]:
    """Return sorted list of image filenames inside a CBZ."""
    with zipfile.ZipFile(filepath, "r") as zf:
        names = [
            n for n in zf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTS
            and not n.startswith("__MACOSX")
        ]
        return sorted(names)


def _extract_cbz_page(filepath: str, page_index: int) -> bytes:
    pages = _get_cbz_pages(filepath)
    if page_index < 0 or page_index >= len(pages):
        raise IndexError(f"Page {page_index} hors limites ({len(pages)} pages)")
    with zipfile.ZipFile(filepath, "r") as zf:
        return zf.read(pages[page_index])


def _extract_cbr_page(filepath: str, page_index: int) -> bytes:
    import rarfile
    with rarfile.RarFile(filepath, "r") as rf:
        names = sorted([
            n for n in rf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTS
        ])
        if page_index < 0 or page_index >= len(names):
            raise IndexError(f"Page {page_index} hors limites ({len(names)} pages)")
        return rf.read(names[page_index])


def _extract_pdf_page(filepath: str, page_index: int) -> bytes:
    import fitz
    from PIL import Image
    import io
    doc = fitz.open(filepath)
    if page_index < 0 or page_index >= doc.page_count:
        raise IndexError(f"Page {page_index} hors limites ({doc.page_count} pages)")
    page = doc[page_index]
    mat = fitz.Matrix(1.5, 1.5)  # ~150 DPI
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("jpeg")
    doc.close()
    return img_bytes


def _get_page_count(filepath: str, fmt: str) -> int:
    if fmt == "cbz":
        return len(_get_cbz_pages(filepath))
    elif fmt == "cbr":
        import rarfile
        with rarfile.RarFile(filepath, "r") as rf:
            return len([n for n in rf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
    elif fmt == "pdf":
        import fitz
        doc = fitz.open(filepath)
        count = doc.page_count
        doc.close()
        return count
    return 0


@router.get("/{tome_id}/info")
async def reader_info(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    page_count = tome.page_count
    if page_count is None:
        page_count = await asyncio.to_thread(_get_page_count, tome.filepath, tome.file_format)
        tome.page_count = page_count
        await db.commit()

    return {
        "tome_id": tome_id,
        "title": tome.title or tome.filename,
        "page_count": page_count,
        "file_format": tome.file_format,
    }


@router.get("/{tome_id}/page/{page_index}")
async def get_page(tome_id: int, page_index: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    fmt = tome.file_format
    filepath = tome.filepath

    try:
        if fmt == "cbz":
            img_bytes = await asyncio.to_thread(_extract_cbz_page, filepath, page_index)
        elif fmt == "cbr":
            img_bytes = await asyncio.to_thread(_extract_cbr_page, filepath, page_index)
        elif fmt == "pdf":
            img_bytes = await asyncio.to_thread(_extract_pdf_page, filepath, page_index)
        else:
            raise HTTPException(status_code=400, detail=f"Format non supporté: {fmt}")
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur extraction: {str(e)}")

    # Determine content type
    content_type = "image/jpeg"
    if img_bytes[:4] == b"\x89PNG":
        content_type = "image/png"

    return Response(
        content=img_bytes,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )
