from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Series, Tome, Metadata, MissingAlbum, UserTomeData, ReadingActivity, User
from ..services.hidden_series import get_user_excluded_series_ids

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(require_permission("library.read"))])


def _compute_streaks(day_strings: list[str]) -> tuple[int, int]:
    """(série en cours, meilleure série) de jours consécutifs avec au moins une seconde de
    lecture — day_strings au format "YYYY-MM-DD" (ReadingActivity.day), pas forcément triés."""
    days = {datetime.strptime(d, "%Y-%m-%d").date() for d in day_strings}
    if not days:
        return 0, 0

    today = datetime.utcnow().date()
    # La série en cours part d'aujourd'hui s'il y a déjà eu de la lecture aujourd'hui, sinon
    # d'hier — la journée en cours n'est pas encore "manquée" tant qu'elle n'est pas terminée,
    # sans quoi le compteur retomberait artificiellement à 0 entre deux sessions du même jour.
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        longest = max(longest, run)
        prev = d

    return current, longest


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # ── Compteurs de base ──────────────────────────────────────────────────
    series_count = (await db.execute(select(func.count()).select_from(Series))).scalar() or 0
    tome_count   = (await db.execute(select(func.count()).select_from(Tome))).scalar() or 0
    total_size   = (await db.execute(select(func.sum(Tome.file_size)))).scalar() or 0
    total_pages  = (await db.execute(select(func.sum(Tome.page_count)))).scalar() or 0

    # Séries masquées pour cet utilisateur (globalement ou spécifiquement) — exclues des
    # requêtes ci-dessous qui révèlent un NOM de série/album précis, pas des compteurs
    # d'agrégat (voir décision de périmètre : seules top_series/top10_series/heaviest sont
    # concernées, le reste de cette page reste un agrégat global non-identifiant).
    excluded_series_ids = await get_user_excluded_series_ids(db, current_user)

    # ── Plus grande série ─────────────────────────────────────────────────
    # Compte LIVE des tomes non-oneshot par série (plutôt que Series.tome_count, qui compte
    # tout) — un dossier "One Shot" regroupant des albums indépendants ne doit pas ressortir
    # comme la plus grosse série juste parce qu'il contient beaucoup de fichiers sans lien
    # narratif entre eux. Une série classique avec un one-shot isolé (ex. hors-série) garde
    # son compte normal, seul ce tome-là est exclu.
    top_series_q = (
        select(Series.name, func.count(Tome.id).label("cnt"))
        .join(Tome, Tome.series_id == Series.id)
        .where(Tome.is_oneshot == False)
        .group_by(Series.id, Series.name)
        .order_by(func.count(Tome.id).desc())
    )
    if excluded_series_ids:
        top_series_q = top_series_q.where(Series.id.notin_(excluded_series_ids))
    top_series_row = (await db.execute(top_series_q.limit(1))).first()
    top_series = {"name": top_series_row.name, "count": top_series_row.cnt} if top_series_row else None

    # ── Top 10 séries par nombre de tomes ─────────────────────────────────
    top10_rows = (await db.execute(top_series_q.limit(10))).all()
    top10_series = [{"name": r.name, "count": r.cnt} for r in top10_rows]

    # ── Albums par année (metadata.Year) ──────────────────────────────────
    year_rows = (await db.execute(
        select(Metadata.Year, func.count().label("n"))
        .where(Metadata.Year.isnot(None))
        .where(Metadata.Year != "")
        .group_by(Metadata.Year)
        .order_by(Metadata.Year)
    )).all()
    # Filtrer les années plausibles (1900-2030)
    by_year = [
        {"year": r.Year, "count": r.n}
        for r in year_rows
        if r.Year and r.Year.isdigit() and 1900 <= int(r.Year) <= 2030
    ]

    # ── Éditeurs (top 10) ─────────────────────────────────────────────────
    pub_rows = (await db.execute(
        select(Metadata.Publisher, func.count().label("n"))
        .where(Metadata.Publisher.isnot(None))
        .where(Metadata.Publisher != "")
        .group_by(Metadata.Publisher)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    publishers = [{"name": r.Publisher, "count": r.n} for r in pub_rows]

    # ── Genres ──────────────────────────────────────────────────────────
    # Pas de limit() ici (contrairement à publishers/writers/pencillers) : affiché en
    # treemap, où la longue traîne des genres rares apparaît sous forme de petits blocs,
    # comme le nombre de langues distinctes (voir "languages" plus bas).
    genre_rows = (await db.execute(
        select(Metadata.Genre, func.count().label("n"))
        .where(Metadata.Genre.isnot(None))
        .where(Metadata.Genre != "")
        .group_by(Metadata.Genre)
        .order_by(func.count().desc())
    )).all()
    genres = [{"name": r.Genre, "count": r.n} for r in genre_rows]

    # ── Scénaristes (top 10) ──────────────────────────────────────────────
    writer_rows = (await db.execute(
        select(Metadata.Writer, func.count().label("n"))
        .where(Metadata.Writer.isnot(None))
        .where(Metadata.Writer != "")
        .group_by(Metadata.Writer)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    writers = [{"name": r.Writer, "count": r.n} for r in writer_rows]

    # ── Dessinateurs (top 10) ─────────────────────────────────────────────
    penciller_rows = (await db.execute(
        select(Metadata.Penciller, func.count().label("n"))
        .where(Metadata.Penciller.isnot(None))
        .where(Metadata.Penciller != "")
        .group_by(Metadata.Penciller)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    pencillers = [{"name": r.Penciller, "count": r.n} for r in penciller_rows]

    # ── Album le plus lourd ───────────────────────────────────────────────
    heaviest_q = select(Tome.title, Tome.filename, Tome.file_size).where(Tome.file_size.isnot(None))
    if excluded_series_ids:
        heaviest_q = heaviest_q.where(Tome.series_id.notin_(excluded_series_ids))
    heaviest_row = (await db.execute(heaviest_q.order_by(Tome.file_size.desc()).limit(1))).first()
    heaviest = {
        "name": heaviest_row.title or heaviest_row.filename,
        "size": heaviest_row.file_size,
    } if heaviest_row else None

    # ── Langues ───────────────────────────────────────────────────────────
    lang_rows = (await db.execute(
        select(Metadata.LanguageISO, func.count().label("n"))
        .where(Metadata.LanguageISO.isnot(None))
        .where(Metadata.LanguageISO != "")
        .group_by(Metadata.LanguageISO)
        .order_by(func.count().desc())
    )).all()
    languages = [{"lang": r.LanguageISO, "count": r.n} for r in lang_rows]

    # ── Couverture métadonnées ─────────────────────────────────────────────
    with_meta = (await db.execute(
        select(func.count()).select_from(Tome).where(Tome.has_metadata == True)
    )).scalar() or 0

    avg_size  = round(total_size / tome_count) if tome_count else 0
    avg_pages = round((total_pages or 0) / tome_count) if tome_count else 0

    # ── Séries en cours / finies (statut Bedetheque) ────────────────────────
    ongoing_count = (await db.execute(
        select(func.count()).select_from(Series).where(Series.bedetheque_status == "Série en cours")
    )).scalar() or 0
    finished_count = (await db.execute(
        select(func.count()).select_from(Series).where(Series.bedetheque_status == "Série finie")
    )).scalar() or 0
    unknown_status_count = series_count - ongoing_count - finished_count
    series_status = [
        {"name": "En cours", "count": ongoing_count},
        {"name": "Terminées", "count": finished_count},
        {"name": "Statut inconnu", "count": unknown_status_count},
    ]

    # ── % de séries complètes (suivies, sans album manquant) ────────────────
    # "Complète" n'a de sens que pour une série effectivement comparée à Bedetheque (suivie
    # ET dont l'URL a été résolue avec succès) — une série jamais vérifiée n'est ni complète
    # ni incomplète, juste inconnue, donc exclue du dénominateur plutôt que comptée par défaut.
    tracked_matched_count = (await db.execute(
        select(func.count()).select_from(Series)
        .where(Series.track_new_albums == True, Series.bedetheque_match_status == "found")
    )).scalar() or 0
    incomplete_count = (await db.execute(
        select(func.count(func.distinct(MissingAlbum.series_id)))
        .select_from(MissingAlbum)
        .join(Series, Series.id == MissingAlbum.series_id)
        .where(Series.track_new_albums == True, Series.bedetheque_match_status == "found")
    )).scalar() or 0
    complete_series_count = tracked_matched_count - incomplete_count
    complete_series_pct = round((complete_series_count / tracked_matched_count) * 100) if tracked_matched_count else None

    return {
        "series_count": series_count,
        "tome_count": tome_count,
        "total_size": total_size,
        "avg_size": avg_size,
        "total_pages": total_pages,
        "avg_pages": avg_pages,
        "top_series": top_series,
        "top10_series": top10_series,
        "heaviest": heaviest,
        "by_year": by_year,
        "publishers": publishers,
        "genres": genres,
        "writers": writers,
        "pencillers": pencillers,
        "languages": languages,
        "tomes_without_meta": tome_count - with_meta,
        "series_status": series_status,
        "complete_series_count": complete_series_count,
        "complete_series_total": tracked_matched_count,
        "complete_series_pct": complete_series_pct,
    }


@router.get("/me")
async def get_my_stats(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Statistiques personnelles ("Ma lecture") — propres à l'utilisateur connecté, à
    l'inverse de get_stats ci-dessus qui décrit la bibliothèque partagée. Le temps de
    lecture (ReadingActivity) n'existe qu'à partir de sa mise en service : aucune donnée
    rétroactive pour les albums déjà lus avant."""
    # ── Albums/pages lus ──────────────────────────────────────────────────
    read_rows = (await db.execute(
        select(UserTomeData.last_page, Tome.page_count)
        .join(Tome, Tome.id == UserTomeData.tome_id)
        .where(UserTomeData.user_id == current_user.id, UserTomeData.is_read == True)
    )).all()
    read_count = len(read_rows)
    # Pages lues : page_count si connu (cas normal), sinon last_page en repli (album marqué
    # lu manuellement avant que sa pagination soit connue — rare, mais évite un sous-compte
    # silencieux plutôt qu'une exception).
    pages_read = sum((r.page_count if r.page_count else r.last_page) for r in read_rows)

    in_progress_count = (await db.execute(
        select(func.count()).select_from(UserTomeData)
        .where(UserTomeData.user_id == current_user.id, UserTomeData.is_read == False, UserTomeData.last_page > 0)
    )).scalar() or 0

    # Séries distinctes ayant au moins un album en cours — même critère que in_progress_count
    # ci-dessus (last_page > 0, pas encore marqué lu), regroupé par série plutôt que par tome.
    series_in_progress_count = (await db.execute(
        select(func.count(func.distinct(Tome.series_id)))
        .select_from(UserTomeData)
        .join(Tome, Tome.id == UserTomeData.tome_id)
        .where(UserTomeData.user_id == current_user.id, UserTomeData.is_read == False, UserTomeData.last_page > 0)
    )).scalar() or 0

    # ── Temps de lecture total ────────────────────────────────────────────
    total_seconds = (await db.execute(
        select(func.sum(ReadingActivity.seconds)).where(ReadingActivity.user_id == current_user.id)
    )).scalar() or 0
    avg_seconds_per_read = round(total_seconds / read_count) if read_count else 0

    # ── Série de jours consécutifs de lecture ("streak") ──────────────────
    # Sur l'historique complet (pas seulement les 30 jours d'activity_by_day ci-dessous) :
    # une série peut en théorie dépasser cette fenêtre, mieux vaut la calculer juste une fois
    # sur l'ensemble plutôt que de la borner arbitrairement à 30 jours.
    all_days_rows = (await db.execute(
        select(ReadingActivity.day).where(ReadingActivity.user_id == current_user.id, ReadingActivity.seconds > 0).distinct()
    )).scalars().all()
    current_streak, longest_streak = _compute_streaks(all_days_rows)

    # ── Genres — albums lus ET temps de lecture, réunis par nom de genre. Même convention
    # que get_stats::genres (groupé sur la chaîne Metadata.Genre telle quelle, pas éclatée
    # sur les virgules d'un album multi-genres) pour rester cohérent entre les deux onglets. ──
    genre_read_rows = (await db.execute(
        select(Metadata.Genre, func.count().label("n"))
        .join(Tome, Tome.id == Metadata.tome_id)
        .join(UserTomeData, (UserTomeData.tome_id == Tome.id) & (UserTomeData.user_id == current_user.id))
        .where(UserTomeData.is_read == True, Metadata.Genre.isnot(None), Metadata.Genre != "")
        .group_by(Metadata.Genre)
    )).all()
    genre_seconds_rows = (await db.execute(
        select(Metadata.Genre, func.sum(ReadingActivity.seconds).label("s"))
        .join(Tome, Tome.id == Metadata.tome_id)
        .join(ReadingActivity, (ReadingActivity.tome_id == Tome.id) & (ReadingActivity.user_id == current_user.id))
        .where(Metadata.Genre.isnot(None), Metadata.Genre != "")
        .group_by(Metadata.Genre)
    )).all()
    genre_seconds_by_name = {r.Genre: r.s or 0 for r in genre_seconds_rows}
    by_genre = sorted(
        [
            {"name": r.Genre, "read_count": r.n, "seconds": genre_seconds_by_name.get(r.Genre, 0)}
            for r in genre_read_rows
        ],
        key=lambda g: g["read_count"], reverse=True,
    )

    # ── Activité de lecture, 30 derniers jours (UTC) — jours à 0 explicites, pour un
    # graphique à axe temporel continu plutôt qu'une liste creuse. ──
    since = (datetime.utcnow() - timedelta(days=29)).strftime("%Y-%m-%d")
    day_rows = (await db.execute(
        select(ReadingActivity.day, func.sum(ReadingActivity.seconds).label("s"))
        .where(ReadingActivity.user_id == current_user.id, ReadingActivity.day >= since)
        .group_by(ReadingActivity.day)
    )).all()
    seconds_by_day = {r.day: r.s or 0 for r in day_rows}
    today = datetime.utcnow().date()
    activity_by_day = [
        {"day": (today - timedelta(days=i)).isoformat(), "seconds": seconds_by_day.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(29, -1, -1)
    ]

    # ── Répartition des notes personnelles (1 à 5 étoiles) ────────────────
    rating_rows = (await db.execute(
        select(UserTomeData.rating, func.count().label("n"))
        .where(UserTomeData.user_id == current_user.id, UserTomeData.rating.isnot(None))
        .group_by(UserTomeData.rating)
    )).all()
    rating_by_value = {r.rating: r.n for r in rating_rows}
    ratings_distribution = [{"stars": i, "count": rating_by_value.get(i, 0)} for i in range(1, 6)]

    return {
        "read_count": read_count,
        "pages_read": pages_read,
        "in_progress_count": in_progress_count,
        "series_in_progress_count": series_in_progress_count,
        "total_seconds": total_seconds,
        "avg_seconds_per_read": avg_seconds_per_read,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "by_genre": by_genre,
        "activity_by_day": activity_by_day,
        "ratings_distribution": ratings_distribution,
    }
