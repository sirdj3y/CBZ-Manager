import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Tome, TomePagePanels, ReadingActivity, User
from ..models.schemas import HeartbeatIn
from ..services import page_extractor, panel_detector
from ..services.hidden_series import get_user_excluded_series_ids, assert_tomes_visible

router = APIRouter(prefix="/api/reader", tags=["reader"], dependencies=[Depends(require_permission("library.read"))])


@router.get("/{tome_id}/info")
async def reader_info(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    page_count = tome.page_count
    if page_count is None:
        try:
            page_count = await asyncio.to_thread(page_extractor.get_page_count, tome.filepath, tome.file_format)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fichier illisible : {e}")
        tome.page_count = page_count
        await db.commit()

    return {
        "tome_id": tome_id,
        "title": tome.title or tome.filename,
        "page_count": page_count,
        "file_format": tome.file_format,
    }


@router.get("/{tome_id}/page/{page_index}")
async def get_page(tome_id: int, page_index: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    try:
        img_bytes = await asyncio.to_thread(page_extractor.extract_page, tome.filepath, tome.file_format, page_index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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


@router.get("/{tome_id}/panels/{page_index}")
async def get_page_panels(tome_id: int, page_index: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Cases détectées sur cette page, triées dans l'ordre de lecture, pour l'option "Zoom
    sur les cases" du lecteur — calculées à la demande puis mises en cache (voir
    services/panel_detector.py), jamais recalculées une fois en base."""
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    cached = await db.execute(
        select(TomePagePanels).where(TomePagePanels.tome_id == tome_id, TomePagePanels.page_index == page_index)
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return {"panels": json.loads(row.panels_json)}

    try:
        img_bytes = await asyncio.to_thread(page_extractor.extract_page, tome.filepath, tome.file_format, page_index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur extraction: {str(e)}")

    try:
        panels = await asyncio.to_thread(panel_detector.detect_panels_sync, img_bytes, True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Détection impossible : {e}")

    db.add(TomePagePanels(tome_id=tome_id, page_index=page_index, panels_json=json.dumps(panels)))
    await db.commit()

    return {"panels": panels}


# Plafond par battement — le lecteur envoie l'écart depuis le dernier battement (voir
# ReaderView.vue::flushReadingTime), jamais une durée totale ; une valeur aberrante (bug
# client, horloge système modifiée, requête rejouée à la main) ne peut donc gonfler le
# compteur que de quelques minutes au pire, pas de plusieurs heures d'un coup.
MAX_HEARTBEAT_SECONDS = 120


@router.post("/{tome_id}/heartbeat")
async def reader_heartbeat(
    tome_id: int, body: HeartbeatIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Incrémente le temps de lecture actif du jour courant pour ce tome — voir
    ReadingActivity (agrégation par jour, pas de session précise à fusionner)."""
    await assert_tomes_visible(db, current_user, [tome_id])
    seconds = max(0, min(body.seconds, MAX_HEARTBEAT_SECONDS))
    if seconds == 0:
        return {"ok": True}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = (await db.execute(
        select(ReadingActivity).where(
            ReadingActivity.user_id == current_user.id,
            ReadingActivity.tome_id == tome_id,
            ReadingActivity.day == today,
        )
    )).scalar_one_or_none()
    if row is None:
        db.add(ReadingActivity(user_id=current_user.id, tome_id=tome_id, day=today, seconds=seconds))
    else:
        row.seconds += seconds
        row.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}
