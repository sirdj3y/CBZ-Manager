import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user, require_permission
from ..models.db_models import Series, SmartList, User
from ..models.schemas import SmartListFieldOut, SmartListIn, SmartListOut, SmartListPatchIn, SmartListReorderIn, SeriesOut, TomeOut
from ..services import smart_lists as smart_lists_service
from .library import build_series_out_list
from .tomes import _build_tome_out, _user_data_map

router = APIRouter(prefix="/api/smart-lists", tags=["smart-lists"], dependencies=[Depends(require_permission("library.read"))])


def _rules_dict(smart_list: SmartList) -> dict:
    try:
        return json.loads(smart_list.rules) if smart_list.rules else {"groups": []}
    except json.JSONDecodeError:
        return {"groups": []}


async def _to_out(db: AsyncSession, sl: SmartList, current_user: User, username_map: dict[int, str]) -> SmartListOut:
    q = await smart_lists_service.build_smart_list_query(db, sl, current_user)
    count_q = select(func.count()).select_from(q.order_by(None).subquery())
    result_count = (await db.execute(count_q)).scalar() or 0
    return SmartListOut(
        id=sl.id, name=sl.name, owner_id=sl.owner_id, owner_username=username_map.get(sl.owner_id),
        shared=sl.shared, is_default=sl.is_default,
        rules=_rules_dict(sl), result_count=result_count,
        can_edit=current_user.is_admin or sl.owner_id == current_user.id,
        created_at=sl.created_at, updated_at=sl.updated_at,
    )


async def _get_owned_or_admin(db: AsyncSession, smart_list_id: int, current_user: User) -> SmartList:
    sl = (await db.execute(select(SmartList).where(SmartList.id == smart_list_id))).scalar_one_or_none()
    if sl is None:
        raise HTTPException(status_code=404, detail="Smart list introuvable")
    if not (current_user.is_admin or sl.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Seul le propriétaire (ou un administrateur) peut modifier cette liste")
    return sl


@router.get("/fields", response_model=list[SmartListFieldOut])
async def get_fields():
    return smart_lists_service.get_fields_catalog()


@router.get("", response_model=list[SmartListOut])
async def list_smart_lists(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = select(SmartList).where((SmartList.owner_id == current_user.id) | (SmartList.shared == True))
    rows = (await db.execute(q.order_by(SmartList.sort_order, SmartList.id))).scalars().all()
    owner_ids = {sl.owner_id for sl in rows}
    username_map = {}
    if owner_ids:
        username_map = dict((await db.execute(select(User.id, User.username).where(User.id.in_(owner_ids)))).all())
    return [await _to_out(db, sl, current_user, username_map) for sl in rows]


@router.post("", response_model=SmartListOut)
async def create_smart_list(body: SmartListIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rules = body.rules.model_dump()
    try:
        smart_lists_service.validate_rules(rules, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    max_order = (await db.execute(select(func.max(SmartList.sort_order)))).scalar()
    sl = SmartList(
        name=name, owner_id=current_user.id, shared=body.shared,
        rules=json.dumps(rules, ensure_ascii=False),
        sort_order=(max_order or 0) + 1,
    )
    db.add(sl)
    await db.commit()
    await db.refresh(sl)
    return await _to_out(db, sl, current_user, {current_user.id: current_user.username})


@router.post("/{smart_list_id}/duplicate", response_model=SmartListOut)
async def duplicate_smart_list(smart_list_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Copie une liste visible (la sienne ou une partagée) — mêmes règles, mais toujours
    privée et non par défaut au départ : à l'utilisateur de la partager/publier lui-même une
    fois ajustée, plutôt que de dupliquer une liste partagée directement en partagé (risque de
    multiplier les doublons visibles par tout le monde sans le vouloir)."""
    sl = (await db.execute(select(SmartList).where(SmartList.id == smart_list_id))).scalar_one_or_none()
    if sl is None or not (sl.shared or sl.owner_id == current_user.id or current_user.is_admin):
        raise HTTPException(status_code=404, detail="Smart list introuvable")
    max_order = (await db.execute(select(func.max(SmartList.sort_order)))).scalar()
    copy = SmartList(
        name=f"{sl.name} (copie)", owner_id=current_user.id, shared=False, is_default=False,
        rules=sl.rules, sort_order=(max_order or 0) + 1,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return await _to_out(db, copy, current_user, {current_user.id: current_user.username})


@router.patch("/reorder")
async def reorder_smart_lists(body: SmartListReorderIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ordre d'affichage partagé (voir SmartList.sort_order) — n'importe quel utilisateur
    peut réordonner, même les listes des autres : c'est un simple ordre d'affichage, pas une
    donnée de contenu, cohérent avec le reste de la fonctionnalité (n'importe qui peut créer
    une liste partagée). Seules les listes visibles par cet utilisateur (les siennes + les
    partagées) peuvent être réordonnées, pour ne pas permettre de deviner/altérer une liste
    privée d'un autre utilisateur via son id."""
    visible_ids = set((await db.execute(
        select(SmartList.id).where((SmartList.owner_id == current_user.id) | (SmartList.shared == True))
    )).scalars().all())
    unknown = set(body.ids) - visible_ids
    if unknown:
        raise HTTPException(status_code=404, detail="Une ou plusieurs listes sont introuvables")
    for i, smart_list_id in enumerate(body.ids):
        await db.execute(
            SmartList.__table__.update().where(SmartList.id == smart_list_id).values(sort_order=i)
        )
    await db.commit()
    return {"ok": True}


@router.patch("/{smart_list_id}", response_model=SmartListOut)
async def update_smart_list(smart_list_id: int, body: SmartListPatchIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sl = await _get_owned_or_admin(db, smart_list_id, current_user)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Nom requis")
        sl.name = name
    if body.shared is not None:
        sl.shared = body.shared
    if body.rules is not None:
        rules = body.rules.model_dump()
        try:
            smart_lists_service.validate_rules(rules, current_user.id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        sl.rules = json.dumps(rules, ensure_ascii=False)
    await db.commit()
    await db.refresh(sl)
    owner = (await db.execute(select(User.id, User.username).where(User.id == sl.owner_id))).first()
    username_map = {owner[0]: owner[1]} if owner else {}
    return await _to_out(db, sl, current_user, username_map)


@router.delete("/{smart_list_id}")
async def delete_smart_list(smart_list_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sl = await _get_owned_or_admin(db, smart_list_id, current_user)
    await db.delete(sl)
    await db.commit()
    return {"ok": True}


@router.get("/{smart_list_id}/tomes", response_model=list[TomeOut])
async def get_smart_list_tomes(smart_list_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sl = (await db.execute(select(SmartList).where(SmartList.id == smart_list_id))).scalar_one_or_none()
    if sl is None or not (sl.shared or sl.owner_id == current_user.id or current_user.is_admin):
        raise HTTPException(status_code=404, detail="Smart list introuvable")
    q = await smart_lists_service.build_smart_list_query(db, sl, current_user)
    try:
        rows = (await db.execute(q)).all()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    series_meta = (await db.execute(select(Series.id, Series.name, Series.hidden, Series.classification))).all()
    series_name_map = {r[0]: r[1] for r in series_meta}
    series_hidden_map = {r[0]: bool(r[2]) for r in series_meta}
    series_classification_map = {r[0]: r[3] for r in series_meta}
    user_data_map = await _user_data_map(db, current_user.id, [t.id for t, m in rows])
    return [
        _build_tome_out(
            t, m, user_data_map.get(t.id),
            series_hidden=series_hidden_map.get(t.series_id, False), series_name=series_name_map.get(t.series_id),
            series_classification=series_classification_map.get(t.series_id),
        )
        for t, m in rows
    ]


@router.get("/{smart_list_id}/series", response_model=list[SeriesOut])
async def get_smart_list_series(smart_list_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sl = (await db.execute(select(SmartList).where(SmartList.id == smart_list_id))).scalar_one_or_none()
    if sl is None or not (sl.shared or sl.owner_id == current_user.id or current_user.is_admin):
        raise HTTPException(status_code=404, detail="Smart list introuvable")
    try:
        series_ids = await smart_lists_service.get_smart_list_series_ids(db, sl, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not series_ids:
        return []
    series_list = (await db.execute(select(Series).where(Series.id.in_(series_ids)).order_by(Series.name))).scalars().all()
    return await build_series_out_list(db, series_list, current_user)
