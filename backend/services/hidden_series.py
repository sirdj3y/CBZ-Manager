from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import Series, Tome, UserHiddenSeries, User
from .age_rating import AGE_RATINGS


async def get_user_hidden_series_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Séries masquées spécifiquement à cet utilisateur (UserHiddenSeries seule, pas
    Series.hidden) — utile là où le masquage global a déjà son propre traitement
    indépendant (ex. list_series/show_hidden) et où seul l'ajout personnel manque."""
    return set((await db.execute(
        select(UserHiddenSeries.series_id).where(UserHiddenSeries.user_id == user_id)
    )).scalars().all())


async def get_user_age_restricted_series_ids(db: AsyncSession, age_rating_limit: str | None) -> set[int]:
    """Séries au-delà du public conseillé maximum de l'utilisateur (User.age_rating_limit).
    Une série sans Public défini compte comme la plus restrictive (invisible dès qu'une
    limite est fixée) plutôt que comme "Tout public" — décision explicite : sinon un compte
    restreint verrait par défaut la quasi-totalité d'une bibliothèque pas encore classée.
    Retourne un set vide si l'utilisateur n'a aucune limite (NULL = illimité, réservé de fait
    aux admins) OU si sa limite est le palier le plus élevé ("Adultes (illimité)" côté UI) —
    ce palier doit voir vraiment tout, y compris les séries pas encore classées, pas seulement
    tout le contenu déjà classé."""
    if not age_rating_limit:
        return set()
    try:
        limit_rank = AGE_RATINGS.index(age_rating_limit)
    except ValueError:
        return set()
    if limit_rank == len(AGE_RATINGS) - 1:
        return set()
    allowed = AGE_RATINGS[:limit_rank + 1]
    return set((await db.execute(
        select(Series.id).where(or_(Series.age_rating.is_(None), Series.age_rating.notin_(allowed)))
    )).scalars().all())


async def get_user_excluded_series_ids(db: AsyncSession, user: User) -> set[int]:
    """Union des séries masquées globalement (Series.hidden, à tout le monde), de celles
    masquées spécifiquement à cet utilisateur (UserHiddenSeries) et de celles au-delà de son
    public conseillé maximum (age_rating_limit) — toujours vide pour un admin, qui voit tout
    quoi qu'il arrive."""
    if user.is_admin:
        return set()
    global_ids = set((await db.execute(select(Series.id).where(Series.hidden == True))).scalars().all())
    personal_ids = await get_user_hidden_series_ids(db, user.id)
    age_restricted_ids = await get_user_age_restricted_series_ids(db, user.age_rating_limit)
    return global_ids | personal_ids | age_restricted_ids


async def assert_tomes_visible(db: AsyncSession, user: User, tome_ids: list[int]) -> None:
    """404 si un des tomes appartient à une série exclue pour cet utilisateur — pour les
    routes qui reçoivent une liste de tome_ids du client (bulk), en plus du filtrage déjà
    appliqué aux listes affichées. Un tome_id inexistant est laissé à la charge du handler
    (pas de vérification d'existence ici, seulement de visibilité)."""
    if user.is_admin or not tome_ids:
        return
    excluded = await get_user_excluded_series_ids(db, user)
    if not excluded:
        return
    series_ids = (await db.execute(select(Tome.series_id).where(Tome.id.in_(tome_ids)))).scalars().all()
    if any(sid in excluded for sid in series_ids):
        raise HTTPException(status_code=404, detail="Un ou plusieurs albums sont introuvables")


async def assert_series_visible(db: AsyncSession, user: User, series_ids: list[int]) -> None:
    """Équivalent à assert_tomes_visible, pour les routes recevant une liste de series_ids
    directement (ex. suppression en lot de séries)."""
    if user.is_admin or not series_ids:
        return
    excluded = await get_user_excluded_series_ids(db, user)
    if not excluded:
        return
    if any(sid in excluded for sid in series_ids):
        raise HTTPException(status_code=404, detail="Une ou plusieurs séries sont introuvables")
