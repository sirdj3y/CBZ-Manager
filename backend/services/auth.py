"""
Authentification multi-compte : hachage bcrypt du mot de passe, session par cookie signé
(itsdangerous) plutôt qu'un store de session côté serveur — le cookie porte {user_id, tv}
(token_version), vérifié contre la ligne User à chaque requête (dependencies.py) plutôt que
mis en cache, pour que profil/is_admin puissent changer immédiatement. La clé de signature
elle-même reste unique pour toute l'app (AuthConfig.secret_key, mise en cache — voir
get_secret_key) : l'invalidation par utilisateur passe par User.token_version, pas par
rotation de cette clé qui invaliderait tout le monde à la fois.
"""
import asyncio
import json
import secrets
from datetime import datetime
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import AuthConfig, User, UserTomeData, Profile

SESSION_COOKIE_NAME = "cbz_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 jours
_SALT = "cbz-session"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def new_secret_key() -> str:
    return secrets.token_hex(32)


def generate_temp_password() -> str:
    """Mot de passe temporaire fort pour un compte créé par l'admin — transmis une seule
    fois (voir routers/users.py), à changer par l'utilisateur (must_change_password)."""
    return secrets.token_urlsafe(12)


async def get_config(db: AsyncSession) -> AuthConfig:
    """Retourne l'unique ligne de config, en la créant avec des identifiants par défaut
    si l'app démarre pour la première fois."""
    result = await db.execute(select(AuthConfig).limit(1))
    config = result.scalar_one_or_none()
    if config is None:
        config = AuthConfig(
            username=DEFAULT_USERNAME,
            password_hash=hash_password(DEFAULT_PASSWORD),
            secret_key=new_secret_key(),
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        print(
            f"[startup] Aucun compte configuré — identifiants par défaut créés : "
            f"{DEFAULT_USERNAME} / {DEFAULT_PASSWORD}. À changer depuis "
            f"Configuration > Sécurité dès la première connexion.",
            flush=True,
        )
    return config


async def bootstrap_first_admin(db: AsyncSession) -> None:
    """Si aucun compte User n'existe encore, crée le premier admin à partir de l'AuthConfig
    existant — identifiants réels préservés tels quels (bcrypt est portable, pas de ré-hash),
    pour ne pas enfermer dehors une installation déjà en place lors du passage au
    multi-compte. get_config() garantit qu'une ligne AuthConfig existe à ce stade (créée avec
    admin/admin par défaut sur un tout premier démarrage), donc ce même chemin couvre aussi
    bien la migration d'une install existante que le tout premier démarrage."""
    existing = (await db.execute(select(User).limit(1))).scalar_one_or_none()
    if existing is not None:
        return
    config = await get_config(db)
    # Forcer le changement si les identifiants sont ENCORE littéralement admin/admin (premier
    # démarrage tout juste bootstrapé, ou vieille installation jamais reconfigurée) — pas si
    # l'admin avait déjà personnalisé son mot de passe avant le passage au multi-compte, ce
    # qui redemanderait inutilement un changement de quelque chose de déjà sécurisé.
    is_still_default = config.username == DEFAULT_USERNAME and verify_password(DEFAULT_PASSWORD, config.password_hash)
    db.add(User(
        username=config.username, password_hash=config.password_hash, is_admin=True,
        must_change_password=is_still_default,
        # Bibliothèque déjà en place le cas échéant — rien de tout ça n'est "nouveau", sinon
        # le menu Nouveautés se retrouverait avec potentiellement des années de contenu au
        # premier login post-migration.
        notifications_last_seen_at=datetime.utcnow(),
    ))
    await db.commit()


async def migrate_personal_data(db: AsyncSession) -> None:
    """Migration ponctuelle : bascule les données personnelles historiquement partagées
    (colonnes tomes.user_rating/user_notes/user_tag_list, table reading_progress) vers
    UserTomeData, rattachées au premier compte admin — qui héritait de facto de tout,
    l'app étant mono-compte jusqu'ici.

    Lecture en SQL brut plutôt que via l'ORM : ces colonnes/cette table ne sont plus
    déclarées dans le modèle (models/db_models.py) une fois cette bascule faite — elles
    restent physiquement présentes sur une installation existante (pas de migration de
    suppression, même principe que AuthConfig.username/password_hash à l'étape 1) mais
    n'existent jamais du tout sur une installation neuve, d'où le OperationalError attrapé
    ci-dessous. Idempotente : ne fait rien si déjà migré."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    if (await db.execute(select(UserTomeData).limit(1))).scalar_one_or_none() is not None:
        return
    admin = (await db.execute(
        select(User).where(User.is_admin == True).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    if admin is None:
        return

    try:
        tome_rows = (await db.execute(text(
            "SELECT id, user_rating, user_notes, user_tag_list FROM tomes"
        ))).all()
    except OperationalError:
        await db.rollback()
        return  # installation neuve : ces colonnes n'ont jamais existé, rien à migrer

    try:
        progress_rows = (await db.execute(text("SELECT tome_id, last_page FROM reading_progress"))).all()
    except OperationalError:
        await db.rollback()
        progress_rows = []
    progress_by_tome = {r.tome_id: r.last_page for r in progress_rows}

    migrated = 0
    for row in tome_rows:
        last_page = progress_by_tome.get(row.id, 0)
        if not (row.user_rating or row.user_notes or row.user_tag_list or last_page):
            continue
        db.add(UserTomeData(
            user_id=admin.id, tome_id=row.id,
            rating=row.user_rating, notes=row.user_notes, tag_list=row.user_tag_list,
            last_page=last_page,
        ))
        migrated += 1
    await db.commit()
    if migrated:
        print(f"[startup] Données personnelles historiques ({migrated} album(s)) rattachées au compte admin « {admin.username} ».", flush=True)


DEFAULT_PROFILES = {
    # library.download inclus : sans lui, un compte Lecteur ne peut pas lire via un catalogue
    # OPDS (Chunky, Panels...) — contrairement au lecteur web intégré qui streame page par
    # page, ces apps ont besoin de télécharger le fichier pour le lire.
    "Lecteur":      ["library.read", "library.download"],
    "Contributeur": ["library.read", "library.import", "library.scan"],
}


async def seed_default_profiles(db: AsyncSession) -> None:
    """Profils de départ, pour ne pas laisser un admin devant un écran Profils vide au
    premier démarrage. Idempotent : ne fait rien si un profil existe déjà (y compris si
    l'admin en a créé/supprimé lui-même depuis — on ne les recrée jamais après coup)."""
    existing = (await db.execute(select(Profile).limit(1))).scalar_one_or_none()
    if existing is not None:
        return
    for name, permissions in DEFAULT_PROFILES.items():
        db.add(Profile(name=name, permissions=json.dumps(permissions, ensure_ascii=False)))
    await db.commit()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Recherche insensible à la casse — la casse d'un identifiant ne protège rien
    (contrairement au mot de passe, laissé lui strictement sensible à la casse) et ne fait
    que créer des échecs de connexion déroutants (verrouillage majuscules, autocapitalisation
    mobile...). Couvre aussi la vérification d'unicité à la création de compte (même fonction),
    pour ne jamais permettre "Bob" et "bob" comme deux comptes distincts."""
    return (await db.execute(select(User).where(func.lower(User.username) == username.lower()))).scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def create_user(
    db: AsyncSession, username: str, password: str, is_admin: bool = False, must_change_password: bool = False,
    profile_id: int | None = None, custom_permissions: str | None = None, age_rating_limit: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=await asyncio.to_thread(hash_password, password),
        is_admin=is_admin,
        must_change_password=must_change_password,
        profile_id=profile_id if not is_admin else None,
        custom_permissions=custom_permissions if not is_admin else None,
        # Un administrateur voit tout quoi qu'il arrive (get_user_excluded_series_ids le
        # court-circuite) — jamais stocké pour lui, même logique que profile_id ci-dessus.
        age_rating_limit=age_rating_limit if not is_admin else None,
        # Voir bootstrap_first_admin — un compte tout juste créé ne doit rien voir de
        # "nouveau" dans la bibliothèque déjà en place au moment de sa création.
        notifications_last_seen_at=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# Mise en cache mémoire de la clé de signature — auth_required tourne sur quasi toutes les
# routes de l'app et n'a besoin que de ce champ, pas de relire toute la ligne AuthConfig en DB
# à chaque requête. Invalidée explicitement par invalidate_secret_key_cache() quand la clé est
# régénérée (changement d'identifiants), pour que l'invalidation des autres sessions reste
# immédiate plutôt que de rester bloquée sur l'ancienne clé jusqu'au redémarrage du process.
_cached_secret_key: str | None = None


async def get_secret_key(db: AsyncSession) -> str:
    global _cached_secret_key
    if _cached_secret_key is None:
        config = await get_config(db)
        _cached_secret_key = config.secret_key
    return _cached_secret_key


def invalidate_secret_key_cache() -> None:
    global _cached_secret_key
    _cached_secret_key = None


def create_session_token(user_id: int, token_version: int, secret_key: str) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt=_SALT)
    return serializer.dumps({"user_id": user_id, "tv": token_version})


def verify_session_token(token: str, secret_key: str) -> dict | None:
    """Retourne {"user_id", "tv"} si la signature/expiration est valide, None sinon. La
    correspondance de tv (token_version) avec la valeur actuelle de l'utilisateur est
    vérifiée par l'appelant (dependencies.py), pas ici — ce module ne fait pas de requête DB."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_SALT)
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        if "user_id" not in data or "tv" not in data:
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None
