import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from ..database import get_db
from ..dependencies import require_admin
from ..models.db_models import Profile, User
from ..services.permissions import PERMISSIONS
from .auth import get_client_ip

router = APIRouter(prefix="/api/profiles", tags=["profiles"], dependencies=[Depends(require_admin)])


def _out(p: Profile) -> dict:
    try:
        permissions = json.loads(p.permissions) if p.permissions else []
    except (json.JSONDecodeError, TypeError):
        permissions = []
    return {"id": p.id, "name": p.name, "permissions": permissions}


@router.get("")
async def list_profiles(db: AsyncSession = Depends(get_db)):
    # Par id (ordre de création) plutôt que par nom — un tri alphabétique inversait
    # Contributeur/Lecteur dans le sélecteur Rôle de la page Comptes, contre-intuitif.
    profiles = (await db.execute(select(Profile).order_by(Profile.id))).scalars().all()
    return [_out(p) for p in profiles]


@router.get("/permissions")
async def list_permissions():
    """Catalogue des permissions disponibles (clé + libellé), pour l'écran Profils."""
    return [{"key": k, "label": v} for k, v in PERMISSIONS.items()]


class ProfileIn(BaseModel):
    name: str
    permissions: list[str] = []


@router.post("")
async def create_profile(body: ProfileIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de profil requis")
    unknown = [k for k in body.permissions if k not in PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Permission(s) inconnue(s) : {', '.join(unknown)}")
    if (await db.execute(select(Profile).where(Profile.name == name))).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Ce nom de profil est déjà pris")

    profile = Profile(name=name, permissions=json.dumps(body.permissions, ensure_ascii=False))
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    from ..services.activity import log as activity_log
    await activity_log(db, "profile_create", f"Profil créé : « {name} » ({len(body.permissions)} permission(s))", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return _out(profile)


@router.put("/{profile_id}")
async def update_profile(profile_id: int, body: ProfileIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    profile = (await db.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de profil requis")
    unknown = [k for k in body.permissions if k not in PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Permission(s) inconnue(s) : {', '.join(unknown)}")
    if name != profile.name and (await db.execute(select(Profile).where(Profile.name == name))).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Ce nom de profil est déjà pris")

    profile.name = name
    profile.permissions = json.dumps(body.permissions, ensure_ascii=False)
    await db.commit()

    from ..services.activity import log as activity_log
    await activity_log(db, "profile_update", f"Profil modifié : « {name} » ({len(body.permissions)} permission(s))", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return _out(profile)


@router.delete("/{profile_id}", status_code=200)
async def delete_profile(profile_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    profile = (await db.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    # Désassigne plutôt que de bloquer la suppression — cohérent avec "pas de profil = aucune
    # permission" (deny by default), pas besoin d'empêcher la suppression d'un profil en cours
    # d'utilisation.
    assigned = (await db.execute(select(User).where(User.profile_id == profile_id))).scalars().all()
    for u in assigned:
        u.profile_id = None

    name = profile.name
    await db.delete(profile)
    await db.commit()

    from ..services.activity import log as activity_log
    n = len(assigned)
    detail = f" — {n} compte(s) désassigné(s)" if n else ""
    await activity_log(db, "profile_delete", f"Profil supprimé : « {name} »{detail}", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": True}
