import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from ..database import get_db
from ..dependencies import require_admin
from ..models.db_models import User, Profile, UserHiddenSeries
from ..services import auth as auth_service
from ..services.permissions import PERMISSIONS
from ..services.age_rating import AGE_RATINGS
from .auth import get_client_ip

# API minimale de gestion des comptes — pas d'interface graphique encore (arrive avec les
# écrans admin, étape 3), juste de quoi vérifier bout en bout que le multi-compte et le
# câblage des permissions (étape 2) fonctionnent.
router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _out(u: User) -> dict:
    custom_permissions = None
    if u.custom_permissions:
        try:
            custom_permissions = json.loads(u.custom_permissions)
        except (json.JSONDecodeError, TypeError):
            custom_permissions = None
    return {
        "id": u.id,
        "username": u.username,
        "is_admin": u.is_admin,
        "profile_id": u.profile_id,
        "custom_permissions": custom_permissions,
        "age_rating_limit": u.age_rating_limit,
        "must_change_password": u.must_change_password,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


def _validate_new_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 8 caractères")


def _encode_custom_permissions(keys: list[str] | None) -> str | None:
    if keys is None:
        return None
    unknown = set(keys) - set(PERMISSIONS.keys())
    if unknown:
        raise HTTPException(status_code=400, detail=f"Permission(s) inconnue(s) : {', '.join(sorted(unknown))}")
    return json.dumps(sorted(set(keys)))


def _validate_age_rating_limit(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in AGE_RATINGS:
        raise HTTPException(status_code=400, detail=f"Public invalide : {value}")
    return value


@router.get("")
async def list_users(db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.username))).scalars().all()
    return [_out(u) for u in users]


class CreateUserIn(BaseModel):
    username: str
    is_admin: bool = False
    profile_id: int | None = None
    # Personnalisation pour CET utilisateur, au-delà de ce que son profil de base accorde —
    # voir models.db_models.User.custom_permissions. None = pas de personnalisation, hérite
    # simplement du profil.
    custom_permissions: list[str] | None = None
    # Plafond de public (voir models.db_models.User.age_rating_limit) — None retombe sur
    # "Tout public" par défaut pour un non-admin (jamais d'accès "Illimité" implicite).
    age_rating_limit: str | None = None
    # Optionnel : si l'admin saisit un mot de passe directement, il est utilisé tel quel
    # (jamais renvoyé) ; sinon un mot de passe temporaire fort est généré et renvoyé une
    # seule fois (voir plus bas).
    password: str | None = None


@router.post("")
async def create_user(body: CreateUserIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Crée un compte. Si aucun mot de passe n'est fourni, un mot de passe temporaire fort
    est généré et renvoyé une seule fois — à charge pour l'admin de le transmettre. Dans les
    deux cas, l'utilisateur devra le changer à la première connexion (must_change_password),
    sans passer par un lien/email : l'app n'a aucune infrastructure d'envoi de mail."""
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
    if await auth_service.get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=400, detail="Ce nom d'utilisateur est déjà pris")
    if body.profile_id is not None and not body.is_admin:
        if (await db.execute(select(Profile).where(Profile.id == body.profile_id))).scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Profil introuvable")
    custom_permissions = _encode_custom_permissions(body.custom_permissions if not body.is_admin else None)
    # Pas de "Illimité" pour un non-admin : sécurité par défaut, un oubli de paramétrage ne
    # doit jamais exposer plus que "Tout public" — celui qui a vraiment besoin de tout voir
    # doit être admin (qui bypass ce filtre entièrement), pas un compte "limité à rien".
    age_rating_limit = _validate_age_rating_limit(body.age_rating_limit)
    if not body.is_admin and age_rating_limit is None:
        age_rating_limit = AGE_RATINGS[0]

    if body.password:
        _validate_new_password(body.password)
        password, reveal_password = body.password, None
    else:
        password = reveal_password = auth_service.generate_temp_password()

    user = await auth_service.create_user(
        db, username, password, is_admin=body.is_admin, must_change_password=True, profile_id=body.profile_id,
        custom_permissions=custom_permissions, age_rating_limit=age_rating_limit,
    )

    from ..services.activity import log as activity_log
    role = "administrateur" if body.is_admin else "utilisateur"
    await activity_log(db, "user_create", f"Compte créé : « {username} » ({role})", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {**_out(user), "temp_password": reveal_password}


class UpdateUserIn(BaseModel):
    username: str | None = None
    profile_id: int | None = None
    is_admin: bool | None = None
    custom_permissions: list[str] | None = None
    # Plafond de public — None retombe sur "Tout public" par défaut pour un non-admin
    # (jamais d'accès "Illimité" implicite, voir create_user/update_user). Comme profile_id/
    # custom_permissions ci-dessus, le formulaire envoie toujours l'état complet du champ.
    age_rating_limit: str | None = None
    # Optionnel — vide/absent = mot de passe inchangé (contrairement aux champs ci-dessus,
    # ici l'absence a vraiment un sens différent de "remettre à zéro"). Fixé par l'admin,
    # donc must_change_password repasse à True et les sessions existantes sont invalidées
    # (token_version), même logique qu'un changement de mot de passe volontaire.
    password: str | None = None


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UpdateUserIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Assignation de profil, personnalisation des droits, statut administrateur, et
    renommage — auparavant réservé à AccountView.vue (auto-renommage), désormais possible
    aussi pour un admin sur n'importe quel compte depuis cette page."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    from ..services.activity import log as activity_log

    old_username = target.username
    if body.username is not None:
        new_username = body.username.strip()
        if not new_username:
            raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
        if new_username.lower() != target.username.lower():
            existing = await auth_service.get_user_by_username(db, new_username)
            if existing is not None and existing.id != target.id:
                raise HTTPException(status_code=400, detail="Ce nom d'utilisateur est déjà pris")
        target.username = new_username

    was_admin = target.is_admin
    is_admin = body.is_admin if body.is_admin is not None else target.is_admin

    if was_admin and not is_admin:
        # Même garde que la suppression : jamais se retrouver sans aucun administrateur, y
        # compris si l'admin connecté se rétrograde lui-même.
        admin_count = (await db.execute(
            select(func.count()).select_from(User).where(User.is_admin == True)
        )).scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Impossible de retirer les droits du dernier administrateur")

    profile_name = None
    if is_admin:
        # Un administrateur a tous les droits quoi qu'il arrive (profile_id/custom_permissions/
        # age_rating_limit ignorés partout ailleurs dans l'app dès is_admin=True) — jamais
        # stockés, pour ne pas laisser un profil fantôme incohérent avec le badge affiché.
        target.profile_id = None
        target.custom_permissions = None
        target.age_rating_limit = None
    elif body.profile_id is not None:
        profile = (await db.execute(select(Profile).where(Profile.id == body.profile_id))).scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=400, detail="Profil introuvable")
        target.profile_id = body.profile_id
        target.custom_permissions = _encode_custom_permissions(body.custom_permissions)
        profile_name = profile.name
    else:
        target.profile_id = None
        target.custom_permissions = _encode_custom_permissions(body.custom_permissions)

    if not is_admin:
        # Pas de "Illimité" pour un non-admin — voir create_user pour le raisonnement.
        target.age_rating_limit = _validate_age_rating_limit(body.age_rating_limit) or AGE_RATINGS[0]

    if is_admin != was_admin:
        target.is_admin = is_admin
        role = "administrateur" if is_admin else "utilisateur"
        await activity_log(db, "user_update", f"Statut modifié pour « {target.username} » : {role}", user=current_user, ip=get_client_ip(request))
    else:
        modified = " (personnalisé)" if target.custom_permissions else ""
        detail = f"profil « {profile_name} »{modified}" if profile_name else "aucun profil (aucun droit)"
        await activity_log(db, "user_update", f"Profil modifié pour « {target.username} » : {detail}", user=current_user, ip=get_client_ip(request))

    if target.username != old_username:
        await activity_log(db, "user_update", f"Compte renommé : « {old_username} » → « {target.username} »", user=current_user, ip=get_client_ip(request))

    if body.password:
        _validate_new_password(body.password)
        target.password_hash = await asyncio.to_thread(auth_service.hash_password, body.password)
        target.must_change_password = True
        target.token_version += 1
        await activity_log(db, "user_update", f"Mot de passe réinitialisé pour « {target.username} »", user=current_user, ip=get_client_ip(request))

    await db.commit()
    return _out(target)


@router.get("/{user_id}/hidden-series")
async def get_hidden_series(user_id: int, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    series_ids = (await db.execute(
        select(UserHiddenSeries.series_id).where(UserHiddenSeries.user_id == user_id)
    )).scalars().all()
    return {"series_ids": list(series_ids)}


class HiddenSeriesIn(BaseModel):
    series_ids: list[int] = []


@router.put("/{user_id}/hidden-series")
async def set_hidden_series(user_id: int, body: HiddenSeriesIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Remplace la liste complète des séries masquées pour cet utilisateur — plus simple
    qu'un ajout/retrait unitaire pour une liste éditée via des cases à cocher côté UI."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    await db.execute(
        UserHiddenSeries.__table__.delete().where(UserHiddenSeries.user_id == user_id)
    )
    for series_id in set(body.series_ids):
        db.add(UserHiddenSeries(user_id=user_id, series_id=series_id))
    await db.commit()

    from ..services.activity import log as activity_log
    n = len(set(body.series_ids))
    await activity_log(db, "user_hidden_series", f"Séries masquées mises à jour pour « {target.username} » ({n} série(s))", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"series_ids": sorted(set(body.series_ids))}


@router.delete("/{user_id}", status_code=200)
async def delete_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if target.is_admin:
        admin_count = (await db.execute(
            select(func.count()).select_from(User).where(User.is_admin == True)
        )).scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur")

    username = target.username
    await db.delete(target)
    await db.commit()

    from ..services.activity import log as activity_log
    await activity_log(db, "user_delete", f"Compte supprimé : « {username} »", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": True}
