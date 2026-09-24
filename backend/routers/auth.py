import asyncio
import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user, _profile_permissions
from ..models.schemas import AuthStatus, LoginIn, CredentialsIn
from ..models.db_models import User
from ..services import auth as auth_service
from ..services import avatar as avatar_service
from ..services.rate_limit import PerKeyRateLimiter
from ..config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _parse_trusted_proxies(raw: str) -> list:
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            # Accepte une IP seule ("127.0.0.1") ou un CIDR ("172.20.0.0/24") — ip_network
            # seul ne accepte pas une IP hôte avec des bits d'hôte non nuls sans strict=False.
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


# Adresses depuis lesquelles X-Forwarded-For/-Proto sont considérées fiables — configurable
# via TRUSTED_PROXY_IPS (voir config.py), loopback seul par défaut. Docker publie le port du
# conteneur directement (voir docker-compose.yml) — sans cette frontière, n'importe quel
# client se connectant directement (y compris un simple autre appareil du LAN, pas seulement
# Internet) peut poser ces en-têtes lui-même. Un vrai client externe arrivant via le reverse
# proxy annoncé n'a jamais pour adresse DE CONNEXION une IP publique directement sur ce port :
# la connexion TCP vue par l'app vient toujours du proxy, seul l'en-tête transporte la vraie
# IP du visiteur — délibérément PAS tout un LAN/réseau Docker entier par défaut (trop large :
# n'importe quel autre poste du même réseau pourrait sinon usurper ces en-têtes).
_TRUSTED_PROXY_NETWORKS = _parse_trusted_proxies(settings.TRUSTED_PROXY_IPS)


def _is_trusted_proxy_peer(request: Request) -> bool:
    host = request.client.host if request.client else None
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXY_NETWORKS)

# Bcrypt (~100-300ms de calcul CPU par vérification) tourne en synchrone dans un process
# uvicorn à un seul worker (voir Dockerfile) — sans cette limite, une rafale de tentatives
# de connexion bloque la boucle d'événements pour TOUS les utilisateurs (pas seulement
# l'auth), en plus de permettre un brute-force sur le mot de passe. Clé = IP (voir
# get_client_ip) : un compteur global ferait qu'un seul attaquant bloque les connexions
# légitimes de tout le monde.
_login_rate_limiter = PerKeyRateLimiter(max_calls=10, period_seconds=60)


def _cookie_kwargs(request: Request) -> dict:
    # Un cookie Secure n'est jamais stocké par le navigateur sur une connexion non-HTTPS
    # (accès direct en HTTP au NAS, par ex.) — se baser sur DEV_MODE seul est faux dès que
    # l'app tourne en prod sans TLS devant. On reflète la connexion réelle : le header
    # X-Forwarded-Proto posé par un reverse proxy (nginx, Traefik, Synology…) prime, sinon
    # le schéma de la requête telle que reçue par l'app — mais seulement si la connexion
    # directe vient bien d'un pair de confiance (voir _is_trusted_proxy_peer), sinon un
    # client arbitraire pourrait se faire passer pour une connexion HTTPS déjà terminée.
    proto = request.headers.get("x-forwarded-proto") if _is_trusted_proxy_peer(request) else None
    proto = proto or request.url.scheme
    return dict(
        httponly=True,
        samesite="lax",
        secure=proto == "https",
        max_age=auth_service.SESSION_MAX_AGE,
        path="/",
    )


def get_client_ip(request: Request) -> str | None:
    """IP réelle du client pour le journal d'activité — X-Forwarded-For posé par un reverse
    proxy (nginx, Traefik, Synology…) prime, sinon l'IP de connexion telle que reçue par
    l'app (même raisonnement que _cookie_kwargs pour X-Forwarded-Proto). Le premier maillon
    de X-Forwarded-For est le client d'origine, les suivants sont les proxys traversés.
    N'accepte cet en-tête que si la connexion DIRECTE vient d'un pair de confiance (voir
    _is_trusted_proxy_peer) — sinon un client qui contacte l'app directement (port Docker
    publié sans proxy devant, ou simplement en évitant le proxy annoncé) pouvait poser
    lui-même cet en-tête à chaque tentative pour contourner la limitation de débit du login
    (clé = IP) et polluer le journal d'activité avec une IP arbitraire."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _is_trusted_proxy_peer(request):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _status(db: AsyncSession, user: User) -> AuthStatus:
    # Source unique avec require_permission (dependencies._profile_permissions) : évite deux
    # implémentations divergentes de la résolution custom_permissions/profil qui finiraient
    # par désynchroniser ce que l'UI affiche de ce que le serveur autorise réellement.
    permissions = [] if user.is_admin else sorted(await _profile_permissions(db, user))
    return AuthStatus(
        authenticated=True,
        username=user.username,
        is_admin=user.is_admin,
        must_change_password=user.must_change_password,
        permissions=permissions,
        avatar_version=user.avatar_version,
    )


async def _verify_token(request: Request, db: AsyncSession) -> User | None:
    """Résout l'utilisateur courant à partir du cookie sans lever d'exception — utilisé par
    /me, qui doit répondre authenticated=False plutôt qu'une 401 en cas d'échec."""
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if not token:
        return None
    secret_key = await auth_service.get_secret_key(db)
    payload = auth_service.verify_session_token(token, secret_key)
    if payload is None:
        return None
    user = await auth_service.get_user_by_id(db, payload["user_id"])
    if user is None or user.token_version != payload["tv"]:
        return None
    return user


@router.get("/me", response_model=AuthStatus)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _verify_token(request, db)
    if user is None:
        return AuthStatus(authenticated=False)
    return await _status(db, user)


@router.post("/login", response_model=AuthStatus)
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from ..services.activity import log as activity_log

    username = body.username.strip()
    ip = get_client_ip(request)
    _login_rate_limiter.check(ip or "unknown")

    user = await auth_service.get_user_by_username(db, username)
    valid = user is not None and await asyncio.to_thread(auth_service.verify_password, body.password, user.password_hash)
    if not valid:
        await activity_log(db, "login", f"Échec de connexion — identifiant « {username} »", status="error", ip=ip)
        await db.commit()
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

    secret_key = await auth_service.get_secret_key(db)
    token = auth_service.create_session_token(user.id, user.token_version, secret_key)
    response.set_cookie(auth_service.SESSION_COOKIE_NAME, token, **_cookie_kwargs(request))
    await activity_log(db, "login", f"Connexion réussie — utilisateur « {user.username} »", status="ok", user=user, ip=ip)
    await db.commit()
    return await _status(db, user)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth_service.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.put("/credentials", response_model=AuthStatus)
async def update_credentials(
    body: CredentialsIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await asyncio.to_thread(auth_service.verify_password, body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")

    new_username = (body.new_username or "").strip()
    if new_username and new_username != current_user.username:
        if await auth_service.get_user_by_username(db, new_username) is not None:
            raise HTTPException(status_code=400, detail="Ce nom d'utilisateur est déjà pris")
        current_user.username = new_username

    if body.new_password:
        if len(body.new_password) < 8:
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit faire au moins 8 caractères")
        if body.new_password == body.current_password:
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent de l'actuel")
        current_user.password_hash = await asyncio.to_thread(auth_service.hash_password, body.new_password)
        current_user.must_change_password = False

    # Invalide les autres sessions DE CET UTILISATEUR uniquement (compteur de version, pas la
    # clé de signature globale) — contrairement à l'ancien système à compte unique qui
    # régénérait la clé globale et invalidait tout le monde à chaque changement d'identifiants.
    current_user.token_version += 1
    await db.commit()

    secret_key = await auth_service.get_secret_key(db)
    token = auth_service.create_session_token(current_user.id, current_user.token_version, secret_key)
    response.set_cookie(auth_service.SESSION_COOKIE_NAME, token, **_cookie_kwargs(request))
    return await _status(db, current_user)


@router.get("/avatar")
async def get_own_avatar(current_user: User = Depends(get_current_user)):
    path = avatar_service.get_avatar_path(current_user.id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Aucune photo de profil")
    return FileResponse(
        str(path), media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, must-revalidate"},
    )


@router.post("/avatar", response_model=AuthStatus)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (8 Mo max)")
    try:
        avatar_service.save_avatar(current_user.id, content)
    except Exception:
        raise HTTPException(status_code=400, detail="Image invalide")

    current_user.avatar_version += 1
    await db.commit()
    return await _status(db, current_user)


@router.delete("/avatar", response_model=AuthStatus)
async def remove_avatar(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    avatar_service.delete_avatar(current_user.id)
    current_user.avatar_version += 1
    await db.commit()
    return await _status(db, current_user)


@router.get("/avatar-presets")
async def list_avatar_presets(current_user: User = Depends(get_current_user)):
    return {"presets": list(range(1, avatar_service.PRESET_COUNT + 1))}


@router.get("/avatar-presets/{n}")
async def get_avatar_preset(n: int, current_user: User = Depends(get_current_user)):
    path = avatar_service.get_preset_path(n)
    if n < 1 or n > avatar_service.PRESET_COUNT or not path.exists():
        raise HTTPException(status_code=404, detail="Préréglage introuvable")
    return FileResponse(
        str(path), media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@router.post("/avatar-preset", response_model=AuthStatus)
async def apply_avatar_preset(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = body.get("preset")
    if not isinstance(n, int) or n < 1 or n > avatar_service.PRESET_COUNT:
        raise HTTPException(status_code=400, detail="Préréglage invalide")
    path = avatar_service.get_preset_path(n)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Préréglage introuvable")

    # Passe par le même pipeline que l'upload (recadrage carré, redimensionnement, JPEG) —
    # les préréglages sont déjà en 512×512, mais autant garder un seul chemin de code plutôt
    # que de dupliquer/contourner save_avatar pour ce cas précis.
    avatar_service.save_avatar(current_user.id, path.read_bytes())
    current_user.avatar_version += 1
    await db.commit()
    return await _status(db, current_user)
