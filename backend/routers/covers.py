from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Tome, User
from ..services.cover_cache import ensure_cover, ensure_thumb
from ..services.hidden_series import get_user_excluded_series_ids

router = APIRouter(prefix="/api/covers", tags=["covers"], dependencies=[Depends(require_permission("library.read"))])

_PLACEHOLDER = None  # lazy-loaded grey placeholder bytes


def _grey_placeholder() -> bytes:
    global _PLACEHOLDER
    if _PLACEHOLDER is None:
        from PIL import Image
        import io
        img = Image.new("RGB", (300, 430), color=(50, 50, 60))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        _PLACEHOLDER = buf.getvalue()
    return _PLACEHOLDER


@router.get("/{tome_id}")
async def get_cover(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    cover_path, original_size = await ensure_cover(tome_id, tome.filepath)
    if cover_path is None:
        return Response(content=_grey_placeholder(), media_type="image/jpeg")

    # Peuplement paresseux, une seule fois (voir ensure_cover) : original_size n'est
    # renseigné que juste après une extraction fraîche, jamais sur un cache-hit.
    if original_size is not None and tome.cover_width is None:
        tome.cover_width, tome.cover_height = original_size
        await db.commit()

    import hashlib, os
    mtime = os.path.getmtime(str(cover_path))
    etag = hashlib.md5(f"{tome_id}:{mtime}".encode()).hexdigest()
    return FileResponse(
        str(cover_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, must-revalidate", "ETag": etag},
    )


@router.get("/{tome_id}/thumb")
async def get_thumb(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    thumb_path = await ensure_thumb(tome_id, tome.filepath)
    if thumb_path is None:
        return Response(content=_grey_placeholder(), media_type="image/jpeg")

    import hashlib, os
    mtime = os.path.getmtime(str(thumb_path))
    etag = hashlib.md5(f"{tome_id}_thumb:{mtime}".encode()).hexdigest()
    return FileResponse(
        str(thumb_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, must-revalidate", "ETag": etag},
    )
