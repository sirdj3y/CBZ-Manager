import asyncio
import json
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import require_permission, get_current_user
from ..models.db_models import Series, Tome, ScanJob, Metadata, UserTomeData, User
from ..models.schemas import SeriesOut, SeriesDetailOut, TomeOut, ScanStartOut, ScanStatusOut, DeleteSeriesBulkIn
from ..services.scanner import create_scan_job, scan_library, get_running_scan
from ..services.hidden_series import get_user_hidden_series_ids, get_user_excluded_series_ids, get_user_age_restricted_series_ids, assert_series_visible
from ..services.classification import CLASSIFICATIONS
from ..services.age_rating import AGE_RATINGS
from .auth import get_client_ip
from ..config import settings

router = APIRouter(prefix="/api", tags=["library"], dependencies=[Depends(require_permission("library.read"))])

# In-memory scan progress store {job_id: {processed, total, status}}
_scan_progress: dict[int, dict] = {}


def _cover_url(tome_id: int, cached: bool, updated_at=None) -> str:
    if updated_at is not None:
        v = int(updated_at.timestamp()) if hasattr(updated_at, "timestamp") else str(updated_at).replace(" ", "")
        return f"/api/covers/{tome_id}?v={v}"
    return f"/api/covers/{tome_id}"


def _split_multi(value: str | None) -> list[str]:
    """Un album peut avoir plusieurs scénaristes/dessinateurs/éditeurs — convention
    multi-valeurs de l'app : séparés par une virgule dans un même champ ComicInfo.xml."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@router.get("/classifications")
async def list_classifications():
    return CLASSIFICATIONS


@router.get("/age-ratings")
async def list_age_ratings():
    return AGE_RATINGS


async def build_series_out_list(db: AsyncSession, series_list: list[Series], current_user: User) -> list[SeriesOut]:
    """Agrège métadonnées/couverture/tags pour une liste de Series déjà résolue (filtrage de
    visibilité à la charge de l'appelant) — factorisé pour être réutilisé tel quel par la
    variante 'par série' des smart lists (routers/smart_lists.py), qui doit produire
    exactement le même SeriesOut que la page Séries pour un sous-ensemble d'ids donné."""
    if not series_list:
        return []

    # Agrégation des métadonnées par série en une seule requête. Étiquettes utilisateur
    # jointes depuis UserTomeData scopées à l'utilisateur courant (données personnelles,
    # pas Tome.user_tag_list — colonne conservée en base mais plus lue nulle part).
    series_ids = [s.id for s in series_list]
    meta_rows = (await db.execute(
        select(Tome.series_id, Tome.has_metadata, Metadata.Writer, Metadata.Penciller, Metadata.Publisher, Metadata.Genre, UserTomeData.tag_list)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .outerjoin(UserTomeData, (UserTomeData.tome_id == Tome.id) & (UserTomeData.user_id == current_user.id))
        .where(Tome.series_id.in_(series_ids))
    )).all() if series_ids else []

    # Couverture par série (premier tome)
    cover_rows = (await db.execute(
        select(Tome.series_id, Tome.id, Tome.cover_cached, Tome.updated_at)
        .where(Tome.series_id.in_(series_ids))
        .order_by(Tome.series_id, Tome.number)
    )).all() if series_ids else []
    # Build default cover map (first tome per series)
    cover_map: dict[int, str] = {}
    for series_id, tid, cached, updated in cover_rows:
        if series_id not in cover_map:
            cover_map[series_id] = _cover_url(tid, cached, updated)
    # Override with custom cover_tome_id when set
    for s in series_list:
        if s.cover_tome_id:
            cover_map[s.id] = _cover_url(s.cover_tome_id, True)

    # Agrégation
    agg: dict[int, dict] = defaultdict(lambda: {
        "writers": set(), "pencillers": set(), "publishers": set(),
        "tags": set(), "genres": set(), "has_no_meta": False,
    })
    for series_id, has_meta, writer, penciller, publisher, genre, user_tag_list in meta_rows:
        a = agg[series_id]
        if not has_meta:
            a["has_no_meta"] = True
        a["writers"].update(_split_multi(writer))
        a["pencillers"].update(_split_multi(penciller))
        a["publishers"].update(_split_multi(publisher))
        a["genres"].update(_split_multi(genre))
        # Étiquettes de CET utilisateur (UserTomeData.tag_list, JSON) — pas Metadata.Tags
        # (champ ComicInfo.xml jamais exposé à l'édition dans l'app, donc toujours vide en
        # pratique). Donnée personnelle : les chips affichées sur la carte série reflètent
        # les tags que l'utilisateur connecté a lui-même posés, pas ceux des autres comptes.
        if user_tag_list:
            try:
                a["tags"].update(json.loads(user_tag_list))
            except Exception:
                pass

    out = []
    for s in series_list:
        a = agg[s.id]
        out.append(SeriesOut(
            id=s.id,
            name=s.name,
            tome_count=s.tome_count,
            cover_url=cover_map.get(s.id),
            hidden=s.hidden,
            created_at=s.created_at,
            updated_at=s.updated_at,
            classification=s.classification,
            writers=sorted(a["writers"]),
            pencillers=sorted(a["pencillers"]),
            publishers=sorted(a["publishers"]),
            tags=sorted(a["tags"]),
            genres=sorted(a["genres"]),
            has_tomes_without_meta=a["has_no_meta"],
            bedetheque_url=s.bedetheque_url,
            bedetheque_match_status=s.bedetheque_match_status,
            hero_logo_version=s.hero_logo_version,
            hero_background_version=s.hero_background_version,
        ))
    return out


@router.get("/series", response_model=list[SeriesOut])
async def list_series(show_hidden: bool = False, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = select(Series).order_by(Series.name)
    # show_hidden ne lève le masquage global que pour un admin — sinon un simple
    # ?show_hidden=true dans l'URL suffisait à un non-admin pour voir des séries masquées à
    # tout le monde, alors que la fiche détail d'une série masquée reste, elle, bloquée.
    if not show_hidden or not current_user.is_admin:
        q = q.where(Series.hidden == False)
    # Masquage personnel (UserHiddenSeries) — indépendant de show_hidden, qui ne contrôle
    # que le masquage global : une série masquée spécifiquement à cet utilisateur reste
    # invisible pour lui même si show_hidden=true. Le plafond de public conseillé
    # (age_rating_limit) s'applique de la même façon, y compris si show_hidden=true.
    if not current_user.is_admin:
        excluded_ids = await get_user_hidden_series_ids(db, current_user.id)
        excluded_ids |= await get_user_age_restricted_series_ids(db, current_user.age_rating_limit)
        if excluded_ids:
            q = q.where(Series.id.notin_(excluded_ids))
    result = await db.execute(q)
    series_list = result.scalars().all()
    return await build_series_out_list(db, series_list, current_user)


def _fold_name(s: str) -> str:
    """Clé de regroupement insensible à la casse/accents — "Le Lombard" et "Le lombard"
    doivent compter comme la même entrée, pas deux entrées séparées."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip().lower()


@router.get("/library/authors")
async def list_authors(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retourne writers/pencillers/publishers avec nb de tomes et séries, ainsi que les
    genres distincts de toute la bibliothèque et les étiquettes de l'utilisateur connecté
    (donnée personnelle) — pour l'autocomplétion des filtres, voir ContentToolbar.vue.

    Regroupement des auteurs/éditeurs par orthographe EXACTE — reflète fidèlement ce qu'il y
    a réellement dans les fichiers, y compris les doublons de casse/accents ("Le Lombard" /
    "Le lombard"). Voir /library/authors/duplicates pour la détection de ces doublons, et
    /library/authors/merge pour les réconcilier explicitement (avec confirmation)."""
    rows = (await db.execute(
        select(Metadata.Writer, Metadata.Penciller, Metadata.Publisher, Metadata.Genre, Tome.series_id, UserTomeData.tag_list)
        .join(Tome, Tome.id == Metadata.tome_id)
        .outerjoin(UserTomeData, (UserTomeData.tome_id == Tome.id) & (UserTomeData.user_id == current_user.id))
        .where(
            Metadata.Writer.isnot(None) | Metadata.Penciller.isnot(None) | Metadata.Publisher.isnot(None)
            | Metadata.Genre.isnot(None) | UserTomeData.tag_list.isnot(None)
        )
    )).all()

    authors:    dict[str, dict] = defaultdict(lambda: {"tomes": 0, "series": set()})
    publishers: dict[str, dict] = defaultdict(lambda: {"tomes": 0, "series": set()})
    genres_set: set[str] = set()
    tags_set: set[str] = set()

    def add(bucket: dict, raw: str, series_id: int):
        v = raw.strip()
        if not v:
            return
        bucket[v]["tomes"] += 1
        bucket[v]["series"].add(series_id)

    for writer, penciller, publisher, genre, series_id, user_tag_list in rows:
        for field in [writer, penciller]:
            if field:
                for v in field.split(","):
                    add(authors, v, series_id)
        if publisher:
            for v in publisher.split(","):
                add(publishers, v, series_id)
        genres_set.update(_split_multi(genre))
        if user_tag_list:
            try:
                tags_set.update(json.loads(user_tag_list))
            except (json.JSONDecodeError, TypeError):
                pass

    def fmt(d: dict) -> list:
        return sorted([
            {"name": k, "tomes": v["tomes"], "series": len(v["series"])}
            for k, v in d.items()
        ], key=lambda x: x["name"].lower())

    return {
        "authors":    fmt(authors),
        "publishers": fmt(publishers),
        "genres":     sorted(genres_set),
        "tags":       sorted(tags_set),
    }


def _find_duplicate_groups(counts: dict[str, int]) -> list[dict]:
    """Détecte les groupes de noms probablement identiques, à 3 niveaux de fiabilité :
      1 = casse/accents différents uniquement (quasi certain)
      2 = mêmes mots, ordre différent (assez fiable, ex. "Franquin André" / "André Franquin")
      3 = tous les mots de l'un forment un sous-ensemble des mots de l'autre (moins fiable,
          ex. "Bamboo" / "Bamboo Éditions" — comparaison mot à mot, jamais sur des fragments
          à l'intérieur d'un mot : "Sti" ne doit pas matcher "Christian" sous prétexte que la
          chaîne "sti" y apparaît)
    Ne fusionne jamais rien lui-même — sert uniquement à suggérer à l'utilisateur."""
    keys = list(counts.keys())
    n = len(keys)
    folded = [_fold_name(k) for k in keys]
    wordsets = [set(f.split()) for f in folded]

    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    edge_tier: dict[tuple[int, int], int] = {}
    for i in range(n):
        for j in range(i + 1, n):
            fi, fj = folded[i], folded[j]
            if fi == fj:
                tier = 1
            elif len(wordsets[i]) > 1 and wordsets[i] == wordsets[j]:
                tier = 2
            elif fi != fj and wordsets[i] and wordsets[j] and (wordsets[i] <= wordsets[j] or wordsets[j] <= wordsets[i]):
                # Sous-ensemble mot-à-mot uniquement (ex. "Bamboo" ⊆ {"Bamboo","Éditions"}) —
                # jamais sur un fragment interne à un mot ("Sti" ne doit pas matcher "Christian").
                contained = wordsets[i] if wordsets[i] <= wordsets[j] else wordsets[j]
                if min(len(w) for w in contained) < 3:
                    continue
                tier = 3
            else:
                continue
            union(i, j)
            edge_tier[(i, j)] = tier

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    groups = []
    for idxs in clusters.values():
        if len(idxs) < 2:
            continue
        idx_set = set(idxs)
        tiers = [t for (a, b), t in edge_tier.items() if a in idx_set and b in idx_set]
        variants = sorted(
            [{"name": keys[i], "tomes": counts[keys[i]]} for i in idxs],
            key=lambda v: -v["tomes"]
        )
        groups.append({"tier": max(tiers), "variants": variants})

    groups.sort(key=lambda g: (g["tier"], -sum(v["tomes"] for v in g["variants"])))
    return groups


@router.get("/library/authors/duplicates")
async def list_author_duplicates(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Metadata.Writer, Metadata.Penciller, Metadata.Publisher)
        .join(Tome, Tome.id == Metadata.tome_id)
        .where(Metadata.Writer.isnot(None) | Metadata.Penciller.isnot(None) | Metadata.Publisher.isnot(None))
    )).all()

    author_counts: dict[str, int] = defaultdict(int)
    publisher_counts: dict[str, int] = defaultdict(int)
    for writer, penciller, publisher in rows:
        for field in [writer, penciller]:
            if field:
                for v in field.split(","):
                    v = v.strip()
                    if v: author_counts[v] += 1
        if publisher:
            for v in publisher.split(","):
                v = v.strip()
                if v: publisher_counts[v] += 1

    return {
        "authors":    _find_duplicate_groups(author_counts),
        "publishers": _find_duplicate_groups(publisher_counts),
    }


class MergeAuthorsIn(BaseModel):
    kind: str  # "author" (Writer+Penciller) | "publisher"
    sources: list[str]
    target: str


@router.post("/library/authors/merge", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def merge_authors(body: MergeAuthorsIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.metadata_writer import write_metadata

    target = body.target.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Nom cible manquant")
    if body.kind not in ("author", "publisher"):
        raise HTTPException(status_code=400, detail="kind invalide")

    sources_folded = {_fold_name(s) for s in body.sources}
    fields_to_check = ["Writer", "Penciller"] if body.kind == "author" else ["Publisher"]

    def merge_field(raw: str | None) -> tuple[str | None, bool]:
        if not raw:
            return raw, False
        changed = False
        seen = set()
        new_parts = []
        for p in [p.strip() for p in raw.split(",")]:
            if not p:
                continue
            if _fold_name(p) in sources_folded:
                p = target
                changed = True
            key = _fold_name(p)
            if key in seen:
                continue
            seen.add(key)
            new_parts.append(p)
        return (", ".join(new_parts) if new_parts else None), changed

    q = (
        select(Tome, Metadata)
        .join(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.file_format == "cbz")
    )
    # Sans ce filtre, un compte avec library.metadata_edit mais sans accès à une série
    # masquée/restreinte pouvait quand même en modifier les métadonnées (et le fichier CBZ
    # sur disque) via cette fusion globale, qui ne recevait pourtant aucun id explicite de
    # série de sa part — seulement des noms d'auteur/éditeur, sans lien direct avec la
    # visibilité des tomes qu'elle finit par toucher.
    excluded_ids = await get_user_excluded_series_ids(db, current_user)
    if excluded_ids:
        q = q.where(Tome.series_id.notin_(excluded_ids))
    result = await db.execute(q)
    rows = result.all()

    to_update = []
    for tome, meta in rows:
        updates = {}
        for f in fields_to_check:
            new_val, changed = merge_field(getattr(meta, f))
            if changed:
                updates[f] = new_val
        if updates:
            to_update.append((tome, meta, updates))

    write_semaphore = asyncio.Semaphore(4)

    async def _write_one(tome: Tome, meta: Metadata, updates: dict):
        # Repartir de TOUS les champs actuels du tome (pas seulement ceux modifiés) pour ne
        # pas effacer le reste du ComicInfo.xml lors de la réécriture.
        full_fields = {
            k: getattr(meta, k) for k in Metadata.__table__.columns.keys()
            if k not in ("id", "tome_id")
        }
        full_fields.update(updates)
        async with write_semaphore:
            try:
                await write_metadata(tome.filepath, full_fields)
                return (tome, meta, updates, True)
            except Exception:
                return (tome, meta, updates, False)

    write_results = await asyncio.gather(*[_write_one(t, m, u) for t, m, u in to_update])

    errors = 0
    merged = 0
    for tome, meta, updates, ok in write_results:
        if not ok:
            errors += 1
            continue
        for k, v in updates.items():
            setattr(meta, k, v)
        tome.updated_at = datetime.utcnow()
        merged += 1

    await db.commit()

    from ..services.activity import log as activity_log
    msg = f"Fusion « {', '.join(body.sources)} » → « {target} » ({merged} album(s))"
    if errors:
        msg += f", {errors} erreur(s)"
    await activity_log(db, "edit_metadata", msg, status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"merged": merged, "errors": errors}


@router.patch("/series/{series_id}/hidden", response_model=SeriesOut, dependencies=[Depends(require_permission("library.delete"))])
async def toggle_series_hidden(series_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])
    series.hidden = not series.hidden
    await db.commit()
    await db.refresh(series)
    from ..services.activity import log as activity_log
    action = "Série masquée" if series.hidden else "Série affichée"
    await activity_log(db, "edit_metadata", f"{action} : « {series.name} »", user=current_user, ip=get_client_ip(request))
    await db.commit()
    # Get cover url
    first_tome = await db.execute(
        select(Tome).where(Tome.series_id == series.id).order_by(Tome.number).limit(1)
    )
    ft = first_tome.scalar_one_or_none()
    return SeriesOut(
        id=series.id,
        name=series.name,
        tome_count=series.tome_count,
        cover_url=_cover_url(ft.id, ft.cover_cached, ft.updated_at) if ft else None,
        hidden=series.hidden,
        updated_at=series.updated_at,
    )


class SetCoverIn(BaseModel):
    tome_id: int | None = None  # None = reset to first tome


@router.patch("/series/{series_id}/cover", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def set_series_cover(series_id: int, body: SetCoverIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    if body.tome_id is not None:
        # Validate that the tome belongs to this series
        tome_res = await db.execute(select(Tome).where(Tome.id == body.tome_id, Tome.series_id == series_id))
        if tome_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Tome introuvable dans cette série")

    series.cover_tome_id = body.tome_id
    await db.commit()
    from ..services.activity import log as activity_log
    cover_msg = f"Cover personnalisée : tome #{body.tome_id}" if body.tome_id else "Cover réinitialisée (auto)"
    await activity_log(db, "edit_metadata", f"Série « {series.name} » — {cover_msg}", user=current_user, ip=get_client_ip(request))
    await db.commit()

    # Return the new cover url
    if body.tome_id is not None:
        cover_url = _cover_url(body.tome_id, True)
    else:
        first = (await db.execute(
            select(Tome).where(Tome.series_id == series_id).order_by(Tome.number).limit(1)
        )).scalar_one_or_none()
        cover_url = _cover_url(first.id, first.cover_cached, first.updated_at) if first else None

    return {"cover_url": cover_url, "cover_tome_id": body.tome_id}


@router.get("/series/{series_id}", response_model=SeriesDetailOut)
async def get_series(series_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Series).where(Series.id == series_id)
    )
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    excluded = await get_user_excluded_series_ids(db, current_user)
    if series_id in excluded:
        raise HTTPException(status_code=404, detail="Série introuvable")

    tomes_result = await db.execute(
        select(Tome)
        .where(Tome.series_id == series_id)
        .order_by(Tome.number)
    )
    tomes = tomes_result.scalars().all()

    # Auteurs/éditeurs distincts sur TOUS les tomes de la série — jusqu'ici seul le premier
    # tome était consulté (page série + popup d'édition), laissant le champ vide dès qu'il
    # n'était pas renseigné sur ce tome précis, même si d'autres tomes l'avaient.
    meta_rows = (await db.execute(
        select(Metadata.Writer, Metadata.Penciller, Metadata.Publisher, Metadata.Genre, Metadata.CommunityRating, Metadata.Year)
        .join(Tome, Tome.id == Metadata.tome_id)
        .where(Tome.series_id == series_id)
    )).all()
    writers_set: set[str] = set()
    pencillers_set: set[str] = set()
    publishers_set: set[str] = set()
    genres_set: set[str] = set()
    # Pas de note "série" sur Bedetheque.com (contrairement à l'album) — moyenne des notes
    # des tomes qui en ont une, plutôt qu'un champ dédié à maintenir à jour.
    ratings: list[float] = []
    # Idem pour les années : pas de champ "année de la série" dédié, min/max des années des
    # tomes qui en ont une (Metadata.Year, texte libre ComicInfo.xml — filtré aux valeurs
    # plausibles comme stats.py::by_year).
    years: list[int] = []
    for writer, penciller, publisher, genre, community_rating, year in meta_rows:
        if community_rating:
            try:
                ratings.append(float(community_rating))
            except ValueError:
                pass
        if year and year.isdigit() and 1900 <= int(year) <= 2100:
            years.append(int(year))
        writers_set.update(_split_multi(writer))
        pencillers_set.update(_split_multi(penciller))
        publishers_set.update(_split_multi(publisher))
        genres_set.update(_split_multi(genre))

    # Use custom cover tome if set, otherwise first tome
    cover_tome = None
    if series.cover_tome_id:
        cover_tome = next((t for t in tomes if t.id == series.cover_tome_id), None)
    if cover_tome is None:
        cover_tome = tomes[0] if tomes else None
    cover_url = _cover_url(cover_tome.id, cover_tome.cover_cached, cover_tome.updated_at) if cover_tome else None

    tomes_out = [
        TomeOut(
            id=t.id,
            series_id=t.series_id,
            filename=t.filename,
            number=t.number,
            title=t.title,
            file_format=t.file_format,
            file_size=t.file_size,
            page_count=t.page_count,
            has_metadata=t.has_metadata,
            cover_cached=t.cover_cached,
            cover_url=_cover_url(t.id, t.cover_cached, t.updated_at),
            status=t.status,
            is_oneshot=t.is_oneshot,
            classification=series.classification,
        )
        for t in tomes
    ]

    return SeriesDetailOut(
        id=series.id,
        name=series.name,
        tome_count=series.tome_count,
        cover_url=cover_url,
        cover_tome_id=series.cover_tome_id,
        hidden=series.hidden,
        bedetheque_url=series.bedetheque_url,
        bedetheque_match_status=series.bedetheque_match_status,
        bedetheque_status=series.bedetheque_status,
        bedetheque_resume=series.bedetheque_resume,
        classification=series.classification,
        age_rating=series.age_rating,
        hero_background_version=series.hero_background_version,
        hero_logo_version=series.hero_logo_version,
        hero_character_version=series.hero_character_version,
        community_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
        year_start=min(years) if years else None,
        year_end=max(years) if years else None,
        writers=sorted(writers_set),
        pencillers=sorted(pencillers_set),
        publishers=sorted(publishers_set),
        genres=sorted(genres_set),
        tomes=tomes_out,
    )


@router.put("/series/{series_id}/metadata", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def update_series_metadata(series_id: int, body: dict, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..models.db_models import Metadata
    from ..services.metadata_writer import write_metadata
    from ..services.activity import log as activity_log

    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    # Champ propre à l'app (pas du ComicInfo.xml, jamais écrit dans les fichiers) — sorti de
    # body avant la boucle de réécriture des CBZ plus bas, qui traite tout le reste du body
    # comme des champs ComicInfo à propager sur chaque tome de la série.
    if "classification" in body:
        classification = (body.pop("classification") or "").strip() or None
        if classification is not None and classification not in CLASSIFICATIONS:
            raise HTTPException(status_code=400, detail="Classification invalide")
        series.classification = classification

    if "age_rating" in body:
        age_rating = (body.pop("age_rating") or "").strip() or None
        if age_rating is not None and age_rating not in AGE_RATINGS:
            raise HTTPException(status_code=400, detail="Public invalide")
        series.age_rating = age_rating

    # Résumé — même principe que classification/age_rating : colonne dédiée (pas de champ
    # ComicInfo.xml équivalent au niveau série), normalement rempli par le scraper Bedetheque
    # mais désormais aussi saisissable à la main pour les séries qu'il ne trouve pas.
    if "bedetheque_resume" in body:
        series.bedetheque_resume = (body.pop("bedetheque_resume") or "").strip() or None

    # Rien d'autre à faire : évite de réécrire le ComicInfo.xml de CHAQUE tome de la série
    # (coûteux en I/O, plusieurs secondes sur une grosse série) juste pour un changement de
    # classification, qui n'a rien à voir avec le ComicInfo.xml.
    if not body:
        await db.commit()
        return {"ok": 1, "errors": 0}

    tomes_result = await db.execute(select(Tome).where(Tome.series_id == series_id))
    tomes = tomes_result.scalars().all()

    # Renommer le dossier si le nom de la série change — sinon le prochain scan (qui déduit
    # le nom de série du nom du dossier) ne retrouve plus la série renommée et en recrée une
    # nouvelle sous l'ancien nom, dupliquant les albums.
    new_name = (body.get("Series") or "").strip()
    if new_name and new_name != series.name:
        # Caractères réservés Windows/SMB (":" notamment) : un rename() les acceptant sans
        # erreur ne garantit pas le nom obtenu sur disque — certains partages réseau/systèmes
        # de fichiers compatibles Windows y substituent silencieusement un nom court à la
        # DOS 8.3 (ex. "Code : Breaker" → "CRUHFO~C"), désynchronisant folder_path en base
        # du nom réel sur le disque. Bloqué en amont plutôt que de risquer cet état incohérent.
        bad_chars = sorted(set(new_name) & set('/\\:*?"<>|'))
        if bad_chars or new_name in (".", ".."):
            detail = (
                f"Nom de série invalide : le caractère « {bad_chars[0]} » n'est pas autorisé "
                "(peut être mal supporté par certains systèmes de fichiers/partages réseau)."
                if bad_chars else "Nom de série invalide"
            )
            raise HTTPException(status_code=400, detail=detail)
        old_folder = Path(series.folder_path)
        new_folder = old_folder.parent / new_name
        if new_folder.exists():
            raise HTTPException(status_code=409, detail=f"Un dossier « {new_name} » existe déjà")
        try:
            old_folder.rename(new_folder)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Impossible de renommer le dossier : {e}")
        for tome in tomes:
            tome.filepath = str(new_folder / Path(tome.filepath).name)
        series.folder_path = str(new_folder)

    cbz_tomes = [t for t in tomes if t.file_format == "cbz"]

    # Charger les métadonnées déjà présentes sur chaque tome — body ne contient que les
    # champs édités dans cette modale (Série/Éditeur/Scénariste/Dessinateur) ; réécrire le
    # CBZ avec seulement ceux-là effacerait Résumé/Genre/ISBN/etc. déjà renseignés.
    meta_rows = await db.execute(
        select(Metadata).where(Metadata.tome_id.in_([t.id for t in cbz_tomes]))
    )
    existing_meta: dict[int, Metadata] = {m.tome_id: m for m in meta_rows.scalars().all()}

    # La réécriture de chaque CBZ (I/O + compression) est ce qui prend du temps sur une
    # grosse série — parallélisée (bornée) car indépendante par fichier. Les écritures en
    # base restent séquentielles ensuite : une AsyncSession ne supporte pas les accès
    # concurrents depuis plusieurs coroutines.
    write_semaphore = asyncio.Semaphore(4)

    async def _write_one(tome: Tome) -> tuple[Tome, bool]:
        meta = existing_meta.get(tome.id)
        full_fields = {
            k: getattr(meta, k) for k in Metadata.__table__.columns.keys()
            if k not in ("id", "tome_id")
        } if meta else {}
        full_fields.update(body)
        async with write_semaphore:
            try:
                await write_metadata(tome.filepath, full_fields)
                return (tome, True)
            except Exception:
                return (tome, False)

    write_results = await asyncio.gather(*[_write_one(t) for t in cbz_tomes])

    errors = 0
    for tome, ok in write_results:
        if not ok:
            errors += 1
            continue
        meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
        meta = meta_result.scalar_one_or_none()
        if meta is None:
            meta = Metadata(tome_id=tome.id)
            db.add(meta)
        for key, val in body.items():
            if hasattr(meta, key):
                setattr(meta, key, val)
        tome.has_metadata = True
        tome.updated_at = datetime.utcnow()

    if "Series" in body and body["Series"]:
        series.name = body["Series"]

    await db.commit()

    cbz_count = len(cbz_tomes)
    msg = f"Métadonnées éditées : série « {series.name} » ({cbz_count} album(s))"
    if errors:
        msg += f", {errors} erreur(s)"
    await activity_log(db, "edit_metadata", msg, status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"ok": cbz_count - errors, "errors": errors}


_ENRICH_FIELDS = ("Title", "Writer", "Penciller", "Publisher", "Year", "ISBN", "Web")
_ENRICH_FIELD_LABELS = {
    "Title": "Titre", "Writer": "Scénariste", "Penciller": "Dessinateur", "Publisher": "Éditeur",
    "Year": "Année", "ISBN": "ISBN", "Web": "Fiche Bedetheque",
}


async def _fetch_series_html(bedetheque_url: str) -> str:
    """Une seule requête pour toute la série — la page liste déjà auteurs/éditeur/année
    pour chaque album (possédé ou non), pas besoin de visiter chaque fiche individuelle."""
    import httpx
    from ..services import scraper_bedetheque as bd

    async with httpx.AsyncClient(headers=bd.HEADERS, timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(bd._series_all_url(bedetheque_url))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Impossible de charger la page Bedetheque")
    return resp.text


async def _compute_enrich_items(series: Series, db: AsyncSession) -> list[dict]:
    if not series.bedetheque_url:
        raise HTTPException(status_code=400, detail="Aucune URL Bedetheque définie pour cette série")
    if series.bedetheque_match_status != "found":
        raise HTTPException(
            status_code=400,
            detail="Cette URL Bedetheque n'a pas pu être chargée avec succès — vérifie/corrige-la sur la fiche série avant de compléter.",
        )

    # Statut/genre/résumé/note communautaire — même fonction partagée que le scan "Albums
    # manquants" (services/missing_albums.py), pour que "Compléter les métadonnées" tienne
    # ces infos à jour aussi, pas seulement le scan complet de la bibliothèque.
    from ..services.missing_albums import sync_series_from_html

    html = await _fetch_series_html(series.bedetheque_url)
    albums = await sync_series_from_html(db, series, html)
    by_number = {a["number"]: a for a in albums if a.get("number")}

    tomes_result = await db.execute(
        select(Tome, Metadata)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.series_id == series.id, Tome.file_format == "cbz")
    )
    items = []
    for tome, meta in tomes_result.all():
        album = by_number.get(tome.number)
        if not album:
            continue

        fields = {}
        current_all = {}
        remote = {"Title": album.get("title"), "Writer": album.get("writer"), "Penciller": album.get("penciller"),
                  "Publisher": album.get("publisher"), "Year": album.get("year"),
                  "ISBN": album.get("isbn"), "Web": album.get("url")}
        for key in _ENRICH_FIELDS:
            # Titre : source Tome.title (affiché partout dans l'app), pas Metadata.Title
            # (simple passthrough ComicInfo.xml, jamais montré ailleurs) — les deux sont
            # réécrits ensemble à l'application pour rester cohérents entre eux.
            if key == "Title":
                current = (tome.title or "").strip()
            else:
                current = (getattr(meta, key, None) or "").strip() if meta else ""
            current_all[key] = current or None
            new_val = (remote.get(key) or "").strip()
            # Renvoyé dès que Bedetheque a une valeur, même si le champ est déjà rempli —
            # sinon impossible de proposer une correction pour un champ non-vide (le
            # suggestion-hint de la popup n'a alors jamais de valeur à afficher).
            if new_val:
                fields[key] = new_val
        # Inclut aussi les albums déjà à jour (fields vide) — sinon impossible de distinguer
        # "rien à compléter ici" de "cet album n'a pas été trouvé sur Bedetheque".
        items.append({
            "tome_id": tome.id, "number": tome.number, "title": tome.title,
            "filename": tome.filename, "fields": fields, "current": current_all,
        })
    items.sort(key=lambda it: (it["number"] or "").zfill(10))
    await db.commit()
    return items


@router.get("/series/{series_id}/enrich-preview", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def preview_series_enrich(series_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Aperçu, sans rien écrire : pour chaque album possédé retrouvé sur Bedetheque, les 4
    champs suivis sont TOUJOURS renvoyés (pas seulement ceux à compléter) — sinon impossible
    de voir pourquoi un champ donné n'est pas proposé (déjà rempli vs absent sur Bedetheque).
    "scraped" n'est présent que pour un champ réellement ajoutable (vide localement + connu
    sur Bedetheque) ; c'est aussi la liste qui sera effectivement cochable/appliquée."""
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])
    items = await _compute_enrich_items(series, db)
    files = [
        {
            "id": it["tome_id"],
            "name": it["filename"],
            "title": it["title"],
            "number": it["number"],
            "fields": [
                {
                    "field": key,
                    "field_label": _ENRICH_FIELD_LABELS[key],
                    "current": it["current"].get(key),
                    "scraped": it["fields"].get(key),
                }
                for key in _ENRICH_FIELDS
            ],
        }
        for it in items
    ]
    return {"files": files}


class EnrichUpdateIn(BaseModel):
    tome_id: int
    field: str
    value: str


class EnrichApplyIn(BaseModel):
    updates: list[EnrichUpdateIn]


@router.post("/series/{series_id}/enrich-apply", dependencies=[Depends(require_permission("library.metadata_edit"))])
async def apply_series_enrich(series_id: int, body: EnrichApplyIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Applique les valeurs envoyées par le client — aussi bien un champ vide complété
    depuis Bedetheque qu'un champ déjà renseigné corrigé manuellement (l'utilisateur peut
    éditer n'importe quelle cellule dans la popup, pas seulement les vides). Fusion complète
    des métadonnées existantes : jamais d'autre champ écrasé."""
    from ..services.metadata_writer import write_metadata
    from ..services.activity import log as activity_log

    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    tome_ids = {u.tome_id for u in body.updates}
    tomes_result = await db.execute(
        select(Tome).where(Tome.id.in_(tome_ids), Tome.series_id == series_id, Tome.file_format == "cbz")
    )
    tomes_by_id = {t.id: t for t in tomes_result.scalars().all()}

    wanted: dict[int, dict] = {}
    for u in body.updates:
        val = u.value.strip()
        if u.tome_id not in tomes_by_id or u.field not in _ENRICH_FIELDS or not val:
            continue  # tome hors série, champ non suivi, ou vidé par l'utilisateur — ignoré
        wanted.setdefault(u.tome_id, {})[u.field] = val

    if not wanted:
        return {"ok": 0, "errors": 0}

    # Pré-chargées avant le gather : une AsyncSession ne supporte pas plusieurs requêtes
    # concurrentes depuis des coroutines différentes (contrairement à write_metadata, qui ne
    # touche que le fichier et peut tourner en parallèle sans problème).
    meta_rows = await db.execute(select(Metadata).where(Metadata.tome_id.in_(wanted.keys())))
    meta_by_tome_id = {m.tome_id: m for m in meta_rows.scalars().all()}

    write_semaphore = asyncio.Semaphore(4)

    async def _write_one(tome_id: int, fields: dict) -> tuple[int, bool]:
        tome = tomes_by_id.get(tome_id)
        if tome is None:
            return (tome_id, False)
        meta = meta_by_tome_id.get(tome_id)
        full_fields = {
            k: getattr(meta, k) for k in Metadata.__table__.columns.keys()
            if k not in ("id", "tome_id")
        } if meta else {}
        full_fields.update(fields)
        async with write_semaphore:
            try:
                await write_metadata(tome.filepath, full_fields)
                return (tome_id, True)
            except Exception:
                return (tome_id, False)

    results = await asyncio.gather(*[_write_one(tid, f) for tid, f in wanted.items()])

    errors = 0
    ok = 0
    for tome_id, success in results:
        if not success:
            errors += 1
            continue
        tome = tomes_by_id[tome_id]
        meta = meta_by_tome_id.get(tome_id)
        if meta is None:
            meta = Metadata(tome_id=tome.id)
            db.add(meta)
            meta_by_tome_id[tome_id] = meta
        for key, val in wanted[tome_id].items():
            setattr(meta, key, val)
            if key == "Title":
                tome.title = val
        tome.has_metadata = True
        tome.updated_at = datetime.utcnow()
        ok += 1

    await activity_log(db, "edit_metadata", f"Métadonnées complétées depuis Bedetheque : série « {series.name} » ({ok} album(s))", status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()
    return {"ok": ok, "errors": errors}


async def _delete_series_folder_safely(db: AsyncSession, series: Series, exclude_ids: set[int] = frozenset()) -> None:
    """Supprime le dossier d'une série sans jamais toucher aux fichiers d'une AUTRE série dont
    le dossier vit à l'intérieur. Le scanner crée une série par dossier contenant directement
    des albums (voir scanner.py) — une arborescence imbriquée (Parent/album.cbz et
    Parent/Enfant/album.cbz) donne donc DEUX séries distinctes, l'une dans le dossier de
    l'autre. Un rmtree naïf du parent détruirait aussi les fichiers de l'enfant même si cette
    seconde série n'a pas été sélectionnée pour suppression (ou est masquée pour l'utilisateur
    courant). `exclude_ids` doit contenir les ids de TOUTES les séries traitées dans la même
    opération (suppression en lot) : elles seront nettoyées par leur propre passage, pas
    protégées ici comme si elles devaient survivre.
    """
    import logging, os, shutil
    try:
        folder = Path(series.folder_path).resolve()
        library_root = Path(settings.LIBRARY_PATH).resolve()
        if not folder.exists() or folder == library_root:
            return

        others = (await db.execute(
            select(Series.id, Series.folder_path).where(Series.id != series.id)
        )).all()
        nested_folders = []
        for other_id, other_path in others:
            if other_id in exclude_ids:
                continue
            try:
                other_folder = Path(other_path).resolve()
            except Exception:
                continue
            if other_folder == folder or other_folder.is_relative_to(folder):
                nested_folders.append(other_folder)

        if not nested_folders:
            # Cas normal (grande majorité des séries) : aucune série imbriquée, on retrouve le
            # comportement d'origine — wipe complet plutôt qu'une liste de motifs de fichiers
            # parasites à maintenir (HTML d'import, __MACOSX, etc.).
            shutil.rmtree(folder, ignore_errors=True)
            return

        # Une série imbriquée non supprimée vit ici : on supprime tout ce qui appartient à
        # CETTE série (fichiers hors de tout dossier de série imbriquée), puis on ne retire
        # que les dossiers redevenus vides — jamais de rmtree sur `folder` dans ce cas, le
        # dossier de la série imbriquée (non vide) fera systématiquement échouer son propre
        # rmdir() et restera intact, avec tout son contenu.
        for dirpath, _dirnames, filenames in os.walk(folder, topdown=False):
            dirpath_p = Path(dirpath)
            if any(dirpath_p == nf or dirpath_p.is_relative_to(nf) for nf in nested_folders):
                continue
            for fname in filenames:
                fpath = dirpath_p / fname
                if any(fpath == nf or fpath.is_relative_to(nf) for nf in nested_folders):
                    continue
                try:
                    fpath.unlink()
                except OSError:
                    pass
            try:
                dirpath_p.rmdir()
            except OSError:
                pass  # non vide : sous-dossier d'une série imbriquée protégée, ou déjà géré
    except Exception as e:
        logging.warning(f"Could not delete folder {series.folder_path}: {e}")


@router.delete("/series/{series_id}", status_code=200, dependencies=[Depends(require_permission("library.delete"))])
async def delete_series(series_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Supprime la série : tous les fichiers sur disque, le dossier si vide, et les entrées DB."""
    import logging
    result = await db.execute(select(Series).where(Series.id == series_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    await assert_series_visible(db, current_user, [series_id])

    # Récupérer tous les tomes pour supprimer les fichiers et covers
    tomes = (await db.execute(select(Tome).where(Tome.series_id == series_id))).scalars().all()
    cover_dir = Path(settings.COVER_CACHE_DIR)

    for tome in tomes:
        # Fichier du tome
        try:
            Path(tome.filepath).unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"Could not delete file {tome.filepath}: {e}")
        # Cache cover
        for f in [cover_dir / f"{tome.id}.jpg", cover_dir / f"{tome.id}_thumb.jpg"]:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    # Garde-fou déjà présent : un fichier posé directement à la racine de la bibliothèque
    # (sans sous-dossier dédié) fait du dossier racine lui-même le "folder_path" de sa série
    # (voir scanner.py) — jamais de rmtree dans ce cas précis, ce serait toute la bibliothèque
    # (vérifié dans _delete_series_folder_safely). Protège aussi le dossier d'une éventuelle
    # série imbriquée (voir _delete_series_folder_safely).
    await _delete_series_folder_safely(db, series, exclude_ids={series_id})

    # Supprimer la série (cascade supprime les tomes et leurs métadonnées)
    series_name = series.name
    await db.delete(series)
    await db.commit()
    from ..services.activity import log as activity_log
    await activity_log(db, "delete_series", f"Série supprimée : « {series_name} » ({len(tomes)} album(s))", user=current_user, ip=get_client_ip(request))
    await db.commit()
    return {"deleted": True}


@router.post("/series/delete-bulk", status_code=200, dependencies=[Depends(require_permission("library.delete"))])
async def delete_series_bulk(body: DeleteSeriesBulkIn, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Supprime plusieurs séries (mêmes règles que delete_series, une par une)."""
    import logging
    from ..services.activity import log as activity_log

    await assert_series_visible(db, current_user, body.series_ids)
    cover_dir = Path(settings.COVER_CACHE_DIR)
    # Tout le lot est exclu de la protection "série imbriquée" de _delete_series_folder_safely :
    # ces séries sont de toute façon toutes nettoyées ici, pas besoin de protéger le dossier
    # de l'une pendant qu'on traite une autre du même lot.
    batch_ids = set(body.series_ids)
    ok = 0
    errors: list[str] = []

    for series_id in body.series_ids:
        series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if series is None:
            errors.append(f"id={series_id} : introuvable")
            continue

        tomes = (await db.execute(select(Tome).where(Tome.series_id == series_id))).scalars().all()
        for tome in tomes:
            try:
                Path(tome.filepath).unlink(missing_ok=True)
            except Exception as e:
                logging.warning(f"Could not delete file {tome.filepath}: {e}")
            for f in [cover_dir / f"{tome.id}.jpg", cover_dir / f"{tome.id}_thumb.jpg"]:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

        await _delete_series_folder_safely(db, series, exclude_ids=batch_ids)

        await db.delete(series)
        ok += 1

    await db.commit()
    await activity_log(db, "delete_series", f"{ok} série(s) supprimée(s) en lot", status="ok" if not errors else "error", user=current_user, ip=get_client_ip(request))
    await db.commit()
    return {"ok": ok, "errors": errors}


@router.get("/scan/last")
async def last_scan(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanJob).order_by(ScanJob.id.desc()).limit(1))
    job = result.scalar_one_or_none()
    if job is None:
        return {"status": "never", "finished_at": None, "processed": 0, "total": 0}
    return {
        "status": job.status,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "processed": job.processed,
        "total": job.total,
        "error_msg": job.error_msg,
    }


@router.post("/scan", response_model=ScanStartOut, dependencies=[Depends(require_permission("library.scan"))])
async def start_scan(background_tasks: BackgroundTasks, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Return existing running job if any
    running = await get_running_scan(db)
    if running:
        return ScanStartOut(job_id=running.id)

    job = await create_scan_job(db)
    _scan_progress[job.id] = {"processed": 0, "total": 0, "status": "pending"}
    # Capturés avant la tâche de fond plutôt que de garder request/current_user en vie
    # au-delà de la requête HTTP — la closure n'a besoin que de ces deux valeurs simples.
    scan_user_id, scan_ip = current_user.id, get_client_ip(request)

    def progress_cb(processed: int, total: int):
        _scan_progress[job.id] = {"processed": processed, "total": total, "status": "running"}

    async def run_scan():
        import logging
        from ..database import AsyncSessionLocal
        from ..services.activity import log as activity_log
        from ..models.db_models import User as _User
        async with AsyncSessionLocal() as scan_db:
            scan_user = await scan_db.get(_User, scan_user_id)
            try:
                await scan_library(settings.LIBRARY_PATH, scan_db, job.id, progress_cb)
                _scan_progress[job.id]["status"] = "done"
                p = _scan_progress[job.id]
                await activity_log(scan_db, "scan", f"Scan terminé — {p.get('processed', 0)} fichiers traités", user=scan_user, ip=scan_ip)
            except Exception as e:
                _scan_progress[job.id]["status"] = "error"
                await activity_log(scan_db, "scan", f"Scan échoué : {e}", status="error", user=scan_user, ip=scan_ip)
            await scan_db.commit()

    background_tasks.add_task(run_scan)
    return ScanStartOut(job_id=job.id)


@router.get("/scan/{job_id}", response_model=ScanStatusOut)
async def scan_status(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanJob).where(ScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return ScanStatusOut(
        job_id=job.id,
        status=job.status,
        processed=job.processed,
        total=job.total,
        error_msg=job.error_msg,
    )


@router.get("/scan/{job_id}/stream")
async def scan_stream(job_id: int):
    async def event_gen():
        while True:
            data = _scan_progress.get(job_id)
            if data is None:
                # Entrée mémoire absente (ex: conteneur redémarré pendant le scan, ou client
                # connecté après coup) — sans ce repli, la boucle envoyait "unknown" indéfini-
                # ment, un statut jamais égal à "done"/"error" : la barre de progression ne
                # s'affichait jamais et la date de dernier scan n'était jamais rafraîchie côté
                # client, même quand le scan s'était en réalité bien terminé. Repli sur le
                # statut persisté en base, comme le fait déjà l'équivalent scan Bedetheque
                # (services/missing_albums.py).
                from ..database import AsyncSessionLocal
                async with AsyncSessionLocal() as fallback_db:
                    result = await fallback_db.execute(select(ScanJob).where(ScanJob.id == job_id))
                    job = result.scalar_one_or_none()
                data = (
                    {"processed": job.processed, "total": job.total, "status": job.status}
                    if job is not None else {"processed": 0, "total": 0, "status": "error"}
                )
            yield f"data: {json.dumps(data)}\n\n"
            if data["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
