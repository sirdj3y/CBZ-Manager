from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Tome, Series, User
from ..models.schemas import NotificationsOut, NewContentItemOut
from ..services.hidden_series import get_user_excluded_series_ids

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_permission("library.read"))])

# items = historique persistant des N derniers ajouts, qu'ils aient déjà été vus ou non — ne
# se vide plus après consultation (contrairement à avant, où "nouveau depuis la dernière
# fois" redevenait vide dès qu'on avait tout vu). count = uniquement les vraiment nouveaux
# depuis la dernière consultation (total réel, non plafonné) — c'est lui qui pilote la
# pastille, qui elle disparaît normalement une fois tout vu.
NOTIF_CAP = 10


@router.get("", response_model=NotificationsOut)
async def get_notifications(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # notifications_last_seen_at est toujours renseigné à la création du compte (voir
    # services/auth.py) — le repli sur created_at n'est qu'un filet de sécurité pour les
    # comptes déjà en base avant l'ajout de cette colonne.
    since = current_user.notifications_last_seen_at or current_user.created_at
    excluded = await get_user_excluded_series_ids(db, current_user)

    tome_q = select(Tome, Series.name).join(Series, Series.id == Tome.series_id)
    if excluded:
        tome_q = tome_q.where(Tome.series_id.notin_(excluded))
    recent_tomes = (await db.execute(tome_q.order_by(Tome.created_at.desc()).limit(NOTIF_CAP))).all()

    series_q = select(Series)
    if excluded:
        series_q = series_q.where(Series.id.notin_(excluded))
    recent_series = (await db.execute(series_q.order_by(Series.created_at.desc()).limit(NOTIF_CAP))).scalars().all()

    # Couverture des séries récentes : cover_tome_id si fixé, sinon le tome au plus petit
    # "number" — une seule requête groupée plutôt qu'une par série (même pattern que
    # routers/opds.py::opds_series_list).
    first_tome_by_series: dict[int, int] = {}
    if recent_series:
        rows = (await db.execute(
            select(Tome.id, Tome.series_id)
            .where(Tome.series_id.in_([s.id for s in recent_series]))
            .order_by(Tome.series_id, Tome.number)
        )).all()
        for tid, sid in rows:
            first_tome_by_series.setdefault(sid, tid)

    items = [
        NewContentItemOut(
            type="tome", id=tome.id, title=tome.title or tome.filename,
            series_id=tome.series_id, series_name=series_name,
            cover_url=f"/api/covers/{tome.id}", created_at=tome.created_at,
        )
        for tome, series_name in recent_tomes
    ]
    for s in recent_series:
        cover_tome_id = s.cover_tome_id or first_tome_by_series.get(s.id)
        items.append(NewContentItemOut(
            type="series", id=s.id, title=s.name,
            series_id=s.id, series_name=s.name,
            cover_url=f"/api/covers/{cover_tome_id}" if cover_tome_id else None,
            created_at=s.created_at,
        ))

    items.sort(key=lambda i: i.created_at, reverse=True)
    items = items[:NOTIF_CAP]

    tome_count_q = select(func.count()).select_from(Tome).where(Tome.created_at > since)
    if excluded:
        tome_count_q = tome_count_q.where(Tome.series_id.notin_(excluded))
    series_count_q = select(func.count()).select_from(Series).where(Series.created_at > since)
    if excluded:
        series_count_q = series_count_q.where(Series.id.notin_(excluded))
    tome_count = (await db.execute(tome_count_q)).scalar() or 0
    series_count = (await db.execute(series_count_q)).scalar() or 0

    return NotificationsOut(count=tome_count + series_count, items=items)


@router.post("/mark-seen")
async def mark_seen(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.notifications_last_seen_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}
