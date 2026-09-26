"""
Détection d'albums manquants — s'appuie sur le scraper Bedetheque (services/scraper_bedetheque)
pour comparer, série par série, les numéros d'albums publiés avec ceux présents dans la
bibliothèque locale.

Ne considère que les albums à numérotation purement numérique (Bedetheque numérote aussi des
hors-séries "HS1", "HS01a", intégrales "INT01", best-of "BOBD" etc. — non comparables à une
suite de tomes classique, donc ignorés ici).

Comparaison par différence d'ensembles (pas seulement "au-dessus du dernier tome connu") :
détecte aussi bien un nouveau tome qu'un trou dans la collection.
"""
from typing import Callable, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import Series, Tome, Metadata, MissingAlbum, IgnoredMissingAlbum
from . import scraper_bedetheque as bd
from .http_client import BEDETHEQUE, ServiceError


def _resolve_series_url(name: str, index: dict[str, str]) -> Optional[str]:
    """Résolution volontairement prudente : correspondance exacte (normalisée) en priorité ;
    à défaut, correspondance approchante uniquement si un seul candidat possible — mieux vaut
    classer une série "non trouvée" que lui associer par erreur les albums d'une autre."""
    # Les noms de l'index sont réordonnés à la construction (bd._reorder_article) : "X (Le)"
    # → "Le X". On applique le même réordonnement ici, sinon un nom local encore au format
    # brut Bedetheque ("Guide du Mauvais Père (Le)") ne matche jamais l'entrée d'index
    # correspondante ("Le Guide du Mauvais Père").
    name = bd._reorder_article(name)
    nq = bd._normalize(name)
    if not nq:
        return None
    for iname, url in index.items():
        if bd._normalize(iname) == nq:
            return url
    # Bedetheque ajoute parfois un suffixe au nom "canonique" (ex. "La Dynastie Donald
    # Duck - Intégrale Carl Barks") — on accepte que le nom local soit un préfixe/sous-
    # chaîne du nom complet, jamais l'inverse (sinon un nom d'index très court comme "Al"
    # matcherait n'importe quelle requête plus longue qui le contient).
    candidates = {url for iname, url in index.items() if nq in bd._normalize(iname)}
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _numeric(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    v = value.strip()
    return int(v) if v.isdigit() else None


async def sync_series_from_html(db: AsyncSession, series: Series, html: str) -> list[dict]:
    """Parse une page série Bedetheque déjà récupérée et met à jour : statut/genre/résumé de
    la série, note communautaire + genre des albums possédés. Renvoie la liste des albums
    parsés (l'appelant s'en sert ensuite pour son propre besoin — albums manquants ici,
    complétion des champs d'un album dans routers/library.py). Factorisé pour ne pas dupliquer
    ce traitement entre le scan "Albums manquants" et "Compléter les métadonnées" — les deux
    en avaient chacun leur propre copie, désynchronisable au prochain correctif de l'un des
    deux sans toucher l'autre."""
    albums = bd._parse_series_page(html)
    series_info = bd._parse_series_info(html)
    series.bedetheque_status = series_info.get("status")
    series.bedetheque_resume = series_info.get("resume")
    genre = series_info.get("genre")

    owned_result = await db.execute(
        select(Tome, Metadata).outerjoin(Metadata, Metadata.tome_id == Tome.id).where(Tome.series_id == series.id)
    )
    owned_by_number: dict[int, tuple[Tome, Metadata | None]] = {}
    for tome, meta in owned_result.all():
        n = _numeric(tome.number)
        if n is not None:
            owned_by_number[n] = (tome, meta)

    # Note communautaire + genre pour les albums possédés — seulement en base (jamais réécrit
    # dans le fichier automatiquement, ce n'est pas une correction voulue par l'utilisateur
    # comme les autres champs, juste une info affichée dans l'app, rafraîchie à chaque sync).
    for album in albums:
        n = _numeric(album.get("number"))
        if n is None or n not in owned_by_number:
            continue
        rating = album.get("rating")
        if rating is None and not genre:
            continue
        tome, meta = owned_by_number[n]
        if meta is None:
            meta = Metadata(tome_id=tome.id)
            db.add(meta)
            owned_by_number[n] = (tome, meta)
        if rating is not None:
            meta.CommunityRating = str(rating)
            meta.bedetheque_votes = album.get("rating_count")
        if genre and not meta.Genre:
            meta.Genre = genre

    return albums


async def _scan_one_series(db: AsyncSession, index: dict[str, str], series: Series) -> None:
    """Lève ServiceError (panne passagère de Bedetheque) SANS avoir rien modifié : la page est
    lue avant toute écriture, la série garde son état (URL, statut, albums manquants connus)."""
    async def clear_missing():
        # Toujours nettoyés puis, si le suivi est actif, recalculés plus bas — sinon les entrées
        # d'une série dont le suivi vient d'être désactivé resteraient affichées indéfiniment.
        await db.execute(delete(MissingAlbum).where(MissingAlbum.series_id == series.id))

    # Une URL déjà CONFIRMÉE (match_status="found" — résolue puis vérifiée avec succès, ou
    # saisie/corrigée manuellement) n'est plus jamais re-devinée par nom : une correction
    # manuelle ne doit jamais être silencieusement écrasée au scan suivant. En revanche une
    # URL en échec ("not_found" : jamais chargée avec succès, ex. lien périmé d'un ancien
    # scan) retente une résolution fraîche à chaque scan — sinon une entrée déjà cassée avant
    # ce correctif resterait figée pour toujours sans que personne n'ait besoin d'intervenir.
    url = series.bedetheque_url if series.bedetheque_match_status == "found" else None
    if not url:
        url = _resolve_series_url(series.name, index)

    if not url:
        await clear_missing()
        series.bedetheque_url = None
        series.bedetheque_match_status = "not_found"
        return

    # Rythme (délai de courtoisie entre deux pages) : client commun http_client.BEDETHEQUE.
    try:
        resp = await BEDETHEQUE.get(bd._series_all_url(url))
    except ServiceError as e:
        if e.kind == "not_found":
            await clear_missing()
            series.bedetheque_url = url
            series.bedetheque_match_status = "not_found"
            return
        # Panne passagère (site lent, 5xx, réseau) : rien n'est conclu sur cette série. Avant,
        # elle passait en "not_found" — son URL confirmée était alors re-devinée par nom au
        # scan suivant (risque de mauvaise série) et « Compléter » la refusait.
        raise

    await clear_missing()
    series.bedetheque_url = url
    series.bedetheque_match_status = "found"
    albums = await sync_series_from_html(db, series, resp.text)

    # Suivi désactivé pour cette série : statut/genre/résumé/note communautaire viennent
    # d'être rafraîchis ci-dessus pour tout le monde, mais les albums manquants ne sont
    # calculés/affichés que pour les séries suivies (voir Series.track_new_albums) — ils
    # restent donc supprimés (nettoyage en tout début de fonction).
    if not series.track_new_albums:
        return

    numeric_albums = [a for a in albums if _numeric(a.get("number")) is not None]
    owned_result = await db.execute(select(Tome.number).where(Tome.series_id == series.id))
    owned_numbers = {_numeric(n) for (n,) in owned_result.all()}
    owned_numbers.discard(None)

    ignored = await db.execute(select(IgnoredMissingAlbum.number).where(IgnoredMissingAlbum.series_id == series.id))
    ignored_numbers = {_numeric(n) for (n,) in ignored.all()}

    missing = [
        a for a in numeric_albums
        if _numeric(a["number"]) not in owned_numbers and _numeric(a["number"]) not in ignored_numbers
    ]

    # Pas de fetch de la page album individuelle (résumé) : coûteux (1 requête par album
    # manquant) pour un gain marginal — titre/couverture/année sont déjà gratuits depuis
    # la page série, et le lien Bedetheque reste cliquable pour qui veut le résumé complet.
    for album in missing:
        db.add(MissingAlbum(
            series_id=series.id,
            number=album["number"],
            title=album.get("title"),
            cover_url=album.get("cover_url"),
            year=album.get("year"),
            bedetheque_url=album.get("url"),
            writer=album.get("writer"),
            penciller=album.get("penciller"),
            publisher=album.get("publisher"),
        ))


async def scan_all(db: AsyncSession, progress_cb: Callable[[int, int], None]) -> None:
    """Scanne désormais TOUTES les séries (pas seulement celles suivies) : statut/genre/
    résumé sont rafraîchis pour toutes, mais les albums manquants ne sont calculés/affichés
    que pour celles avec le suivi actif (Series.track_new_albums — voir _scan_one_series)."""
    index = bd._load_index()

    result = await db.execute(select(Series).order_by(Series.name))
    all_series = list(result.scalars().all())
    progress_cb(0, len(all_series))

    for i, series in enumerate(all_series):
        try:
            await _scan_one_series(db, index, series)
            await db.commit()
        except ServiceError:
            # Série laissée telle quelle (rien n'a été modifié) — la suivante a sa chance, le
            # scan ne s'arrête pas pour une panne passagère.
            pass
        progress_cb(i + 1, len(all_series))


async def scan_series(db: AsyncSession, series: Series) -> None:
    """Re-vérifie une seule série (ex: juste après réactivation du suivi) — pas besoin
    d'attendre le prochain scan complet de toute la bibliothèque pour voir le résultat."""
    index = bd._load_index()
    await _scan_one_series(db, index, series)  # ServiceError : rien n'a été modifié
    await db.commit()
