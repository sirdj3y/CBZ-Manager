import asyncio
from pathlib import Path
from typing import Optional
from PIL import Image
import io

from ..config import settings


def get_cover_path(tome_id: int) -> Path:
    return Path(settings.COVER_CACHE_DIR) / f"{tome_id}.jpg"


def get_thumb_path(tome_id: int) -> Path:
    return Path(settings.COVER_CACHE_DIR) / f"{tome_id}_thumb.jpg"


def _resize_and_save(img_bytes: bytes, dest: Path, max_width: int) -> None:
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPEG", quality=85, optimize=True, progressive=True)


def _extract_cover_sync(tome_path: str) -> Optional[bytes]:
    """Extract first page bytes as cover."""
    import zipfile
    path = Path(tome_path)
    ext = path.suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    if ext in (".cbz", ".zip"):
        try:
            with zipfile.ZipFile(tome_path, "r") as zf:
                names = sorted([
                    n for n in zf.namelist()
                    if Path(n).suffix.lower() in image_exts
                    and not n.startswith("__MACOSX")
                ])
                if names:
                    return zf.read(names[0])
        except Exception:
            pass

    elif ext in (".cbr", ".rar"):
        try:
            import rarfile
            with rarfile.RarFile(tome_path, "r") as rf:
                names = sorted([
                    n for n in rf.namelist()
                    if Path(n).suffix.lower() in image_exts
                ])
                if names:
                    return rf.read(names[0])
        except Exception:
            pass

    elif ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(tome_path)
            if doc.page_count > 0:
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
                img_bytes = pix.tobytes("jpeg")
                doc.close()
                return img_bytes
        except Exception:
            pass

    return None


async def ensure_cover(tome_id: int, tome_path: str) -> Optional[Path]:
    cover_path = get_cover_path(tome_id)
    if cover_path.exists():
        return cover_path

    cover_bytes = await asyncio.to_thread(_extract_cover_sync, tome_path)
    if not cover_bytes:
        return None

    await asyncio.to_thread(_resize_and_save, cover_bytes, cover_path, 400)

    # Also create thumb
    thumb_path = get_thumb_path(tome_id)
    await asyncio.to_thread(_resize_and_save, cover_bytes, thumb_path, 150)

    return cover_path


async def ensure_thumb(tome_id: int, tome_path: str) -> Optional[Path]:
    thumb_path = get_thumb_path(tome_id)
    if thumb_path.exists():
        return thumb_path
    # ensure_cover creates the thumb as a side effect
    await ensure_cover(tome_id, tome_path)
    return thumb_path if thumb_path.exists() else None


def invalidate_cover(tome_id: int) -> None:
    """Remove cached covers so they get regenerated."""
    for p in (get_cover_path(tome_id), get_thumb_path(tome_id)):
        if p.exists():
            p.unlink()
