from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Tome
from ..services.cover_cache import ensure_cover, ensure_thumb

router = APIRouter(prefix="/api/covers", tags=["covers"], dependencies=[Depends(auth_required)])

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
async def get_cover(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")

    cover_path = await ensure_cover(tome_id, tome.filepath)
    if cover_path is None:
        return Response(content=_grey_placeholder(), media_type="image/jpeg")

    import hashlib, os
    mtime = os.path.getmtime(str(cover_path))
    etag = hashlib.md5(f"{tome_id}:{mtime}".encode()).hexdigest()
    return FileResponse(
        str(cover_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, must-revalidate", "ETag": etag},
    )


@router.get("/{tome_id}/thumb")
async def get_thumb(tome_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
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
