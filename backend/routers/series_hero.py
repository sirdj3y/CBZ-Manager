from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Series, User
from ..services import series_hero as series_hero_service
from ..services.hidden_series import get_user_excluded_series_ids, assert_series_visible

router = APIRouter(prefix="/api/series/{series_id}/hero", tags=["series_hero"])

_MEDIA_TYPE = {"background": "image/jpeg", "logo": "image/png", "character": "image/png"}
_VERSION_ATTR = {
    "background": "hero_background_version",
    "logo": "hero_logo_version",
    "character": "hero_character_version",
}


def _validate_kind(kind: str) -> None:
    if kind not in _MEDIA_TYPE:
        raise HTTPException(status_code=404, detail="Type d'image inconnu")


@router.get("/{kind}", dependencies=[Depends(require_permission("library.read"))])
async def get_series_hero(series_id: int, kind: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    _validate_kind(kind)
    if series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Série introuvable")
    path = series_hero_service.get_hero_path(series_id, kind)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Aucune image")
    return FileResponse(
        str(path), media_type=_MEDIA_TYPE[kind],
        headers={"Cache-Control": "public, max-age=604800, must-revalidate"},
    )


@router.post("/{kind}", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def upload_series_hero(
    series_id: int, kind: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_kind(kind)
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (10 Mo max)")
    try:
        series_hero_service.save_hero_image(series_id, kind, content)
    except Exception:
        raise HTTPException(status_code=400, detail="Image invalide")

    setattr(series, _VERSION_ATTR[kind], getattr(series, _VERSION_ATTR[kind]) + 1)
    await db.commit()
    return {_VERSION_ATTR[kind]: getattr(series, _VERSION_ATTR[kind])}


@router.delete("/{kind}", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def delete_series_hero(series_id: int, kind: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    _validate_kind(kind)
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    series_hero_service.delete_hero_image(series_id, kind)
    setattr(series, _VERSION_ATTR[kind], getattr(series, _VERSION_ATTR[kind]) + 1)
    await db.commit()
    return {_VERSION_ATTR[kind]: getattr(series, _VERSION_ATTR[kind])}
