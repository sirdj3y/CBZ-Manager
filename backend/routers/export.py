import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import require_admin
from ..models.db_models import Tome, Metadata, UserTomeData, User
from ..services.user_tome_data import get_or_create_user_tome_data
from ..services.metadata_writer import COMICINFO_FIELDS as METADATA_FIELDS
from .auth import get_client_ip

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(require_admin)])


async def _build_export(db: AsyncSession) -> dict:
    result = await db.execute(
        select(Tome)
        .options(
            selectinload(Tome.series),
            selectinload(Tome.metadata_),
        )
        .order_by(Tome.series_id, Tome.number)
    )
    tomes = result.scalars().all()

    # Une seule requête groupée pour toutes les annotations personnelles de tous les
    # utilisateurs, plutôt qu'une requête par tome — sauvegarde complète multi-comptes,
    # regroupée par tome_id puis par nom d'utilisateur.
    personal_rows = (await db.execute(
        select(UserTomeData.tome_id, User.username, UserTomeData.rating, UserTomeData.notes, UserTomeData.tag_list, UserTomeData.last_page, UserTomeData.is_read)
        .join(User, User.id == UserTomeData.user_id)
    )).all()
    personal_by_tome: dict[int, dict] = {}
    for tome_id, username, rating, notes, tag_list, last_page, is_read in personal_rows:
        try:
            tags = json.loads(tag_list) if tag_list else []
        except Exception:
            tags = []
        personal_by_tome.setdefault(tome_id, {})[username] = {
            "rating": rating,
            "notes": notes,
            "tags": tags,
            "last_page": last_page,
            # Absent de l'export jusqu'ici : une restauration perdait le statut "Lu" manuel
            # d'un album (voir services/user_tome_data.py) même si tout le reste des
            # annotations personnelles revenait correctement.
            "is_read": is_read,
        }

    entries = []
    for t in tomes:
        m = t.metadata_
        entry = {
            "filepath": t.filepath,
            "filename": t.filename,
            "serie": t.series.name if t.series else "",
            "numero": t.number,
            "titre": t.title,
            "format": t.file_format,
            "taille_octets": t.file_size,
            "pages": t.page_count,
            # Annotations personnelles par utilisateur (note, notes texte, étiquettes,
            # progression de lecture) — un compte n'apparaît ici que s'il a réellement une
            # ligne UserTomeData pour ce tome, pas d'entrées vides pour tout le monde.
            "personal": personal_by_tome.get(t.id, {}),
            # Métadonnées ComicInfo.xml
            "metadata": {field: getattr(m, field, None) for field in METADATA_FIELDS} if m else {},
        }
        entries.append(entry)

    return {
        "version": 2,
        "exported_at": datetime.utcnow().isoformat(),
        "tome_count": len(entries),
        "tomes": entries,
    }


@router.get("")
async def export_library(db: AsyncSession = Depends(get_db)):
    data = await _build_export(db)
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=cbzmanager-backup.json"},
    )


@router.post("/import")
async def import_library(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    raw = await file.read()
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier JSON invalide")

    if not isinstance(data, dict) or "tomes" not in data:
        raise HTTPException(status_code=400, detail="Format de fichier non reconnu")

    entries = data["tomes"]
    updated = 0
    not_found = 0
    ambiguous = 0
    # Comptes référencés dans la sauvegarde mais qui n'existent plus (ou pas encore) dans
    # cette installation — leurs annotations sont ignorées sans bloquer le reste de l'import.
    skipped_users: set[str] = set()

    for entry in entries:
        filepath = entry.get("filepath")
        filename = entry.get("filename")

        # Cherche d'abord par filepath, puis par filename. scalars().all() (pas
        # scalar_one_or_none()) : un nom de fichier comme "T01.cbz" peut exister dans
        # plusieurs séries différentes — scalar_one_or_none() lèverait une exception non
        # rattrapée sur un vrai doublon (MultipleResultsFound), interrompant tout le reste de
        # la restauration. Un repli ambigu ne doit jamais deviner au hasard : on le compte à
        # part plutôt que de risquer d'écrire les annotations d'un album sur un autre.
        tome = None
        if filepath:
            result = await db.execute(select(Tome).where(Tome.filepath == filepath).options(
                selectinload(Tome.metadata_)
            ))
            matches = result.scalars().all()
            if len(matches) == 1:
                tome = matches[0]

        if tome is None and filename:
            result = await db.execute(select(Tome).where(Tome.filename == filename).options(
                selectinload(Tome.metadata_)
            ))
            matches = result.scalars().all()
            if len(matches) > 1:
                ambiguous += 1
                continue
            if len(matches) == 1:
                tome = matches[0]

        if tome is None:
            not_found += 1
            continue

        # Restaure les annotations personnelles, par utilisateur
        for username, pdata in (entry.get("personal") or {}).items():
            user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if user is None:
                skipped_users.add(username)
                continue
            ud = await get_or_create_user_tome_data(db, user.id, tome.id)
            if pdata.get("rating") is not None:
                ud.rating = pdata["rating"]
            if pdata.get("notes") is not None:
                ud.notes = pdata["notes"]
            if pdata.get("tags") is not None:
                ud.tag_list = json.dumps(pdata["tags"], ensure_ascii=False)
            if pdata.get("last_page") is not None:
                ud.last_page = pdata["last_page"]
            if pdata.get("is_read") is not None:
                ud.is_read = pdata["is_read"]

        # Restaure métadonnées ComicInfo.xml
        meta_data = entry.get("metadata") or {}
        if any(v for v in meta_data.values()):
            if tome.metadata_ is None:
                meta = Metadata(tome_id=tome.id)
                db.add(meta)
                await db.flush()
                tome.metadata_ = meta
            for field in METADATA_FIELDS:
                val = meta_data.get(field)
                if val is not None:
                    setattr(tome.metadata_, field, val)
            tome.has_metadata = True

        updated += 1

    await db.commit()

    from ..services.activity import log as activity_log
    msg = f"Sauvegarde restaurée : {updated} album(s) mis à jour, {not_found} introuvable(s) sur {len(entries)}"
    if ambiguous:
        msg += f", {ambiguous} ambigu(s) (plusieurs albums de même nom, ignorés par sécurité)"
    await activity_log(db, "restore_backup", msg, user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {
        "updated": updated,
        "not_found": not_found,
        "ambiguous": ambiguous,
        "total": len(entries),
        "skipped_users": sorted(skipped_users),
    }
