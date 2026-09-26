from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import require_permission
from ..database import get_db
from ..models.db_models import Series
from ..models.schemas import (
    ScraperQueryIn, ScraperResultOut, BedethequeBulkIn, BedethequeBulkAlbumOut,
    BedethequeSuggestIn, BedethequeSuggestOut, BedethequeAlbumSummaryIn, BedethequeAlbumSummaryOut,
)
from ..services.scraper_google import search_google_books
from ..services.http_client import BEDETHEQUE, ServiceError
from ..services.scraper_comicvine import search_comicvine
from ..services.scraper_bedetheque import (
    search_bedetheque, fetch_series_page_albums, _extract_wanted_number, _promote_wanted,
    _load_index, _search_series, _series_all_url, _parse_series_page, _parse_series_info, fetch_album_summary, is_bedetheque_url,
)
from ..services.rate_limit import RateLimiter
from ..config import settings

# 20 requêtes / minute, tous clients confondus — largement assez pour un usage interactif
# normal (recherche fichier par fichier pendant un import), assez bas pour empêcher une
# boucle d'abuser du service tiers via cette instance.
_scrape_rate_limiter = RateLimiter(max_calls=20, period_seconds=60)

router = APIRouter(
    prefix="/api/scrape", tags=["scraper"],
    dependencies=[Depends(require_permission("library.read")), Depends(_scrape_rate_limiter)],
)

# Bedetheque n'a pas d'API officielle (contrairement à Google Books/ComicVine) — limite
# dédiée plus stricte, en plus de la limite partagée ci-dessus, pour rester très en deçà
# de tout seuil comportemental.
_bedetheque_rate_limiter = RateLimiter(max_calls=6, period_seconds=60)


@router.post("/googlebooks", response_model=list[ScraperResultOut])
async def scrape_google(body: ScraperQueryIn):
    query = body.query
    if not query:
        # Build query from fields
        parts = []
        if body.series:
            parts.append(body.series)
        if body.number:
            import re
            num = re.sub(r"\D", "", body.number)
            if num:
                parts.append(num)
        if body.author:
            parts.append(body.author)
        query = " ".join(parts)

    if not query:
        raise HTTPException(status_code=400, detail="Requête vide")

    results = await search_google_books(query, api_key=settings.GOOGLE_BOOKS_API_KEY)
    return [ScraperResultOut(**r) for r in results]


@router.post("/comicvine", response_model=list[ScraperResultOut])
async def scrape_comicvine(body: ScraperQueryIn):
    if not settings.COMICVINE_API_KEY:
        raise HTTPException(status_code=400, detail="Clé API ComicVine non configurée")

    query = body.query or body.series or ""
    if not query:
        raise HTTPException(status_code=400, detail="Requête vide")

    results = await search_comicvine(query, api_key=settings.COMICVINE_API_KEY)
    return [ScraperResultOut(**r) for r in results]


@router.post("/bedetheque", response_model=list[ScraperResultOut], dependencies=[Depends(_bedetheque_rate_limiter)])
async def scrape_bedetheque(body: ScraperQueryIn, db: AsyncSession = Depends(get_db)):
    query = body.query or body.series or ""
    if not query:
        raise HTTPException(status_code=400, detail="Requête vide")

    # Série locale déjà identifiée avec une URL Bedetheque confirmée : on va chercher
    # directement dedans plutôt que de deviner la bonne série par son nom (recherche floue
    # ambiguë dès que plusieurs séries Bedetheque partagent un nom proche — ex. une vingtaine
    # de séries "Garfield..." différentes).
    if body.series_id:
        result = await db.execute(select(Series).where(Series.id == body.series_id))
        series = result.scalar_one_or_none()
        if series and series.bedetheque_url and series.bedetheque_match_status == "found":
            _, wanted_number = _extract_wanted_number(query)
            albums = await fetch_series_page_albums(series.bedetheque_url, series.name)
            results = _promote_wanted(albums, wanted_number)
            return [ScraperResultOut(**r) for r in results]

    results = await search_bedetheque(query)
    return [ScraperResultOut(**r) for r in results]


@router.post("/bedetheque-bulk", response_model=list[BedethequeBulkAlbumOut], dependencies=[Depends(_bedetheque_rate_limiter)])
async def scrape_bedetheque_bulk(body: BedethequeBulkIn, db: AsyncSession = Depends(get_db)):
    """Récupère TOUS les albums d'une page série Bedetheque en un seul appel — utilisé à
    l'import pour préremplir le tableau de métadonnées par numéro d'album, plutôt que de
    chercher fichier par fichier. Nouvelle série : URL fournie directement. Série existante :
    series_id, dont l'URL Bedetheque déjà confirmée est relue en base — évite de refaire
    deviner/confirmer une URL déjà connue à chaque import dans cette série."""
    url = (body.url or "").strip()
    if body.series_id:
        result = await db.execute(select(Series).where(Series.id == body.series_id))
        series = result.scalar_one_or_none()
        if series is None:
            raise HTTPException(status_code=404, detail="Série introuvable")
        if not series.bedetheque_url or series.bedetheque_match_status != "found":
            raise HTTPException(status_code=400, detail="Aucune URL Bedetheque confirmée pour cette série")
        url = series.bedetheque_url

    if not url or not is_bedetheque_url(url):
        raise HTTPException(status_code=400, detail="URL invalide (doit être une page bedetheque.com)")

    albums = await fetch_series_page_albums(url, "")
    if not albums:
        raise HTTPException(status_code=502, detail="Impossible de charger cette page Bedetheque, ou aucun album trouvé")
    return [BedethequeBulkAlbumOut(**a) for a in albums]


_SUGGEST_LIMIT = 5  # 1 fetch Bedetheque.com par candidat — reste volontairement bas


@router.post("/bedetheque-suggest", response_model=list[BedethequeSuggestOut], dependencies=[Depends(_bedetheque_rate_limiter)])
async def scrape_bedetheque_suggest(body: BedethequeSuggestIn):
    """Propose jusqu'à _SUGGEST_LIMIT séries Bedetheque candidates pour un nom donné
    (création d'une nouvelle série à l'import) — index local pour le matching (instantané,
    trié par proximité du nom), puis un fetch par candidat pour donner assez d'infos
    (nombre d'albums, statut, années) pour choisir sans ouvrir Bedetheque.com. Au-delà de
    ces _SUGGEST_LIMIT résultats, l'utilisateur colle l'URL manuellement (lien de secours
    dans la popup) plutôt que de multiplier les requêtes au site tiers."""
    name = body.name.strip()
    if not name:
        return []

    index = _load_index()
    candidates = _search_series(name, index, max_series=_SUGGEST_LIMIT)
    if not candidates:
        return []

    results = []
    for cand_name, url in candidates:
        try:
            resp = await BEDETHEQUE.get(_series_all_url(url))
        except ServiceError as e:
            if e.kind == "not_found":
                continue
            raise
        albums = _parse_series_page(resp.text)
        info = _parse_series_info(resp.text)
        years = sorted(a["year"] for a in albums if a.get("year"))
        results.append(BedethequeSuggestOut(
            name=cand_name,
            url=url,
            album_count=len(albums),
            status=info.get("status"),
            year_min=years[0] if years else None,
            year_max=years[-1] if years else None,
        ))
    return results


@router.post("/bedetheque-album-summary", response_model=BedethequeAlbumSummaryOut, dependencies=[Depends(_bedetheque_rate_limiter)])
async def scrape_bedetheque_album_summary(body: BedethequeAlbumSummaryIn):
    """Résumé d'un album précis — page dédiée à l'album, jamais présente sur la page série
    déjà récupérée ailleurs. Appelé uniquement à la sélection d'un résultat de recherche
    (une requête), jamais en masse."""
    url = body.url.strip()
    if not url or not is_bedetheque_url(url):
        raise HTTPException(status_code=400, detail="URL invalide (doit être une page bedetheque.com)")
    summary = await fetch_album_summary(url)
    return BedethequeAlbumSummaryOut(summary=summary)
