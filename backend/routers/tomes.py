from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import asyncio
import json
import re
import logging

from ..config import settings

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Tome, Metadata, UserTomeData, Series, User
from ..models.schemas import TomeOut, MetadataOut, MetadataIn, ParseFilenameOut, UserDataIn, ReadingProgressOut, ReadingProgressIn, RenameIn, RenameBulkIn, RenameToIn, RenameBulkToIn, MoveTomesIn, DeleteBulkIn, MetadataBulkIn
from ..services.filename_parser import parse_filename
from ..services.metadata_writer import write_metadata
from ..services.archive import stream_zip
from ..services.user_tome_data import get_user_tome_data, get_or_create_user_tome_data
from ..services.hidden_series import assert_tomes_visible
from ..services.hidden_series import get_user_hidden_series_ids, get_user_excluded_series_ids, get_user_age_restricted_series_ids, assert_tomes_visible
from .auth import get_client_ip


def apply_pattern(pattern: str, tome: Tome, meta: Metadata | None) -> str:
    p = Path(tome.filepath)
    ext = p.suffix
    name = p.stem
    # Un one-shot n'appartient à aucune suite numérotée — le modèle configuré (avec
    # {Série}/{Numéro}) n'a pas de sens pour lui, quel que soit le modèle demandé par
    # l'appelant (import automatique ou renommage manuel) : juste le titre.
    result = "{Titre}" if tome.is_oneshot else pattern
    result = result.replace("{Fichier}", name)
    result = result.replace("{Filename}", name)
    result = result.replace("{Série}", meta.Series if meta and meta.Series else "")
    result = result.replace("{Series}", meta.Series if meta and meta.Series else "")
    result = result.replace("{Numéro}", meta.Number if meta and meta.Number else "")
    result = result.replace("{Number}", meta.Number if meta and meta.Number else "")
    result = result.replace("{Titre}", meta.Title if meta and meta.Title else "")
    result = result.replace("{Title}", meta.Title if meta and meta.Title else "")
    result = result.replace("{Année}", meta.Year if meta and meta.Year else "")
    result = result.replace("{Year}", meta.Year if meta and meta.Year else "")
    result = result.replace("{Dessinateur}", meta.Penciller if meta and meta.Penciller else "")
    result = result.replace("{Scénariste}", meta.Writer if meta and meta.Writer else "")
    result = result.replace("{Writer}", meta.Writer if meta and meta.Writer else "")
    result = result.replace("{Éditeur}", meta.Publisher if meta and meta.Publisher else "")
    result = result.replace("{Publisher}", meta.Publisher if meta and meta.Publisher else "")
    result = re.sub(r'[<>:"/\\|?*]', '_', result)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    result = re.sub(r'_+', '_', result).strip("_").strip()
    if not result:
        result = name
    return result + ext


router = APIRouter(prefix="/api/tomes", tags=["tomes"], dependencies=[Depends(require_permission("library.read"))])


def _cover_url(tome_id: int, updated_at=None) -> str:
    if updated_at is not None:
        v = int(updated_at.timestamp()) if hasattr(updated_at, "timestamp") else str(updated_at).replace(" ", "")
        return f"/api/covers/{tome_id}?v={v}"
    return f"/api/covers/{tome_id}"


def _build_tome_out(
    t: Tome, meta: Metadata | None = None, user_data: UserTomeData | None = None,
    series_hidden: bool = False, series_name: str | None = None, series_classification: str | None = None,
) -> TomeOut:
    tags: list[str] = []
    if user_data and user_data.tag_list:
        try:
            tags = json.loads(user_data.tag_list)
        except Exception:
            tags = []
    community_rating = None
    if meta and meta.CommunityRating:
        try:
            community_rating = float(meta.CommunityRating)
        except ValueError:
            community_rating = None
    return TomeOut(
        id=t.id, series_id=t.series_id, series_name=series_name, filename=t.filename,
        filepath=t.filepath, number=t.number, title=t.title,
        file_format=t.file_format, file_size=t.file_size,
        page_count=t.page_count, has_metadata=t.has_metadata,
        cover_cached=t.cover_cached, cover_url=_cover_url(t.id, t.updated_at),
        cover_width=t.cover_width, cover_height=t.cover_height,
        status=t.status, created_at=t.created_at, updated_at=t.updated_at,
        hidden=t.hidden, series_hidden=series_hidden, is_oneshot=t.is_oneshot,
        classification=series_classification,
        user_rating=user_data.rating if user_data else None,
        user_notes=user_data.notes if user_data else None,
        user_tags=tags,
        user_is_read=user_data.is_read if user_data else False,
        writer=meta.Writer if meta else None,
        penciller=meta.Penciller if meta else None,
        publisher=meta.Publisher if meta else None,
        genre=meta.Genre if meta else None,
        year=meta.Year if meta else None,
        community_rating=community_rating,
    )


async def _user_data_map(db: AsyncSession, user_id: int, tome_ids: list[int]) -> dict[int, UserTomeData]:
    """Une seule requête groupée pour un lot de tomes, plutôt qu'une requête par tome —
    même pattern que series_hidden_map/series_name_map juste au-dessus."""
    if not tome_ids:
        return {}
    rows = (await db.execute(
        select(UserTomeData).where(UserTomeData.user_id == user_id, UserTomeData.tome_id.in_(tome_ids))
    )).scalars().all()
    return {u.tome_id: u for u in rows}


@router.get("", response_model=list[TomeOut])
async def list_all_tomes(show_hidden: bool = False, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..models.db_models import Series
    from sqlalchemy import text

    # Récupère le mapping series_id → hidden/nom/classification
    series_rows = (await db.execute(select(Series.id, Series.name, Series.hidden, Series.classification))).all()
    series_hidden_map: dict[int, bool] = {r[0]: bool(r[2]) for r in series_rows}
    series_name_map: dict[int, str] = {r[0]: r[1] for r in series_rows}
    series_classification_map: dict[int, str | None] = {r[0]: r[3] for r in series_rows}

    q = (
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .order_by(Tome.series_id, Tome.number)
    )
    # show_hidden ne lève le masquage global (Series.hidden/Tome.hidden) que pour un admin —
    # sinon un simple ?show_hidden=true dans l'URL suffisait à un non-admin pour voir des
    # séries masquées à tout le monde, alors que les routes de détail (fiche tome/série)
    # continuaient de les bloquer. Le masquage personnel ci-dessous reste, lui, toujours
    # appliqué indépendamment de show_hidden, y compris pour un admin.
    if not show_hidden or not current_user.is_admin:
        hidden_series_ids = [sid for sid, h in series_hidden_map.items() if h]
        q = q.where(Tome.hidden == False)
        if hidden_series_ids:
            q = q.where(Tome.series_id.notin_(hidden_series_ids))
    # Masquage personnel — indépendant de show_hidden (voir list_series pour le même
    # raisonnement) : reste invisible pour cet utilisateur même si show_hidden=true. Le
    # plafond de public conseillé (age_rating_limit) s'applique de la même façon.
    if not current_user.is_admin:
        excluded_ids = await get_user_hidden_series_ids(db, current_user.id)
        excluded_ids |= await get_user_age_restricted_series_ids(db, current_user.age_rating_limit)
        if excluded_ids:
            q = q.where(Tome.series_id.notin_(excluded_ids))
    result = await db.execute(q)
    rows = result.all()
    user_data_map = await _user_data_map(db, current_user.id, [t.id for t, m in rows])
    return [
        _build_tome_out(
            t, m, user_data_map.get(t.id),
            series_hidden=series_hidden_map.get(t.series_id, False), series_name=series_name_map.get(t.series_id),
            series_classification=series_classification_map.get(t.series_id),
        )
        for t, m in rows
    ]


@router.get("/recent", response_model=list[TomeOut])
async def list_recent_tomes(limit: int = 20, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..models.db_models import Series

    series_rows = (await db.execute(select(Series.id, Series.hidden))).all()
    hidden_series_ids = {sid for sid, h in series_rows if h}
    if not current_user.is_admin:
        hidden_series_ids |= await get_user_hidden_series_ids(db, current_user.id)
        hidden_series_ids |= await get_user_age_restricted_series_ids(db, current_user.age_rating_limit)

    q = (
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.hidden == False)
        .order_by(Tome.created_at.desc())
        .limit(limit)
    )
    if hidden_series_ids:
        q = q.where(Tome.series_id.notin_(hidden_series_ids))
    result = await db.execute(q)
    rows = result.all()
    user_data_map = await _user_data_map(db, current_user.id, [t.id for t, m in rows])
    return [_build_tome_out(t, m, user_data_map.get(t.id)) for t, m in rows]


@router.get("/in-progress", response_model=list[dict])
async def list_in_progress(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..models.db_models import Series
    q = (
        select(UserTomeData, Tome, Metadata)
        .join(Tome, Tome.id == UserTomeData.tome_id)
        .join(Series, Series.id == Tome.series_id)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(UserTomeData.user_id == current_user.id, UserTomeData.last_page > 0, UserTomeData.is_read == False)
        .where(Tome.hidden == False, Series.hidden == False)
        .order_by(UserTomeData.updated_at.desc())
        .limit(12)
    )
    if not current_user.is_admin:
        excluded_ids = await get_user_hidden_series_ids(db, current_user.id)
        excluded_ids |= await get_user_age_restricted_series_ids(db, current_user.age_rating_limit)
        if excluded_ids:
            q = q.where(Tome.series_id.notin_(excluded_ids))
    result = await db.execute(q)
    rows = result.all()
    out = []
    for ud, tome, meta in rows:
        t = _build_tome_out(tome, meta, ud)
        out.append({
            **t.model_dump(),
            "last_page": ud.last_page,
            "progress_pct": round(ud.last_page / tome.page_count * 100) if tome.page_count else 0,
        })
    return out


@router.get("/tags", response_model=list[str])
async def list_tags(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(UserTomeData.tag_list).where(UserTomeData.user_id == current_user.id, UserTomeData.tag_list.isnot(None))
    )
    all_tags: set[str] = set()
    for (tag_list,) in result.all():
        try:
            all_tags.update(json.loads(tag_list))
        except Exception:
            pass
    return sorted(all_tags)


@router.post("/rename-bulk", dependencies=[Depends(require_permission("library.rename"))])
async def rename_bulk(body: RenameBulkIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await assert_tomes_visible(db, current_user, body.ids)
    ok = 0
    errors = []
    for tome_id in body.ids:
        result = await db.execute(
            select(Tome, Metadata)
            .outerjoin(Metadata, Metadata.tome_id == Tome.id)
            .where(Tome.id == tome_id)
        )
        row = result.first()
        if row is None:
            errors.append(f"id={tome_id} : introuvable")
            continue
        tome, meta = row
        try:
            new_name = apply_pattern(body.pattern, tome, meta)
            if new_name == Path(tome.filepath).name:
                continue
            new_path = Path(tome.filepath).parent / new_name
            if new_path.exists():
                errors.append(f"{tome.filename} : fichier cible déjà existant")
                continue
            Path(tome.filepath).rename(new_path)
            tome.filename = new_name
            tome.filepath = str(new_path)
            tome.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(tome)
            ok += 1
        except Exception as e:
            errors.append(f"{tome.filename} : {e}")
    return {"ok": ok, "errors": errors}


@router.post("/move", dependencies=[Depends(require_permission("library.move"))])
async def move_tomes(body: MoveTomesIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Déplace des tomes (potentiellement de séries différentes) vers une série existante :
    fichier déplacé sur le disque + series_id/filepath mis à jour en base. Le champ Series
    des métadonnées (DB + ComicInfo.xml pour les CBZ) est mis à jour vers le nom de la série
    cible, et tome_count est recalculé pour la cible et les séries sources non vidées. Si une
    série source se retrouve vide après le déplacement, elle est supprimée (dossier + DB),
    comme lors de la suppression du dernier tome d'une série (voir delete_tome_file)."""
    from ..services.activity import log as activity_log

    await assert_tomes_visible(db, current_user, body.tome_ids)
    target = (await db.execute(select(Series).where(Series.id == body.target_series_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Série de destination introuvable")
    # Les sources étaient déjà contrôlées, la destination ne l'était pas : sans ça, un
    # utilisateur avec library.move mais sans accès à une série masquée/restreinte pouvait y
    # déplacer des tomes visibles en connaissant seulement son id.
    from ..services.hidden_series import assert_series_visible
    await assert_series_visible(db, current_user, [body.target_series_id])
    target_folder = Path(target.folder_path)

    ok = 0
    errors: list[str] = []
    source_series_ids: set[int] = set()
    moved_tomes: list[Tome] = []

    tomes_by_id = {
        t.id: t for t in (await db.execute(
            select(Tome).where(Tome.id.in_(body.tome_ids))
        )).scalars().all()
    }

    for tome_id in body.tome_ids:
        tome = tomes_by_id.get(tome_id)
        if tome is None:
            errors.append(f"id={tome_id} : introuvable")
            continue
        if tome.series_id == target.id:
            continue  # déjà dans la série cible

        old_path = Path(tome.filepath)
        new_path = target_folder / old_path.name
        if new_path.exists():
            errors.append(f"{tome.filename} : un fichier de ce nom existe déjà dans « {target.name} »")
            continue

        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)
        except OSError as e:
            errors.append(f"{tome.filename} : {e}")
            continue

        source_series_ids.add(tome.series_id)
        tome.series_id = target.id
        tome.filepath = str(new_path)
        tome.updated_at = datetime.utcnow()
        moved_tomes.append(tome)
        ok += 1

    await db.commit()

    # Met à jour le champ Series des métadonnées (DB + fichier ComicInfo.xml pour les CBZ) —
    # sinon le tome garde le nom de l'ancienne série dans ses métadonnées malgré le déplacement.
    if moved_tomes:
        meta_rows = (await db.execute(
            select(Metadata).where(Metadata.tome_id.in_([t.id for t in moved_tomes]))
        )).scalars().all()
        meta_by_tome = {m.tome_id: m for m in meta_rows}

        write_semaphore = asyncio.Semaphore(4)

        async def _write_series_field(tome: Tome, meta: Metadata | None):
            if tome.file_format != "cbz":
                return
            full_fields = {
                k: getattr(meta, k) for k in Metadata.__table__.columns.keys()
                if k not in ("id", "tome_id")
            } if meta else {}
            full_fields["Series"] = target.name
            async with write_semaphore:
                try:
                    await write_metadata(tome.filepath, full_fields)
                except Exception as e:
                    logging.warning(f"Could not update ComicInfo.xml for {tome.filepath}: {e}")

        await asyncio.gather(*[_write_series_field(t, meta_by_tome.get(t.id)) for t in moved_tomes])

        for tome in moved_tomes:
            meta = meta_by_tome.get(tome.id)
            if meta is None:
                meta = Metadata(tome_id=tome.id)
                db.add(meta)
            meta.Series = target.name
        await db.commit()

    # Nettoyage des séries sources devenues vides — même logique que delete_tome_file —
    # et recalcul de tome_count pour celles qui restent non vides.
    deleted_series_names = []
    for sid in source_series_ids:
        remaining = (await db.execute(select(func.count()).select_from(Tome).where(Tome.series_id == sid))).scalar()
        series = (await db.execute(select(Series).where(Series.id == sid))).scalar_one_or_none()
        if series is None:
            continue
        if remaining:
            series.tome_count = remaining
            continue
        try:
            folder = Path(series.folder_path)
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        except Exception as e:
            logging.warning(f"Could not delete folder {series.folder_path}: {e}")
        deleted_series_names.append(series.name)
        await db.delete(series)

    # tome_count de la série cible.
    target.tome_count = (await db.execute(
        select(func.count()).select_from(Tome).where(Tome.series_id == target.id)
    )).scalar()

    await db.commit()

    msg = f"{ok} album(s) déplacé(s) vers « {target.name} »"
    if deleted_series_names:
        msg += f" ({', '.join(deleted_series_names)} supprimée(s), devenue(s) vide(s))"
    await activity_log(db, "move_tomes", msg, status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": ok, "errors": errors, "deleted_series": deleted_series_names}


@router.post("/delete-bulk", dependencies=[Depends(require_permission("library.delete"))])
async def delete_tomes_bulk(body: DeleteBulkIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Supprime plusieurs tomes (fichier + entrée DB + cache cover), potentiellement de
    séries différentes. Même nettoyage des séries devenues vides que la suppression à
    l'unité (delete_tome_file) / le déplacement en lot (move_tomes)."""
    from ..services.activity import log as activity_log

    await assert_tomes_visible(db, current_user, body.tome_ids)
    cover_dir = Path(settings.COVER_CACHE_DIR)
    ok = 0
    errors: list[str] = []
    source_series_ids: set[int] = set()

    for tome_id in body.tome_ids:
        tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
        if tome is None:
            errors.append(f"id={tome_id} : introuvable")
            continue
        try:
            Path(tome.filepath).unlink(missing_ok=True)
        except Exception as e:
            errors.append(f"{tome.filename} : {e}")
            continue
        for f in [cover_dir / f"{tome_id}.jpg", cover_dir / f"{tome_id}_thumb.jpg"]:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        source_series_ids.add(tome.series_id)
        await db.delete(tome)
        ok += 1

    await db.commit()

    deleted_series_names = []
    for sid in source_series_ids:
        remaining = (await db.execute(select(func.count()).select_from(Tome).where(Tome.series_id == sid))).scalar()
        series = (await db.execute(select(Series).where(Series.id == sid))).scalar_one_or_none()
        if series is None:
            continue
        if remaining:
            series.tome_count = remaining
            continue
        try:
            folder = Path(series.folder_path)
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        except Exception as e:
            logging.warning(f"Could not delete folder {series.folder_path}: {e}")
        deleted_series_names.append(series.name)
        await db.delete(series)
    await db.commit()

    msg = f"{ok} album(s) supprimé(s) en lot"
    if deleted_series_names:
        msg += f" ({', '.join(deleted_series_names)} supprimée(s), devenue(s) vide(s))"
    await activity_log(db, "delete_tome", msg, status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": ok, "errors": errors, "deleted_series": deleted_series_names}


@router.put("/metadata-bulk", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def update_metadata_bulk(body: MetadataBulkIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Applique les champs fournis (non vides) à tous les tomes CBZ sélectionnés, en
    conservant leurs autres métadonnées existantes — même logique de fusion que l'édition
    en lot d'une série (update_series_metadata). Écrase volontairement les champs fournis
    (contrairement à la complétion Bedetheque) : c'est une édition manuelle explicite."""
    from ..services.metadata_writer import write_metadata
    from ..services.activity import log as activity_log

    await assert_tomes_visible(db, current_user, body.tome_ids)
    fields = {k: v.strip() for k, v in body.fields.items() if v and v.strip()}
    if not fields:
        return {"ok": 0, "errors": 0}

    tomes_result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id.in_(body.tome_ids), Tome.file_format == "cbz")
    )
    rows = tomes_result.all()

    write_semaphore = asyncio.Semaphore(4)

    async def _write_one(tome: Tome, meta: Metadata | None) -> tuple[Tome, bool]:
        full_fields = {
            k: getattr(meta, k) for k in Metadata.__table__.columns.keys()
            if k not in ("id", "tome_id")
        } if meta else {}
        full_fields.update(fields)
        async with write_semaphore:
            try:
                await write_metadata(tome.filepath, full_fields)
                return (tome, True)
            except Exception:
                return (tome, False)

    results = await asyncio.gather(*[_write_one(t, m) for t, m in rows])
    meta_by_tome = {m.tome_id: m for _, m in rows if m is not None}

    errors = 0
    ok = 0
    for tome, success in results:
        if not success:
            errors += 1
            continue
        meta = meta_by_tome.get(tome.id)
        if meta is None:
            meta = Metadata(tome_id=tome.id)
            db.add(meta)
        for key, val in fields.items():
            setattr(meta, key, val)
        tome.has_metadata = True
        tome.updated_at = datetime.utcnow()
        ok += 1

    await activity_log(db, "edit_metadata", f"Métadonnées éditées en lot : {ok} album(s)", status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": ok, "errors": errors}


@router.post("/{tome_id}/rename", response_model=TomeOut, dependencies=[Depends(require_permission("library.rename"))])
async def rename_tome(tome_id: int, body: RenameIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    user_data = await get_user_tome_data(db, current_user.id, tome_id)
    new_name = apply_pattern(body.pattern, tome, meta)
    if new_name == Path(tome.filepath).name:
        return _build_tome_out(tome, meta, user_data)
    new_path = Path(tome.filepath).parent / new_name
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"Fichier cible déjà existant : {new_name}")
    Path(tome.filepath).rename(new_path)
    tome.filename = new_name
    tome.filepath = str(new_path)
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    return _build_tome_out(tome, meta, user_data)


def _validate_new_filename(new_filename: str, original_filepath: str):
    if any(c in new_filename for c in ('/', '\\')) or '..' in new_filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    orig_ext = Path(original_filepath).suffix
    new_ext = Path(new_filename).suffix
    if new_ext.lower() != orig_ext.lower():
        raise HTTPException(status_code=400, detail="L'extension ne peut pas changer")


@router.post("/rename-bulk-to", dependencies=[Depends(require_permission("library.rename"))])
async def rename_bulk_to(body: RenameBulkToIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await assert_tomes_visible(db, current_user, [item.id for item in body.renames])
    ok = 0
    errors = []
    for item in body.renames:
        result = await db.execute(
            select(Tome, Metadata)
            .outerjoin(Metadata, Metadata.tome_id == Tome.id)
            .where(Tome.id == item.id)
        )
        row = result.first()
        if row is None:
            errors.append(f"id={item.id} : introuvable")
            continue
        tome, meta = row
        try:
            _validate_new_filename(item.new_filename, tome.filepath)
            if item.new_filename == Path(tome.filepath).name:
                continue
            new_path = Path(tome.filepath).parent / item.new_filename
            if new_path.exists():
                errors.append(f"{tome.filename} : fichier cible déjà existant")
                continue
            Path(tome.filepath).rename(new_path)
            tome.filename = item.new_filename
            tome.filepath = str(new_path)
            # Renommer change le sens de "T{Numéro}"/"{Titre}" dans le nom de fichier — sans
            # ceci, un numéro/titre resté vide ou faux avant renommage (ex. mauvaise
            # convention de nommage) reste figé indéfiniment même après correction du fichier.
            parsed = parse_filename(item.new_filename.rsplit(".", 1)[0])
            tome.number = parsed.get("number")
            tome.title = parsed.get("title")
            tome.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(tome)
            ok += 1
        except HTTPException as e:
            errors.append(f"{tome.filename} : {e.detail}")
        except Exception as e:
            errors.append(f"{tome.filename} : {e}")
    from ..services.activity import log as activity_log
    series_name = ""
    if body.renames:
        first_row = (await db.execute(select(Tome).where(Tome.id == body.renames[0].id))).scalar_one_or_none()
        if first_row:
            s = (await db.execute(select(Series).where(Series.id == first_row.series_id))).scalar_one_or_none()
            if s: series_name = s.name
    msg = f"Renommage terminé : {ok} album(s) renommé(s)"
    if series_name: msg += f" dans « {series_name} »"
    if errors: msg += f", {len(errors)} erreur(s)"
    await activity_log(db, "rename", msg, status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()
    return {"ok": ok, "errors": errors}


@router.post("/{tome_id}/rename-to", response_model=TomeOut, dependencies=[Depends(require_permission("library.rename"))])
async def rename_tome_to(tome_id: int, body: RenameToIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    user_data = await get_user_tome_data(db, current_user.id, tome_id)
    _validate_new_filename(body.new_filename, tome.filepath)
    if body.new_filename == Path(tome.filepath).name:
        return _build_tome_out(tome, meta, user_data)
    new_path = Path(tome.filepath).parent / body.new_filename
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"Fichier cible déjà existant : {body.new_filename}")
    Path(tome.filepath).rename(new_path)
    tome.filename = body.new_filename
    tome.filepath = str(new_path)
    # Voir rename_bulk_to — le nom de fichier vient de changer, number/title doivent en
    # refléter le contenu réel plutôt que de rester figés sur l'ancien parsing.
    parsed = parse_filename(body.new_filename.rsplit(".", 1)[0])
    tome.number = parsed.get("number")
    tome.title = parsed.get("title")
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    return _build_tome_out(tome, meta, user_data)


def _content_disposition(filename: str) -> str:
    """En-tête Content-Disposition correct pour un nom de fichier accentué (très courant
    ici : BD/mangas français) — filename= (repli ASCII) + filename*= (RFC 5987, UTF-8)."""
    ascii_fallback = filename.encode("ascii", "ignore").decode() or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


# Déclarés avant GET /{tome_id} ci-dessous : un chemin littéral comme /download-bulk serait
# sinon d'abord intercepté par ce motif générique à un seul segment (tome_id échouerait sa
# conversion en int et renverrait 422 sans jamais atteindre le vrai handler).
@router.get("/download-bulk", dependencies=[Depends(require_permission("library.download"))])
async def download_tomes_bulk(tome_ids: list[int] = Query(...), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await assert_tomes_visible(db, current_user, tome_ids)
    result = await db.execute(
        select(Tome, Series.name)
        .join(Series, Series.id == Tome.series_id)
        .where(Tome.id.in_(tome_ids))
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Aucun album trouvé")

    series_names = {name for _, name in rows}
    # Sous-dossier par série dans l'archive — évite toute collision de noms de fichiers
    # entre séries différentes, et reste lisible une fois décompressé.
    entries = [(f"{series_name}/{tome.filename}", tome.filepath) for tome, series_name in rows]
    zip_name = next(iter(series_names)) if len(series_names) == 1 else "CBZ Manager - export"

    return StreamingResponse(
        stream_zip(entries),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(f"{zip_name}.zip")},
    )


@router.get("/{tome_id}/download", dependencies=[Depends(require_permission("library.download"))])
async def download_tome(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if not Path(tome.filepath).is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")
    return FileResponse(
        tome.filepath,
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(tome.filename)},
    )


@router.get("/{tome_id}", response_model=TomeOut)
async def get_tome(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    user_data = await get_user_tome_data(db, current_user.id, tome_id)
    return _build_tome_out(tome, meta, user_data)


@router.get("/{tome_id}/metadata", response_model=MetadataOut)
async def get_metadata(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome_id))
    meta = meta_result.scalar_one_or_none()
    if meta is None:
        return MetadataOut()
    return MetadataOut.model_validate(meta)


@router.put("/{tome_id}/metadata", response_model=MetadataOut, dependencies=[Depends(require_permission("library.metadata_edit"))])
async def update_metadata(tome_id: int, body: MetadataIn, request: Request, silent: bool = False, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    if tome.file_format not in ("cbz",):
        raise HTTPException(
            status_code=400,
            detail="Seuls les fichiers CBZ peuvent être modifiés. Convertissez d'abord en CBZ."
        )

    fields = body.model_dump(exclude_none=True)

    try:
        await write_metadata(tome.filepath, fields)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur écriture: {str(e)}")

    # Update DB metadata row
    meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome_id))
    meta = meta_result.scalar_one_or_none()
    if meta is None:
        meta = Metadata(tome_id=tome_id)
        db.add(meta)

    for key, val in fields.items():
        if hasattr(meta, key):
            setattr(meta, key, val)

    tome.has_metadata = True
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(meta)

    if not silent:
        from ..services.activity import log as activity_log
        title = fields.get("Title") or tome.title or tome.filename
        series_row = (await db.execute(select(Series).where(Series.id == tome.series_id))).scalar_one_or_none()
        series_name = series_row.name if series_row else ""
        msg = f"Métadonnées éditées : « {title} »"
        if series_name: msg += f" ({series_name})"
        await activity_log(db, "edit_metadata", msg, user=current_user, ip=get_client_ip(request))
        await db.commit()

    return MetadataOut.model_validate(meta)


@router.post("/{tome_id}/parse-filename", response_model=ParseFilenameOut, dependencies=[Depends(require_permission("library.metadata_edit"))])
async def parse_tome_filename(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    await assert_tomes_visible(db, current_user, [tome_id])

    parsed = parse_filename(tome.filename.rsplit(".", 1)[0])
    return ParseFilenameOut(**parsed)


@router.patch("/{tome_id}/user-data", response_model=TomeOut)
async def update_user_data(tome_id: int, body: UserDataIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    # Sans ce contrôle, un lecteur pouvait fournir l'id d'un tome d'une série masquée/au-delà
    # de son public conseillé, modifier ses propres annotations dessus, et recevoir en retour
    # un TomeOut complet (titre, auteurs, chemin...) — contournant le masquage appliqué sur
    # les routes de liste/détail.
    await assert_tomes_visible(db, current_user, [tome_id])
    tome, meta = row
    user_data = await get_or_create_user_tome_data(db, current_user.id, tome_id)

    # "user_rating" explicitement envoyé (y compris null/0, pour effacer la note) vs absent
    # du payload (autres champs seuls modifiés) — is not None seul ne peut pas distinguer
    # les deux, "null" et "absent" valant tous les deux None une fois désérialisés.
    if "user_rating" in body.model_fields_set:
        user_data.rating = max(1, min(5, body.user_rating)) if body.user_rating else None
    if body.user_notes is not None:
        user_data.notes = body.user_notes
    if body.user_tags is not None:
        user_data.tag_list = json.dumps(body.user_tags, ensure_ascii=False)
    # "is_read" bascule manuelle (icône dédiée, voir TomeDetailView.vue) — même truc
    # model_fields_set que "user_rating" pour distinguer un false explicite d'un champ
    # absent. Purement manuel ici ; le passage automatique à True se fait dans
    # save_progress, jamais ici.
    if "is_read" in body.model_fields_set and body.is_read is not None:
        user_data.is_read = body.is_read

    user_data.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user_data)
    return _build_tome_out(tome, meta, user_data)


@router.get("/{tome_id}/progress", response_model=ReadingProgressOut)
async def get_progress(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await assert_tomes_visible(db, current_user, [tome_id])
    ud = await get_user_tome_data(db, current_user.id, tome_id)
    if ud is None:
        return ReadingProgressOut(tome_id=tome_id, last_page=0)
    return ReadingProgressOut(tome_id=tome_id, last_page=ud.last_page, updated_at=ud.updated_at, is_read=ud.is_read)


@router.put("/{tome_id}/progress", response_model=ReadingProgressOut)
async def save_progress(tome_id: int, body: ReadingProgressIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Même contrôle que update_user_data/get_progress (PATCH/GET) — celui-ci (PUT) avait été
    # oublié lors du premier passage, laissant un lecteur restreint écrire sa progression sur
    # un album d'une série masquée/au-delà de son public conseillé.
    await assert_tomes_visible(db, current_user, [tome_id])
    ud = await get_or_create_user_tome_data(db, current_user.id, tome_id)
    ud.last_page = body.last_page
    # Bascule automatique à 95% des pages — jamais l'inverse (une relecture qui repasse par
    # le seuil ne fait que confirmer un état déjà vrai ; un décochage manuel côté
    # update_user_data n'est donc jamais écrasé par un simple tour de lecture ultérieur).
    if not ud.is_read:
        tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
        if tome and tome.page_count and body.last_page >= tome.page_count * 0.95:
            ud.is_read = True
    ud.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ud)
    return ReadingProgressOut(tome_id=tome_id, last_page=ud.last_page, updated_at=ud.updated_at, is_read=ud.is_read)


@router.patch("/{tome_id}/hidden", response_model=TomeOut, dependencies=[Depends(require_permission("library.delete"))])
async def toggle_tome_hidden(tome_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome.hidden = not tome.hidden
    await db.commit()
    await db.refresh(tome)
    from ..services.activity import log as activity_log
    action = "Album masqué" if tome.hidden else "Album affiché"
    await activity_log(db, "edit_metadata", f"{action} : « {tome.title or tome.filename} »", user=current_user, ip=get_client_ip(request))
    await db.commit()
    user_data = await get_user_tome_data(db, current_user.id, tome_id)
    return _build_tome_out(tome, meta, user_data)


@router.patch("/{tome_id}/oneshot", response_model=TomeOut, dependencies=[Depends(require_permission("library.metadata_edit"))])
async def toggle_tome_oneshot(tome_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.id == tome_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome, meta = row
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    tome.is_oneshot = not tome.is_oneshot
    tome.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tome)
    from ..services.activity import log as activity_log
    action = "Marqué one-shot" if tome.is_oneshot else "Retiré des one-shot"
    await activity_log(db, "edit_metadata", f"{action} : « {tome.title or tome.filename} »", user=current_user, ip=get_client_ip(request))
    await db.commit()
    user_data = await get_user_tome_data(db, current_user.id, tome_id)
    return _build_tome_out(tome, meta, user_data)


@router.get("/{tome_id}/file-info")
async def get_tome_file_info(tome_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    p = Path(tome.filepath)
    try:
        file_size = p.stat().st_size
    except OSError:
        file_size = None

    width, height = None, None
    try:
        if tome.file_format in ("cbz",):
            import zipfile
            with zipfile.ZipFile(tome.filepath) as zf:
                images = sorted([n for n in zf.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
                if images:
                    import io
                    from PIL import Image
                    with zf.open(images[0]) as f:
                        img = Image.open(io.BytesIO(f.read()))
                        width, height = img.size
        elif tome.file_format == "cbr":
            import subprocess, io
            from PIL import Image
            result_rar = subprocess.run(["unrar", "lb", tome.filepath], capture_output=True, text=True)
            files = sorted([l.strip() for l in result_rar.stdout.splitlines() if l.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            if files:
                result_rar2 = subprocess.run(["unrar", "p", "-inul", tome.filepath, files[0]], capture_output=True)
                img = Image.open(io.BytesIO(result_rar2.stdout))
                width, height = img.size
        elif tome.file_format == "pdf":
            import fitz
            doc = fitz.open(tome.filepath)
            page = doc[0]
            width, height = int(page.rect.width), int(page.rect.height)
            doc.close()
    except Exception:
        pass

    return {
        "filepath": tome.filepath,
        "file_size": file_size,
        "image_width": width,
        "image_height": height,
    }


@router.delete("/{tome_id}/file", status_code=200, dependencies=[Depends(require_permission("library.delete"))])
async def delete_tome_file(tome_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Supprime le fichier sur disque, l'entrée DB, et le cache cover.
    Si c'était le dernier tome de la série, supprime aussi la série."""
    result = await db.execute(select(Tome).where(Tome.id == tome_id))
    tome = result.scalar_one_or_none()
    if tome is None:
        raise HTTPException(status_code=404, detail="Tome introuvable")
    if tome.series_id in await get_user_excluded_series_ids(db, current_user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    from ..services.tome_deletion import delete_tome_and_cleanup
    info = await delete_tome_and_cleanup(db, tome)

    from ..services.activity import log as activity_log
    if info["series_deleted"]:
        await activity_log(db, "delete_series", f"Album supprimé : « {info['tome_name']} » (série « {info['series_name']} » supprimée car vide)", user=current_user, ip=get_client_ip(request))
    else:
        await activity_log(db, "delete_tome", f"Album supprimé : « {info['tome_name']} »", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"series_deleted": info["series_deleted"], "series_id": info["series_id"]}
