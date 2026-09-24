import asyncio
from pathlib import Path
from typing import Optional
from PIL import Image
import io

from ..config import settings
from .archive_format import detect_archive_ext
from .archive_safety import read_entry_bounded


def get_cover_path(tome_id: int) -> Path:
    return Path(settings.COVER_CACHE_DIR) / f"{tome_id}.jpg"


def get_thumb_path(tome_id: int) -> Path:
    return Path(settings.COVER_CACHE_DIR) / f"{tome_id}_thumb.jpg"


def _resize_and_save(img_bytes: bytes, dest: Path, max_width: int) -> tuple[int, int]:
    """Retourne la résolution ORIGINALE (avant redimensionnement) — c'est celle-ci qui a un
    sens pour l'utilisateur (qualité de la page source), pas la taille du cache."""
    img = Image.open(io.BytesIO(img_bytes))
    original_size = (img.width, img.height)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPEG", quality=85, optimize=True, progressive=True)
    return original_size


def _extract_cover_sync(tome_path: str) -> Optional[bytes]:
    """Extract first page bytes as cover."""
    import zipfile
    path = Path(tome_path)
    # Octets magiques plutôt que l'extension — voir archive_format.py.
    ext = detect_archive_ext(path)
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
                    with zf.open(names[0]) as entry:
                        return read_entry_bounded(entry)
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
                    with rf.open(names[0]) as entry:
                        return read_entry_bounded(entry)
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


async def ensure_cover(tome_id: int, tome_path: str) -> tuple[Optional[Path], Optional[tuple[int, int]]]:
    """Retourne (chemin du cache, résolution originale) — la résolution n'est renseignée que
    lors d'une extraction fraîche (cache absent) : sur un cache-hit, rouvrir le fichier
    juste pour ça serait un aller-retour disque inutile à chaque affichage de couverture, le
    but étant de peupler Tome.cover_width/height une seule fois (voir routers/covers.py)."""
    cover_path = get_cover_path(tome_id)
    if cover_path.exists():
        return cover_path, None

    cover_bytes = await asyncio.to_thread(_extract_cover_sync, tome_path)
    if not cover_bytes:
        return None, None

    original_size = await asyncio.to_thread(_resize_and_save, cover_bytes, cover_path, 400)

    # Also create thumb
    thumb_path = get_thumb_path(tome_id)
    await asyncio.to_thread(_resize_and_save, cover_bytes, thumb_path, 150)

    return cover_path, original_size


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
