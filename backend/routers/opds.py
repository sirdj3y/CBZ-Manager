"""
Catalogue OPDS (Open Publication Distribution System) — permet de parcourir/télécharger la
bibliothèque depuis une app de lecture dédiée (Chunky, Panels, Yacreader...) plutôt que le
lecteur web intégré.

Authentification dédiée, isolée de dependencies.auth_required : les apps OPDS envoient un
header HTTP Basic sur CHAQUE requête (pas de cookie de session), donc pas la même mécanique
que le reste de l'app — inutile de complexifier le chemin d'auth par cookie (revu/durci lors
de l'audit de sécurité) pour ce cas. Voir require_opds_user ci-dessous.
"""
import asyncio
import base64
import binascii
import hashlib
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import _profile_permissions
from ..models.db_models import Metadata, Series, Tome, User
from ..services import auth as auth_service
from ..services import page_extractor
from ..services.cover_cache import ensure_cover
from ..services.hidden_series import get_user_excluded_series_ids
from ..services.rate_limit import PerKeyRateLimiter
from .auth import get_client_ip
from .library import _split_multi
from .tomes import _content_disposition

router = APIRouter(prefix="/opds", tags=["opds"])

ATOM_NS = "http://www.w3.org/2005/Atom"
ET.register_namespace("", ATOM_NS)

# OPDS-PSE (Page Streaming Extension, https://github.com/anansi-project/opds-pse) — extension
# non-officielle mais largement supportée (Chunky compris) qui permet à un lecteur de
# demander UNE page en JPEG plutôt que de télécharger tout l'album avant de pouvoir en
# afficher la première image. Namespace vérifié auprès de la spec source
# (https://vaemendis.net/opds-pse/), pas deviné.
PSE_NS = "http://vaemendis.net/opds-pse/ns"
PSE_REL = "http://vaemendis.net/opds-pse/stream"
ET.register_namespace("pse", PSE_NS)


# ── Authentification Basic dédiée ───────────────────────────────────────────────

# Identifiants déjà vérifiés récemment (clé = hash du header Authorization complet) —
# sans ça, une app OPDS qui charge une page + N miniatures de couverture déclencherait N
# vérifications bcrypt (~100-300 ms chacune, bloquant la boucle d'événements à chaque fois,
# même défaut que documenté pour /api/auth/login avant l'audit). Ne cache QUE le mot de
# passe vérifié, jamais la permission : celle-ci est revérifiée en base à chaque requête
# (cache hit ou non) pour qu'une révocation de droits reste immédiate, même principe que
# require_permission côté cookie.
_CACHE_TTL = 300  # 5 min
_verified_cache: dict[str, tuple[int, float]] = {}  # header_hash -> (user_id, expires_at)

# Même raisonnement que le rate-limit de /api/auth/login : OPDS est une seconde porte
# d'entrée avec mot de passe, doit être protégée pareil contre le brute-force. Ne compte
# que les tentatives avec des identifiants pas encore en cache (voir require_opds_user) —
# jamais les requêtes répétées légitimes d'une app qui recharge son catalogue.
_opds_rate_limiter = PerKeyRateLimiter(max_calls=20, period_seconds=60)


def require_opds_user(permission: str = "library.read"):
    async def _check(request: Request, db: AsyncSession = Depends(get_db)) -> User:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Basic "):
            raise HTTPException(
                status_code=401, detail="Authentification requise",
                headers={"WWW-Authenticate": 'Basic realm="CBZ Manager OPDS"'},
            )

        cache_key = hashlib.sha256(auth_header.encode()).hexdigest()
        cached = _verified_cache.get(cache_key)
        user_id: int | None = None
        cached_token_version: int | None = None
        if cached and cached[1] > time.monotonic():
            user_id, cached_token_version = cached[0], cached[2]
        else:
            _opds_rate_limiter.check(get_client_ip(request) or "unknown")
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, _, password = decoded.partition(":")
            except (binascii.Error, UnicodeDecodeError):
                username, password = "", ""
            candidate = await auth_service.get_user_by_username(db, username) if username else None
            valid = candidate is not None and await asyncio.to_thread(
                auth_service.verify_password, password, candidate.password_hash
            )
            if not valid:
                raise HTTPException(
                    status_code=401, detail="Identifiant ou mot de passe incorrect",
                    headers={"WWW-Authenticate": 'Basic realm="CBZ Manager OPDS"'},
                )
            user_id = candidate.id
            cached_token_version = candidate.token_version
            _verified_cache[cache_key] = (user_id, time.monotonic() + _CACHE_TTL, cached_token_version)

        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalide")
        # token_version bumpé à chaque changement de mot de passe (voir routers/auth.py::
        # update_credentials) — sans ce contrôle, un en-tête Basic déjà vérifié restait
        # accepté jusqu'à expiration du cache (5 min) même après un changement de mot de
        # passe, puisque la clé de cache (hash de l'en-tête lui-même) ne change pas tant que
        # le CLIENT continue d'envoyer ses anciens identifiants.
        if user.token_version != cached_token_version:
            _verified_cache.pop(cache_key, None)
            raise HTTPException(
                status_code=401, detail="Identifiant ou mot de passe incorrect",
                headers={"WWW-Authenticate": 'Basic realm="CBZ Manager OPDS"'},
            )
        # Compte provisoire (mot de passe encore par défaut ou temporaire imposé) : OPDS
        # utilise directement le mot de passe en clair sur chaque requête, jamais de
        # redirection possible côté client comme pour l'app web — plus dangereux d'y laisser
        # un mot de passe connu/prévisible actif que d'y bloquer l'accès tant qu'il n'a pas
        # été changé depuis l'app web.
        if user.must_change_password:
            raise HTTPException(
                status_code=403, detail="Mot de passe à changer depuis l'application avant d'utiliser OPDS",
                headers={"WWW-Authenticate": 'Basic realm="CBZ Manager OPDS"'},
            )
        if not user.is_admin and permission not in await _profile_permissions(db, user):
            raise HTTPException(status_code=403, detail="Action non autorisée pour ce profil")
        return user

    return _check


# ── Génération des feeds Atom/OPDS ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, f"{{{ATOM_NS}}}{tag}", attrib=attrs)
    if text is not None:
        el.text = text
    return el


def _feed_response(feed_id: str, title: str, kind: str, self_href: str, build_entries) -> Response:
    root = ET.Element(f"{{{ATOM_NS}}}feed")
    _sub(root, "id", feed_id)
    _sub(root, "title", title)
    _sub(root, "updated", _now_iso())
    feed_type = f"application/atom+xml;profile=opds-catalog;kind={kind}"
    _sub(root, "link", rel="self", href=self_href, type=feed_type)
    _sub(root, "link", rel="start", href="/opds", type="application/atom+xml;profile=opds-catalog;kind=navigation")
    build_entries(root)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(content=xml_bytes, media_type=feed_type)


EXT_TO_MIME = {"cbz": "application/vnd.comicbook+zip", "cbr": "application/vnd.comicbook-rar", "pdf": "application/pdf"}


def _tome_entries(root, tomes: list[Tome]) -> None:
    """Construit une entrée d'acquisition par tome — factorisé, utilisé par le détail de
    série et les flux "par genre/année/auteur/éditeur" plus bas, mêmes champs partout."""
    for t in tomes:
        entry = _sub(root, "entry")
        _sub(entry, "id", f"urn:cbzmanager:tome:{t.id}")
        _sub(entry, "title", t.title or t.filename)
        _sub(entry, "updated", (t.updated_at or datetime.utcnow()).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        mime = EXT_TO_MIME.get(t.file_format, "application/octet-stream")
        _sub(entry, "link", rel="http://opds-spec.org/acquisition", href=f"/opds/tomes/{t.id}/download", type=mime)
        _sub(entry, "link", rel="http://opds-spec.org/image/thumbnail", href=f"/opds/tomes/{t.id}/cover", type="image/jpeg")
        # OPDS-PSE : {pageNumber} est un gabarit littéral que le CLIENT remplace lui-même,
        # jamais interpolé ici — d'où les accolades doublées pour l'échapper dans cette
        # f-string. Uniquement si le nombre de pages est déjà connu (sinon pse:count="0"
        # laisserait croire à un album vide, pire qu'une absence de lien PSE).
        if t.page_count:
            pse_link = _sub(entry, "link", rel=PSE_REL, type="image/jpeg", href=f"/opds/tomes/{t.id}/page/{{pageNumber}}")
            pse_link.set(f"{{{PSE_NS}}}count", str(t.page_count))


# Axes de navigation "par X" — même principe que /opds/series : un flux de navigation
# listant les valeurs distinctes, chacune menant à un flux d'acquisition des albums
# correspondants. rel="subsection"/kind=navigation, cohérent avec /opds/series, préféré aux
# "facets" OPDS (rel=".../facet") pour la compatibilité la plus large possible avec les apps
# de lecture (Chunky compris — toutes ne gèrent pas les facets).
_FACETS = {
    "genres":     ("Genre",     "Par genre"),
    "years":      ("Year",      "Par année"),
    "writers":    ("Writer",    "Par scénariste"),
    "pencillers": ("Penciller", "Par dessinateur"),
    "publishers": ("Publisher", "Par éditeur"),
}


@router.get("")
@router.get("/")
async def opds_root(user: User = Depends(require_opds_user())):
    def entries(root):
        entry = _sub(root, "entry")
        _sub(entry, "id", "urn:cbzmanager:series-all")
        _sub(entry, "title", "Toutes les séries")
        _sub(entry, "updated", _now_iso())
        _sub(entry, "link", rel="subsection", href="/opds/series",
             type="application/atom+xml;profile=opds-catalog;kind=navigation")
        _sub(entry, "content", "Parcourir toutes les séries de la bibliothèque", type="text")

        for facet, (_field, label) in _FACETS.items():
            fentry = _sub(root, "entry")
            _sub(fentry, "id", f"urn:cbzmanager:{facet}")
            _sub(fentry, "title", label)
            _sub(fentry, "updated", _now_iso())
            _sub(fentry, "link", rel="subsection", href=f"/opds/{facet}",
                 type="application/atom+xml;profile=opds-catalog;kind=navigation")
            _sub(fentry, "content", f"Parcourir la bibliothèque {label.lower()}", type="text")

    return _feed_response("urn:cbzmanager:root", "CBZ Manager", "navigation", "/opds", entries)


@router.get("/series")
async def opds_series_list(db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    excluded = await get_user_excluded_series_ids(db, user)
    series_rows = (await db.execute(select(Series).order_by(Series.name))).scalars().all()
    series_rows = [s for s in series_rows if s.id not in excluded]

    # Couverture de chaque série = son cover_tome_id si fixé, sinon le tome au plus petit
    # "number" (même convention que routers/library.py — une seule requête groupée plutôt
    # qu'une par série).
    tome_rows = (await db.execute(select(Tome.id, Tome.series_id).order_by(Tome.series_id, Tome.number))).all()
    first_tome_by_series: dict[int, int] = {}
    for tome_id, series_id in tome_rows:
        first_tome_by_series.setdefault(series_id, tome_id)

    def entries(root):
        for s in series_rows:
            cover_tome_id = s.cover_tome_id or first_tome_by_series.get(s.id)
            entry = _sub(root, "entry")
            _sub(entry, "id", f"urn:cbzmanager:series:{s.id}")
            _sub(entry, "title", s.name)
            _sub(entry, "updated", _now_iso())
            _sub(entry, "link", rel="subsection", href=f"/opds/series/{s.id}",
                 type="application/atom+xml;profile=opds-catalog;kind=acquisition")
            if cover_tome_id:
                _sub(entry, "link", rel="http://opds-spec.org/image/thumbnail",
                     href=f"/opds/tomes/{cover_tome_id}/cover", type="image/jpeg")

    return _feed_response("urn:cbzmanager:series-all", "Toutes les séries", "navigation", "/opds/series", entries)


@router.get("/series/{series_id}")
async def opds_series_detail(series_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    if series_id in await get_user_excluded_series_ids(db, user):
        raise HTTPException(status_code=404, detail="Série introuvable")
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    tomes = (await db.execute(select(Tome).where(Tome.series_id == series_id).order_by(Tome.number))).scalars().all()

    return _feed_response(
        f"urn:cbzmanager:series:{series_id}", series.name, "acquisition", f"/opds/series/{series_id}",
        lambda root: _tome_entries(root, tomes),
    )


@router.get("/tomes/{tome_id}/download")
async def opds_download_tome(tome_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user("library.download"))):
    tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
    if tome is None or tome.series_id in await get_user_excluded_series_ids(db, user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    from pathlib import Path
    if not Path(tome.filepath).is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")
    return FileResponse(
        tome.filepath, media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(tome.filename)},
    )


@router.get("/tomes/{tome_id}/cover")
async def opds_tome_cover(tome_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
    if tome is None or tome.series_id in await get_user_excluded_series_ids(db, user):
        raise HTTPException(status_code=404, detail="Tome introuvable")
    cover_path, _ = await ensure_cover(tome_id, tome.filepath)
    if cover_path is None:
        raise HTTPException(status_code=404, detail="Pas de couverture")
    return FileResponse(str(cover_path), media_type="image/jpeg")


@router.get("/tomes/{tome_id}/page/{page_index}")
async def opds_tome_page(tome_id: int, page_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    """Endpoint OPDS-PSE — équivalent de /api/reader/{id}/page/{n} (routers/reader.py, même
    services.page_extractor) mais sous l'authentification Basic dédiée à OPDS plutôt que le
    cookie de session."""
    tome = (await db.execute(select(Tome).where(Tome.id == tome_id))).scalar_one_or_none()
    if tome is None or tome.series_id in await get_user_excluded_series_ids(db, user):
        raise HTTPException(status_code=404, detail="Tome introuvable")

    try:
        img_bytes = await asyncio.to_thread(page_extractor.extract_page, tome.filepath, tome.file_format, page_index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur extraction: {str(e)}")

    content_type = "image/jpeg"
    if img_bytes[:4] == b"\x89PNG":
        content_type = "image/png"
    return Response(content=img_bytes, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


# ── Navigation par genre / année / auteur / éditeur ─────────────────────────────
# IMPORTANT : ces deux routes génériques à un et deux segments doivent rester enregistrées
# APRÈS toutes les routes plus spécifiques ci-dessus (/series, /series/{id}, /tomes/...) —
# Starlette matche les routes dans l'ordre d'enregistrement, pas par spécificité. Placées
# avant, "/opds/series" aurait été intercepté ici (facet="series", 404) au lieu d'atteindre
# opds_series_list plus haut.

@router.get("/{facet}")
async def opds_facet_values(facet: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    if facet not in _FACETS:
        raise HTTPException(status_code=404, detail="Introuvable")
    field, label = _FACETS[facet]
    excluded = await get_user_excluded_series_ids(db, user)
    q = select(getattr(Metadata, field)).join(Tome, Tome.id == Metadata.tome_id)
    if excluded:
        q = q.where(Tome.series_id.notin_(excluded))
    rows = (await db.execute(q)).scalars().all()

    values: set[str] = set()
    for raw in rows:
        if field == "Year":
            if raw and raw.strip():
                values.add(raw.strip())
        else:
            values.update(_split_multi(raw))

    def entries(root):
        for v in sorted(values, reverse=(facet == "years")):
            entry = _sub(root, "entry")
            _sub(entry, "id", f"urn:cbzmanager:{facet}:{v}")
            _sub(entry, "title", v)
            _sub(entry, "updated", _now_iso())
            _sub(entry, "link", rel="subsection", href=f"/opds/{facet}/{quote(v, safe='')}",
                 type="application/atom+xml;profile=opds-catalog;kind=acquisition")

    return _feed_response(f"urn:cbzmanager:{facet}", label, "navigation", f"/opds/{facet}", entries)


@router.get("/{facet}/{value}")
async def opds_facet_detail(facet: str, value: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    if facet not in _FACETS:
        raise HTTPException(status_code=404, detail="Introuvable")
    field, _label = _FACETS[facet]
    excluded = await get_user_excluded_series_ids(db, user)

    q = select(Tome, getattr(Metadata, field)).join(Metadata, Metadata.tome_id == Tome.id).where(getattr(Metadata, field).isnot(None))
    if excluded:
        q = q.where(Tome.series_id.notin_(excluded))
    rows = (await db.execute(q)).all()

    tomes: list[Tome] = []
    seen_ids: set[int] = set()
    for t, raw in rows:
        candidates = [raw.strip()] if field == "Year" else _split_multi(raw)
        if value in candidates and t.id not in seen_ids:
            seen_ids.add(t.id)
            tomes.append(t)
    tomes.sort(key=lambda t: (t.title or t.filename or "").lower())

    return _feed_response(
        f"urn:cbzmanager:{facet}:{value}", value, "acquisition", f"/opds/{facet}/{quote(value, safe='')}",
        lambda root: _tome_entries(root, tomes),
    )
