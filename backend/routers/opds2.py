"""
Catalogue OPDS 2.0 (JSON, application/opds+json) — en plus du catalogue OPDS 1.2 existant
(routers/opds.py, Atom/XML), pour les apps de lecture qui ne parlent que la 2.0. Les deux
versions cohabitent sous des préfixes séparés (/opds vs /opds2) plutôt qu'une négociation de
contenu sur les mêmes URLs — évite tout risque de régression sur le flux 1.2 déjà en
production, et les deux formats sont de toute façon structurellement incompatibles (Atom/XML
contre JSON), pas juste un numéro de version différent.

Réutilise require_opds_user (même authentification Basic dédiée) et les endpoints existants
de téléchargement/couverture (/opds/tomes/{id}/download, /opds/tomes/{id}/cover) — inutile de
les dupliquer, ce ne sont que des flux binaires génériques, indépendants du format du feed qui
y a mené.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from ..database import get_db
from ..models.db_models import Metadata, Series, Tome, User
from ..services.hidden_series import get_user_excluded_series_ids
from .library import _split_multi
from .opds import EXT_TO_MIME, _FACETS, require_opds_user

router = APIRouter(prefix="/opds2", tags=["opds2"])

OPDS2_TYPE = "application/opds+json"


def _feed2(data: dict) -> JSONResponse:
    return JSONResponse(content=data, media_type=OPDS2_TYPE)


def _self_start_links(self_href: str) -> list[dict]:
    return [
        {"rel": "self", "href": self_href, "type": OPDS2_TYPE},
        {"rel": "start", "href": "/opds2", "type": OPDS2_TYPE},
    ]


def _publication(t: Tome) -> dict:
    """Un tome, au format Publication de la Readium Web Publication Manifest (utilisée
    telle quelle par OPDS 2.0) — équivalent JSON de _tome_entries dans opds.py."""
    mime = EXT_TO_MIME.get(t.file_format, "application/octet-stream")
    return {
        "metadata": {"@type": "http://schema.org/Book", "title": t.title or t.filename},
        "links": [
            {"rel": "http://opds-spec.org/acquisition", "href": f"/opds/tomes/{t.id}/download", "type": mime},
        ],
        "images": [
            {"href": f"/opds/tomes/{t.id}/cover", "type": "image/jpeg"},
        ],
    }


@router.get("")
@router.get("/")
async def opds2_root(user: User = Depends(require_opds_user())):
    navigation = [{"href": "/opds2/series", "title": "Toutes les séries", "type": OPDS2_TYPE}]
    for facet, (_field, label) in _FACETS.items():
        navigation.append({"href": f"/opds2/{facet}", "title": label, "type": OPDS2_TYPE})

    return _feed2({
        "metadata": {"title": "CBZ Manager"},
        "links": _self_start_links("/opds2"),
        "navigation": navigation,
    })


@router.get("/series")
async def opds2_series_list(db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    excluded = await get_user_excluded_series_ids(db, user)
    series_rows = (await db.execute(select(Series).order_by(Series.name))).scalars().all()
    series_rows = [s for s in series_rows if s.id not in excluded]

    navigation = [
        {"href": f"/opds2/series/{s.id}", "title": s.name, "type": OPDS2_TYPE}
        for s in series_rows
    ]

    return _feed2({
        "metadata": {"title": "Toutes les séries"},
        "links": _self_start_links("/opds2/series"),
        "navigation": navigation,
    })


@router.get("/series/{series_id}")
async def opds2_series_detail(series_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
    if series_id in await get_user_excluded_series_ids(db, user):
        raise HTTPException(status_code=404, detail="Série introuvable")
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")

    tomes = (await db.execute(select(Tome).where(Tome.series_id == series_id).order_by(Tome.number))).scalars().all()

    return _feed2({
        "metadata": {"title": series.name},
        "links": _self_start_links(f"/opds2/series/{series_id}"),
        "publications": [_publication(t) for t in tomes],
    })


# ── Navigation par genre / année / auteur / éditeur ─────────────────────────────
# Même remarque que opds.py : ces deux routes génériques doivent rester enregistrées APRÈS
# /series et /series/{id} ci-dessus, sinon "/opds2/series" serait intercepté ici en premier
# (facet="series", 404) — Starlette matche dans l'ordre d'enregistrement, pas par spécificité.

@router.get("/{facet}")
async def opds2_facet_values(facet: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
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

    navigation = [
        {"href": f"/opds2/{facet}/{quote(v, safe='')}", "title": v, "type": OPDS2_TYPE}
        for v in sorted(values, reverse=(facet == "years"))
    ]

    return _feed2({
        "metadata": {"title": label},
        "links": _self_start_links(f"/opds2/{facet}"),
        "navigation": navigation,
    })


@router.get("/{facet}/{value}")
async def opds2_facet_detail(facet: str, value: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_opds_user())):
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

    return _feed2({
        "metadata": {"title": value},
        "links": _self_start_links(f"/opds2/{facet}/{quote(value, safe='')}"),
        "publications": [_publication(t) for t in tomes],
    })
