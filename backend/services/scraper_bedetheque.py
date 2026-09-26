"""
Bedetheque scraper.

Écrit intégralement à neuf par inspection de pages réelles (session de travail dédiée) —
aucun code repris d'un projet tiers (l'unique scraper Bedetheque public trouvé est un
script ComicRack en IronPython 2.7, sans licence, de toute façon incompatible).

L'endpoint officiel de recherche (/search/tout) sert une page dégradée sans résultats
aux clients non-navigateur — vérifié empiriquement des deux côtés (serveur et navigateur
réel), indépendant du blocage IP. Contournement légitime, pas d'évasion de protection :
les pages d'index alphabétique (bandes_dessinees_X.html) et les fiches séries sont du
contenu statique non protégé, et fonctionnent normalement pour un client HTTP honnête.

Architecture :
  - Index local {nom de série: url}, livré pré-construit avec l'app (scraper_data/),
    copié vers COVER_CACHE_DIR/../bedetheque_index.json au premier démarrage si absent.
    Rafraîchissable manuellement depuis Configuration (requêtes espacées, en tâche de
    fond — voir build_index).
  - Recherche = consultation de l'index (aucun réseau) puis une seule requête par série
    trouvée vers sa page complète (suffixe __10000 = tous les albums sans pagination).
"""
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from ..config import settings
from .http_client import BEDETHEQUE, ServiceError

BASE = "https://www.bedetheque.com"

_ALLOWED_HOSTS = {"bedetheque.com", "www.bedetheque.com"}


def is_bedetheque_url(url: str) -> bool:
    """Un utilisateur (pas seulement l'admin — library.read/library.missing_albums
    suffisent selon l'endpoint) peut fournir cette URL, qui est ensuite fetchée
    côté serveur : sans cette vérification, c'est une SSRF permettant de faire requêter
    au serveur n'importe quelle adresse du réseau local du NAS. startswith("http") seul
    (vérification historique sur ces endpoints) ne protège de rien."""
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _ALLOWED_HOSTS
LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["0"]  # "0" = séries commençant par un chiffre

_BUNDLED_INDEX = Path(__file__).parent.parent / "scraper_data" / "bedetheque_index.json"

_build_progress: dict = {"status": "idle", "processed": 0, "total": len(LETTERS)}


def _index_path() -> Path:
    # Sibling de COVER_CACHE_DIR (donc dans /data en Docker) — pas dans le dossier
    # covers/ lui-même pour ne pas être confondu avec le cache d'images.
    return Path(settings.COVER_CACHE_DIR).parent / "bedetheque_index.json"


def ensure_index_bootstrapped() -> None:
    """Copie l'index pré-construit vers /data au tout premier démarrage."""
    dest = _index_path()
    if not dest.exists() and _BUNDLED_INDEX.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_BUNDLED_INDEX, dest)


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _text_without_links(el) -> str:
    """Texte d'un élément, liens internes retirés — le bloc résumé (album ou série) contient
    parfois le propre lien "Lire la suite" de Bedetheque.com à sa suite ; sans ce retrait,
    get_text() l'incluait tel quel dans le résumé stocké, doublonnant avec le lien "Lire la
    suite" ajouté côté frontend."""
    for a in el.find_all("a"):
        a.decompose()
    return el.get_text(" ", strip=True)


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


# Bedetheque range les séries par mot significatif : "Grand pouvoir du Chninkel (Le)",
# "Île noire (L')", ou avec du texte après l'article : "Dynastie Donald Duck (La) -
# Intégrale Carl Barks". Utile pour trier, pas pour afficher ni pour chercher (une
# requête "La Dynastie..." ne matchait pas tant que l'article restait à la fin) — on le
# remet en tête dans tous les cas, pas seulement quand il termine la chaîne.
_ARTICLE_RE = re.compile(r"^(.*?)\s*\((L'|Le|La|Les|Un|Une)\)\s*(.*)$")


def _reorder_article(name: str) -> str:
    m = _ARTICLE_RE.match(name)
    if not m:
        return name
    prefix, article, suffix = m.group(1), m.group(2), m.group(3)
    sep = "" if article == "L'" else " "
    return _clean_text(f"{article}{sep}{prefix} {suffix}")


# Bedetheque affiche les auteurs "Nom, Prénom" (ex. "Barks, Carl"). En plus d'être peu
# naturel à l'affichage, la virgule fait croire à l'app que ce sont deux auteurs distincts
# séparés par une virgule (convention multi-valeurs utilisée partout ailleurs) — d'où
# "Carl" et "Barks" comptés comme deux personnes sur la page Auteurs. On remet en ordre
# naturel "Prénom Nom" pour éviter les deux problèmes à la source.
def _reformat_author(name: str) -> str:
    parts = name.split(",", 1)
    if len(parts) != 2:
        return name
    lastname, firstname = parts[0].strip(), parts[1].strip()
    if not lastname or not firstname:
        return name
    return f"{firstname} {lastname}"


def _series_all_url(series_url: str) -> str:
    """Variante d'URL qui affiche tous les albums d'une série sans pagination. Idempotent :
    une URL déjà au format __10000.html (ex. saisie manuellement par l'utilisateur) ne doit
    pas se retrouver doublée en ...__10000__10000.html."""
    if series_url.endswith("__10000.html"):
        return series_url
    return re.sub(r"\.html$", "__10000.html", series_url)


# ── Construction / rafraîchissement de l'index ──────────────────────────────────────

def get_build_progress() -> dict:
    return dict(_build_progress)


def index_status() -> dict:
    path = _index_path()
    if not path.exists():
        return {"built": False, "count": 0, "built_at": None}
    try:
        count = len(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        count = 0
    return {"built": True, "count": count, "built_at": path.stat().st_mtime}


async def build_index(letters: Optional[list[str]] = None) -> int:
    """Télécharge les pages d'index A-Z (ou un sous-ensemble) et (re)construit l'index.
    Requêtes espacées par le client commun (http_client.BEDETHEQUE) — grosse opération
    ponctuelle, uniquement manuelle."""
    global _build_progress
    letters = letters or LETTERS
    _build_progress = {"status": "running", "processed": 0, "total": len(letters)}

    index: dict[str, str] = {}
    try:
        for i, letter in enumerate(letters):
            try:
                resp = await BEDETHEQUE.get(f"{BASE}/bandes_dessinees_{letter}.html")
                soup = BeautifulSoup(resp.text, "html.parser")
                for li in soup.find_all("li"):
                    a = li.find("a", href=True)
                    span = li.find("span", class_="libelle")
                    if a and span and "/serie-" in a["href"]:
                        name = _reorder_article(_clean_text(span.get_text()))
                        if name:
                            index[name] = a["href"]
            except ServiceError:
                pass  # une lettre en échec ne doit pas bloquer les suivantes
            _build_progress["processed"] = i + 1

        # Fusionne avec l'index existant plutôt que de l'écraser si on ne rafraîchit
        # qu'un sous-ensemble de lettres
        dest = _index_path()
        if letters != LETTERS and dest.exists():
            try:
                existing = json.loads(dest.read_text(encoding="utf-8"))
                existing.update(index)
                index = existing
            except Exception:
                pass

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        _build_progress["status"] = "done"
    except Exception as e:
        _build_progress["status"] = "error"
        _build_progress["error"] = str(e)
    return len(index)


def _load_index() -> dict[str, str]:
    path = _index_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _search_series(query: str, index: dict[str, str], max_series: int = 3) -> list[tuple[str, str]]:
    nq = _normalize(query)
    if not nq:
        return []
    matches = [(name, url) for name, url in index.items() if nq in _normalize(name)]
    matches.sort(key=lambda item: (not _normalize(item[0]).startswith(nq), item[0]))
    return matches[:max_series]


# ── Parsing d'une page série (tous les albums, un seul fetch) ──────────────────────

def _parse_album_block(side, main) -> Optional[dict]:
    title_el = main.select_one("h3 span[itemprop=name]") or main.find("h3", class_="titre")
    raw_title = _clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
    number = None
    m = re.match(r"^(\S+)\s*\.\s*(.*)$", raw_title)
    title = m.group(2) if m else raw_title
    if m:
        number = m.group(1)

    url_el = main.select_one("h3 a.titre")
    album_url = url_el["href"] if url_el and url_el.get("href") else None

    fields: dict[str, str] = {}
    for li in main.select("ul.infos > li"):
        label_el = li.find("label")
        if not label_el:
            continue
        label = _clean_text(label_el.get_text()).rstrip(":").strip()
        value = _clean_text(li.get_text(" ", strip=True))
        value = value.replace(_clean_text(label_el.get_text()), "", 1).strip(": ").strip()
        if label in ("Scénario", "Dessin", "Couleurs"):
            value = _reformat_author(value)
        fields.setdefault(label, value)

    year = None
    if "Dépot légal" in fields:
        ym = re.search(r"(19|20)\d{2}", fields["Dépot légal"])
        if ym:
            year = ym.group(0)

    cover_url = None
    if side is not None:
        # Certains albums (mis en avant ?) ont une icône de coin décorative
        # (bdgest.com/skin/corner.top.left.png) en premier <img> de div.couv, avant la
        # vraie couverture — sans cette exclusion, select_one("div.couv img") la prenait
        # par erreur (premier match) au lieu de la couverture.
        img = side.select_one("div.couv img:not(.corner-top-left)")
        if img and img.get("src"):
            cover_url = img["src"]

    if not title and not album_url:
        return None

    authors = [a for a in (fields.get("Scénario"), fields.get("Dessin")) if a]
    authors = list(dict.fromkeys(authors))  # dédoublonne (auteur complet scénario+dessin)

    # Note communautaire — "Note: 4.7/5 (27 votes)" dans <p class="message"> sous le
    # widget d'étoiles cliquables, dans le même bloc que le reste des infos de l'album.
    rating = None
    rating_count = None
    msg_el = main.select_one("p.message")
    if msg_el:
        rm = re.search(r"Note\s*:\s*([\d.,]+)\s*/\s*5\s*\(\s*(\d+)\s*votes?\s*\)", msg_el.get_text(" ", strip=True))
        if rm:
            try:
                rating = float(rm.group(1).replace(",", "."))
                rating_count = int(rm.group(2))
            except ValueError:
                pass

    return {
        "title": title,
        "number": number,
        "authors": authors,
        "writer": fields.get("Scénario"),
        "penciller": fields.get("Dessin"),
        "publisher": fields.get("Editeur"),
        "year": year,
        "cover_url": cover_url,
        "url": album_url,
        "isbn": fields.get("ISBN") or None,
        "pages": None,
        "rating": rating,
        "rating_count": rating_count,
        "source": "bedetheque",
    }


def _parse_series_info(html: str) -> dict:
    """Statut ("Série finie"/"Série en cours"), genre et résumé de la série — présents aussi
    bien sur la page de base que sur la variante __10000.html (déjà récupérée pour la liste
    des albums, aucune requête supplémentaire nécessaire pour ces trois infos)."""
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one("div.bandeau-info.serie")
    status = None
    genre = None
    if info is not None:
        h3 = info.find("h3")
        if h3 is not None:
            icon = h3.find("i", class_="icon-info-sign")
            if icon is not None and icon.parent is not None:
                status = _clean_text(icon.parent.get_text(" ", strip=True))
            genre_el = h3.find("span", class_="style")
            if genre_el is not None:
                genre = _clean_text(genre_el.get_text(" ", strip=True))
    resume_el = soup.select_one("div.single-content.serie p")
    resume = _clean_text(_text_without_links(resume_el)) if resume_el is not None else None
    return {"status": status, "genre": genre, "resume": resume or None}


def _parse_album_summary(html: str) -> str | None:
    """Résumé d'un album — présent seulement sur sa page dédiée (pas sur la page série),
    donc une requête à part, jamais faite en masse (voir fetch_album_summary)."""
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("div.bandeau-info.album p.auto-height span")
    if el is None:
        return None
    text = _clean_text(_text_without_links(el))
    return text or None


async def fetch_album_summary(album_url: str) -> str | None:
    """Résumé d'un album précis, récupéré à la demande (sélection d'un résultat de recherche
    unique) — jamais en masse : multiplierait les requêtes par le nombre d'albums d'une série
    pour un "Compléter" ou un import en lot."""
    try:
        resp = await BEDETHEQUE.get(album_url)
    except ServiceError as e:
        if e.kind == "not_found":
            return None
        raise
    return _parse_album_summary(resp.text)


def _parse_series_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    sides = soup.find_all("div", class_="album-side")
    mains = soup.find_all("div", class_="album-main")
    results = []
    for side, main in zip(sides, mains):
        block = _parse_album_block(side, main)
        if block:
            results.append(block)
    return results


_TRAILING_NUMBER_RE = re.compile(r"^(.*\S)\s+(\d{1,3})\s*$")


def _extract_wanted_number(query: str) -> tuple[str, Optional[str]]:
    """Isole un éventuel numéro de tome en fin de requête (le champ se préremplit avec
    "Série + Numéro", ex. "Garfield 78") — sans ça, l'index (noms de série uniquement) ne
    matcherait jamais rien pour une requête se terminant par un chiffre."""
    m = _TRAILING_NUMBER_RE.match(query)
    if m:
        return m.group(1), m.group(2).lstrip("0") or "0"
    return query, None


def _promote_wanted(albums: list[dict], wanted_number: Optional[str]) -> list[dict]:
    """Fait remonter en tête l'album correspondant au numéro recherché — le reste garde
    l'ordre naturel de la page Bedetheque (tri stable)."""
    if not wanted_number:
        return albums
    return sorted(albums, key=lambda a: (a.get("number") or "").lstrip("0") != wanted_number)


async def fetch_series_page_albums(series_url: str, series_name: str) -> list[dict]:
    """Récupère TOUS les albums d'une série déjà identifiée via son URL Bedetheque directe
    (pas de recherche floue par nom) — utilisé quand la série locale possède déjà une URL
    Bedetheque confirmée : résultat complet et sans ambiguïté, contrairement à
    search_bedetheque() qui doit deviner parmi plusieurs séries candidates du même nom
    (ex. "Garfield" a 19 séries différentes sur Bedetheque — variantes, éditions, langues…)."""
    try:
        resp = await BEDETHEQUE.get(_series_all_url(series_url))
    except ServiceError as e:
        if e.kind == "not_found":
            return []
        raise  # panne passagère : erreur claire plutôt que « aucun album »
    albums = _parse_series_page(resp.text)
    for album in albums:
        album["series"] = series_name
    return albums


async def search_bedetheque(query: str) -> list[dict]:
    series_query, wanted_number = _extract_wanted_number(query)

    index = _load_index()
    series_matches = _search_series(series_query, index, max_series=3)
    if not series_matches:
        return []

    all_results: list[dict] = []
    for series_name, series_url in series_matches:
        try:
            resp = await BEDETHEQUE.get(_series_all_url(series_url))
        except ServiceError as e:
            if e.kind == "not_found":
                continue
            raise
        albums = _parse_series_page(resp.text)
        for album in albums:
            album["series"] = series_name
        all_results.extend(albums)

    return _promote_wanted(all_results, wanted_number)
