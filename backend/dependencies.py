import json
from fastapi import Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db

__all__ = ["get_db", "auth_required", "get_current_user", "require_admin", "require_permission"]

# Routes qui doivent rester utilisables par un compte "provisoire" (must_change_password) —
# tout le reste de l'API lui est fermé tant qu'il n'a pas changé son mot de passe. Le champ
# must_change_password existait déjà (voir services/auth.py::bootstrap_first_admin), mais
# n'était appliqué que côté Vue (redirection de routeur, contournable par un appel API
# direct) — jamais vérifié côté serveur avant l'audit de sécurité.
_ALLOWED_WHILE_PROVISIONAL = {"/api/auth/me", "/api/auth/logout", "/api/auth/credentials"}


async def auth_required(request: Request, db: AsyncSession = Depends(get_db)):
    """Vérifie la session et retourne l'utilisateur courant (User). Le retour est ignoré par
    les routes qui n'utilisent cette dépendance que comme garde
    (`dependencies=[Depends(auth_required)]`), et exploitable directement par celles qui ont
    besoin de l'objet (voir get_current_user/require_admin ci-dessous).

    Pas de cache sur l'utilisateur/profil (contrairement à la clé de signature, voir
    get_secret_key) : is_admin et le profil doivent pouvoir changer immédiatement, mettre ça
    en cache reproduirait la classe de bug déjà corrigée sur secret_key."""
    # Import différé : évite un cycle (services.auth -> models.db_models -> database,
    # et dependencies est importé très tôt par la quasi-totalité des routers).
    from .services.auth import get_secret_key, verify_session_token, get_user_by_id, SESSION_COOKIE_NAME

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")

    secret_key = await get_secret_key(db)
    payload = verify_session_token(token, secret_key)
    if payload is None:
        raise HTTPException(status_code=401, detail="Session invalide ou expirée")

    user = await get_user_by_id(db, payload["user_id"])
    if user is None or user.token_version != payload["tv"]:
        raise HTTPException(status_code=401, detail="Session invalide ou expirée")

    if user.must_change_password and request.url.path not in _ALLOWED_WHILE_PROVISIONAL:
        raise HTTPException(status_code=403, detail="Mot de passe à changer avant de continuer")

    request.state.user = user
    return user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """À utiliser quand la route a besoin de l'utilisateur courant (pas juste d'une garde) :
    `current_user = Depends(get_current_user)`."""
    return await auth_required(request, db)


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)):
    """Garde admin-only — indépendante du système de profils : réservée aux réglages système
    et à la gestion des comptes, jamais paramétrable via un profil."""
    user = await auth_required(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur")
    return user


async def _profile_permissions(db: AsyncSession, user) -> set[str]:
    """Droits effectifs d'un utilisateur non-admin : User.custom_permissions (personnalisé
    pour CET utilisateur précis) prime s'il est renseigné, sinon ceux du profil assigné —
    voir models.db_models.User.custom_permissions."""
    if user.custom_permissions:
        try:
            return set(json.loads(user.custom_permissions))
        except (json.JSONDecodeError, TypeError):
            pass
    if user.profile_id is None:
        return set()
    from .models.db_models import Profile
    profile = (await db.execute(select(Profile).where(Profile.id == user.profile_id))).scalar_one_or_none()
    if profile is None or not profile.permissions:
        return set()
    try:
        return set(json.loads(profile.permissions))
    except (json.JSONDecodeError, TypeError):
        return set()


def require_permission(key: str):
    """Garde paramétrable par profil (voir services/permissions.PERMISSIONS pour le
    catalogue). Un admin passe toujours, indépendamment de son profil (généralement absent).
    Requête DB dédiée au profil plutôt qu'un eager-load sur auth_required (qui tourne sur
    toutes les requêtes) : ne coûte que sur les routes réellement gardées, et évite le
    lazy-loading d'une relation SQLAlchemy async (planterait sans selectinload explicite)."""
    async def _check(request: Request, db: AsyncSession = Depends(get_db)):
        user = await auth_required(request, db)
        if user.is_admin:
            return user
        if key not in await _profile_permissions(db, user):
            raise HTTPException(status_code=403, detail="Action non autorisée pour ce profil")
        return user
    return _check
