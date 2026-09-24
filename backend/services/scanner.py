import asyncio
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ..models.db_models import Series, Tome, Metadata, ScanJob
from ..database import AsyncSessionLocal
from ..config import settings
from .filename_parser import parse_filename
from .cover_cache import ensure_cover
from .archive_format import detect_archive_ext
from .archive_safety import read_entry_bounded

COMIC_EXTS = {".cbz", ".cbr", ".pdf", ".zip", ".rar"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _parse_comicinfo_xml(xml_bytes: bytes) -> dict:
    """Parse ComicInfo.xml and return a dict of fields."""
    try:
        root = ET.fromstring(xml_bytes)
        result = {}
        for child in root:
            if child.text and child.text.strip():
                result[child.tag] = child.text.strip()
        return result
    except Exception:
        return {}


def _read_comic_info(filepath: Path) -> tuple[int, dict]:
    """Read page count and ComicInfo.xml metadata from a comic file."""
    ext = detect_archive_ext(filepath)
    page_count = 0
    metadata = {}

    if ext in (".cbz", ".zip"):
        try:
            with zipfile.ZipFile(str(filepath), "r") as zf:
                names = zf.namelist()
                pages = [n for n in names if Path(n).suffix.lower() in IMAGE_EXTS and not n.startswith("__MACOSX")]
                page_count = len(pages)
                # Try to read ComicInfo.xml
                ci_names = [n for n in names if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    with zf.open(ci_names[0]) as entry:
                        metadata = _parse_comicinfo_xml(read_entry_bounded(entry))
        except Exception:
            pass

    elif ext in (".cbr", ".rar"):
        try:
            import rarfile
            with rarfile.RarFile(str(filepath), "r") as rf:
                names = rf.namelist()
                pages = [n for n in names if Path(n).suffix.lower() in IMAGE_EXTS]
                page_count = len(pages)
                ci_names = [n for n in names if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    with rf.open(ci_names[0]) as entry:
                        metadata = _parse_comicinfo_xml(read_entry_bounded(entry))
        except Exception:
            pass

    elif ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(filepath))
            page_count = doc.page_count
            doc.close()
        except Exception:
            pass

    return page_count, metadata


async def get_running_scan(db: AsyncSession) -> Optional[ScanJob]:
    result = await db.execute(
        select(ScanJob).where(ScanJob.status == "running").limit(1)
    )
    return result.scalar_one_or_none()


async def create_scan_job(db: AsyncSession) -> ScanJob:
    job = ScanJob(status="pending", started_at=datetime.utcnow())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def scan_library(
    library_path: str,
    db: AsyncSession,
    job_id: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """
    Walk library_path, group files by parent folder (= series name),
    upsert Series/Tome/Metadata rows, update scan job status.
    """
    lib = Path(library_path)

    # Mark job running
    await db.execute(
        update(ScanJob)
        .where(ScanJob.id == job_id)
        .values(status="running", started_at=datetime.utcnow())
    )
    await db.commit()

    try:
        # Un montage NAS pas encore prêt (ou temporairement décroché) présente typiquement le
        # dossier comme absent ou comme un dossier vide, pas comme une erreur — sans ce garde-
        # fou, la réconciliation plus bas (qui supprime tout tome non retrouvé) interpréterait
        # ça comme "l'utilisateur a vidé sa bibliothèque" et effacerait tout le catalogue.
        if not lib.exists() or not lib.is_dir():
            raise RuntimeError(
                f"Dossier de bibliothèque introuvable : {library_path} — scan interrompu, rien n'a été supprimé."
            )

        # Collect all comic files
        all_files: list[Path] = []
        for ext in COMIC_EXTS:
            all_files.extend(lib.rglob(f"*{ext}"))

        total = len(all_files)

        # Même garde-fou pour un dossier qui existe mais se présente vide (montage revenu
        # mais pas encore repeuplé, permissions provisoirement fermées, etc.) : ne réconcilier
        # les suppressions que si on a un minimum de matière, sinon marquer le scan en erreur
        # sans toucher aux tomes déjà connus. Une bibliothèque réellement vidée par
        # l'utilisateur doit passer par une action explicite (ex. réinitialisation), pas par
        # l'effet de bord d'un scan classique.
        existing_tome_count = len((await db.execute(select(Tome.id))).all())
        if total == 0 and existing_tome_count > 0:
            raise RuntimeError(
                f"Aucun fichier trouvé dans {library_path} alors que {existing_tome_count} "
                "album(s) sont déjà connus — scan interrompu par sécurité (montage absent ou "
                "vide ?), rien n'a été supprimé."
            )

        await db.execute(
            update(ScanJob).where(ScanJob.id == job_id).values(total=total)
        )
        await db.commit()

        # Remove tomes whose files no longer exist on disk OR are outside library_path
        all_paths = {str(f) for f in all_files}
        lib_prefix = str(lib.resolve())
        existing_tomes = (await db.execute(select(Tome))).scalars().all()
        for tome in existing_tomes:
            if tome.filepath not in all_paths or not tome.filepath.startswith(lib_prefix):
                await db.delete(tome)
        await db.commit()

        # Remove series whose folder is outside library_path OR have no remaining tomes
        all_series = (await db.execute(select(Series))).scalars().all()
        for series in all_series:
            outside = not series.folder_path.startswith(lib_prefix)
            count = (await db.execute(
                select(Tome).where(Tome.series_id == series.id)
            )).scalars().first()
            if outside or count is None:
                await db.delete(series)
        await db.commit()

        processed = 0
        # {folder_path: series_id} — avoids one SELECT-by-folder per file for series already
        # seen earlier in this scan (the vast majority once the library is indexed). Keyed by
        # folder path, not series name: two different folders can share a leaf name (e.g. a
        # "OnePiece" folder under both manga/ and bd/), and must stay distinct series.
        series_cache: dict[str, int] = {}
        # Covers are generated after the loop, concurrently — extracting/resizing images
        # is I/O-bound and doesn't need the per-file DB session, so serializing it inside
        # the scan loop only slowed the scan down for no benefit (covers.py already
        # generates them lazily on first request if the scan is skipped/interrupted).
        cover_jobs: list[tuple[int, str]] = []
        for filepath in sorted(all_files):
            # Use a fresh session per file to avoid session corruption on error
            async with AsyncSessionLocal() as file_db:
                try:
                    tome = await _process_file(filepath, lib, file_db, series_cache=series_cache)
                    await file_db.commit()
                    if tome is not None:
                        cover_jobs.append((tome.id, tome.filepath))
                except Exception as e:
                    import logging
                    logging.warning(f"FILE ERROR {filepath}: {e}")
                    await file_db.rollback()
                    # Marquer le tome en erreur s'il existe déjà en DB
                    try:
                        err_result = await file_db.execute(
                            select(Tome).where(Tome.filepath == str(filepath))
                        )
                        err_tome = err_result.scalar_one_or_none()
                        if err_tome:
                            err_tome.status = "error"
                            err_tome.error_msg = str(e)[:500]
                            await file_db.commit()
                    except Exception:
                        pass
            processed += 1
            if progress_cb:
                progress_cb(processed, total)

        # Generate covers for new/updated tomes, several at a time instead of one by one.
        await _generate_covers_bounded(cover_jobs)

        # Update tome_count for all series
        result = await db.execute(select(Series))
        for series in result.scalars().all():
            count_result = await db.execute(
                select(Tome).where(Tome.series_id == series.id)
            )
            count = len(count_result.scalars().all())
            series.tome_count = count
            series.updated_at = datetime.utcnow()

        await db.commit()

        # Cleanup orphan covers
        await _cleanup_orphan_covers(db)

        # Mark done
        await db.execute(
            update(ScanJob)
            .where(ScanJob.id == job_id)
            .values(status="done", processed=processed, total=total, finished_at=datetime.utcnow())
        )
        await db.commit()

    except Exception as e:
        await db.execute(
            update(ScanJob)
            .where(ScanJob.id == job_id)
            .values(status="error", error_msg=str(e), finished_at=datetime.utcnow())
        )
        await db.commit()
        raise


COVER_GEN_CONCURRENCY = 4


async def _generate_covers_bounded(cover_jobs: list[tuple[int, str]]) -> None:
    """Run ensure_cover() for a batch of tomes, several at a time."""
    if not cover_jobs:
        return
    sem = asyncio.Semaphore(COVER_GEN_CONCURRENCY)

    async def _one(tome_id: int, filepath: str) -> None:
        async with sem:
            try:
                await ensure_cover(tome_id, filepath)
            except Exception:
                pass

    await asyncio.gather(*(_one(tid, fp) for tid, fp in cover_jobs))


async def _cleanup_orphan_covers(db: AsyncSession) -> None:
    """Delete cover files whose tome_id no longer exists in DB."""
    cover_dir = Path(settings.COVER_CACHE_DIR)
    if not cover_dir.exists():
        return

    result = await db.execute(select(Tome.id))
    valid_ids = {row[0] for row in result.fetchall()}

    for cover_file in cover_dir.glob("*.jpg"):
        stem = cover_file.stem  # e.g. "42" or "42_thumb"
        try:
            tome_id = int(stem.split("_")[0])
        except ValueError:
            continue
        if tome_id not in valid_ids:
            cover_file.unlink()


async def _process_file(
    filepath: Path, lib: Path, db: AsyncSession, series_cache: dict[str, int] | None = None
) -> Optional[Tome]:
    """Upsert a single comic file into the DB.

    series_cache, when provided, maps folder_path -> series_id and is reused across
    calls within the same scan to skip the per-file SELECT-by-folder lookup for series
    already seen earlier in the scan. Each call still uses its own DB session (see
    scan_library), so only the plain id is cached — not the ORM object.
    """
    # .resolve() + is_relative_to() plutôt que relative_to(lib) seul : relative_to() est une
    # comparaison LEXICALE sur les segments du chemin, elle ne résout pas ".." — un appelant
    # passant un chemin non garanti par le scan lui-même (voir routers/import_router.py::
    # lookup_tomes, qui transmet un chemin fourni par le client) pouvait ainsi faire indexer
    # un fichier hors de la bibliothèque (ex. "/media/../autre/album.cbz"), dont le
    # tome.filepath résultant serait ensuite servi tel quel par les routes de lecture/
    # téléchargement. .resolve() normalise les ".." (et suit les liens symboliques, fermant
    # au passage le même risque pour un lien planté dans la bibliothèque et pointant dehors).
    filepath = filepath.resolve()
    lib = lib.resolve()
    if not filepath.is_relative_to(lib):
        raise ValueError(f"Chemin hors de la bibliothèque : {filepath}")
    rel = filepath.relative_to(lib)
    parts = rel.parts
    if len(parts) > 1:
        # Le dossier immédiat contenant le fichier définit la série, quelle que soit sa
        # profondeur — permet un dossier "catégorie" (ex: manga/OnePiece/T01.cbz) sans que
        # tout ce qui s'y trouve soit fusionné dans une seule série "manga".
        series_name = parts[-2]
        series_folder = filepath.parent
    else:
        # File is directly in the library root → use the library folder name as series
        series_name = lib.name
        series_folder = lib

    # Upsert series — identifié par son dossier physique (folder_path), pas par son seul nom :
    # deux dossiers différents peuvent porter le même nom de feuille (ex: "OnePiece" à la fois
    # sous manga/ et sous bd/), et doivent rester deux séries distinctes plutôt que de fusionner
    # silencieusement (un rename/delete ultérieur agirait alors sur le mauvais dossier).
    series_id = series_cache.get(str(series_folder)) if series_cache is not None else None
    if series_id is None:
        result = await db.execute(select(Series).where(Series.folder_path == str(series_folder)))
        series = result.scalar_one_or_none()
        if series is None:
            name_taken = (await db.execute(
                select(Series.id).where(Series.name == series_name)
            )).scalar_one_or_none()
            if name_taken is not None:
                # Series.name est unique en DB : un autre dossier physique utilise déjà ce nom
                # — désambiguïsé avec le dossier parent plutôt que de planter le scan.
                series_name = f"{series_folder.parent.name}/{series_name}"
            series = Series(name=series_name, folder_path=str(series_folder))
            db.add(series)
            await db.flush()
        series_id = series.id
        if series_cache is not None:
            series_cache[str(series_folder)] = series_id

    # Parse filename
    stem = filepath.stem
    parsed = parse_filename(stem)

    # Detect format — octets magiques plutôt que l'extension du chemin, voir
    # archive_format.py (un fichier en attente de conversion est déjà renommé en .cbz avant
    # que son contenu ne soit réellement réencodé).
    ext = detect_archive_ext(filepath)
    fmt_map = {".cbz": "cbz", ".zip": "cbz", ".cbr": "cbr", ".rar": "cbr", ".pdf": "pdf"}
    file_format = fmt_map.get(ext, "unknown")

    st = filepath.stat()
    file_size = st.st_size
    file_mtime = st.st_mtime

    # Check if tome already exists
    result = await db.execute(select(Tome).where(Tome.filepath == str(filepath)))
    tome = result.scalar_one_or_none()

    # Fichier déjà connu, taille et date de modification inchangées depuis le dernier
    # scan → on saute l'ouverture de l'archive (le plus coûteux). Les fichiers en erreur
    # sont réessayés à chaque fois (permissions/etc. peuvent avoir été corrigées entre
    # temps sans que mtime/size du fichier lui-même ne changent).
    unchanged = (
        tome is not None
        and tome.status != "error"
        and tome.file_size == file_size
        and tome.file_mtime == file_mtime
    )

    if tome is None:
        tome = Tome(
            series_id=series_id,
            filename=filepath.name,
            filepath=str(filepath),
            file_format=file_format,
            file_size=file_size,
            file_mtime=file_mtime,
            number=parsed.get("number"),
            title=parsed.get("title"),
        )
        db.add(tome)
        await db.flush()
    else:
        # Le fichier n'a pas bougé sur le disque mais peut avoir changé de série de
        # rattachement (ex. évolution de la logique de nommage, dossier renommé) — le
        # chemin seul ne le révèle pas puisqu'il est inchangé, il faut réaligner
        # series_id explicitement à chaque scan plutôt que seulement à la création.
        if tome.series_id != series_id:
            tome.series_id = series_id
        if not unchanged:
            tome.file_size = file_size
            tome.file_mtime = file_mtime
            tome.number = parsed.get("number")
            tome.title = parsed.get("title")
            tome.updated_at = datetime.utcnow()
            # Fichier remplacé (taille/date différentes) : un ancien hash de contenu ne
            # correspondrait plus à rien — remis à None, le prochain scan de doublons
            # (services/duplicates.py) le recalculera.
            tome.content_hash = None
        else:
            if tome.number is None and parsed.get("number") is not None:
                # Fichier inchangé sur le disque mais dont le numéro n'avait jamais pu être
                # extrait (convention de nommage non reconnue à l'époque du scan initial,
                # ex. "Tome 01" avant que le motif ne soit géré, ou fichier renommé hors de
                # l'app) — retente à chaque scan, opération quasi gratuite (regex seule, pas
                # de ré-ouverture de l'archive) et sans downside : ne fait jamais régresser un
                # numéro déjà correctement extrait. Le titre est réécrasé avec lui (pas
                # seulement rempli s'il était vide) : les deux proviennent du même nouveau
                # parsing, un ancien titre bancal (ex. numéro resté collé dedans faute de
                # motif reconnu à l'époque) ne doit pas rester figé indéfiniment.
                tome.number = parsed.get("number")
                tome.title = parsed.get("title")
                tome.updated_at = datetime.utcnow()
            elif tome.title is None and parsed.get("title") is not None:
                # Même rattrapage que ci-dessus mais indépendant du numéro : un one-shot n'a
                # justement pas de numéro (parsed["number"] reste toujours None pour lui), la
                # condition précédente ne se déclenche donc jamais pour ces fichiers-là. Sans
                # ce cas séparé, un titre resté à None (motif de nom de fichier corrigé après
                # coup, voir filename_parser.py) ne se rattraperait jamais.
                tome.title = parsed.get("title")
                tome.updated_at = datetime.utcnow()

            if not tome.has_metadata:
                # Idem pour has_metadata : certains flux d'écriture (complétion Bedetheque en
                # lot, édition en lot) ont pu remplir les métadonnées sans mettre ce flag à
                # jour (bug corrigé côté écriture, mais ne rattrape pas les albums déjà
                # concernés). Reconstruit depuis la table Metadata existante — pas de lecture
                # du fichier — sans jamais faire régresser un flag déjà à True.
                meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
                meta = meta_result.scalar_one_or_none()
                if meta and any(getattr(meta, f) for f in ("Title", "Series", "Number", "Writer", "Publisher")):
                    tome.has_metadata = True
                    tome.updated_at = datetime.utcnow()

            if tome.page_count:
                # Rattrapage du champ ComicInfo "Pages" pour les tomes déjà scannés avant
                # l'ajout de ce repli (voir plus bas, cas fichier changé) — sans réouvrir
                # l'archive, juste une lecture/écriture de la ligne Metadata.
                meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
                meta = meta_result.scalar_one_or_none()
                if meta is None:
                    meta = Metadata(tome_id=tome.id)
                    db.add(meta)
                if not meta.PageCount:
                    meta.PageCount = str(tome.page_count)

    if unchanged:
        return tome

    # Read comic metadata in thread pool (blocking I/O)
    try:
        page_count, metadata_dict = await asyncio.to_thread(_read_comic_info, filepath)
        tome.page_count = page_count
        tome.status = "ok"

        tome.has_metadata = bool(metadata_dict) and any(metadata_dict.get(f) for f in ("Title", "Series", "Number", "Writer", "Publisher"))

        # Repli ComicInfo.xml quand le nom de fichier n'a pas fourni de titre/numéro (ex :
        # "Série - T15.cbz" volontairement sans titre en doublon avec le numéro — voir
        # filename_parser.py) — sans ça, l'app retombait sur le nom de fichier complet
        # (extension incluse) pour l'affichage alors que le vrai titre était déjà connu dans
        # le fichier. Ne complète que le vide, ne remplace jamais un titre/numéro déjà déduit
        # du nom de fichier (même philosophie que le rattrapage plus haut pour un fichier
        # inchangé entre deux scans).
        if metadata_dict:
            if not tome.title and metadata_dict.get("Title"):
                tome.title = metadata_dict["Title"]
            if not tome.number and metadata_dict.get("Number"):
                tome.number = metadata_dict["Number"]

        # Le nombre de pages réellement compté dans l'archive sert de repli pour le champ
        # ComicInfo "Pages" du formulaire d'édition — sans ce repli, ce champ restait vide
        # tant que le fichier n'avait pas déjà son propre <PageCount> dans ComicInfo.xml
        # (jamais le cas pour un import fraîchement scrapé, Bedetheque ne fournissant pas
        # cette donnée). Toujours créer/mettre à jour la ligne Metadata, même sans
        # ComicInfo.xml du tout, pour que ce repli s'applique dans tous les cas.
        meta_result = await db.execute(select(Metadata).where(Metadata.tome_id == tome.id))
        meta = meta_result.scalar_one_or_none()
        if meta is None:
            meta = Metadata(tome_id=tome.id)
            db.add(meta)
        if metadata_dict:
            for field in Metadata.__table__.columns.keys():
                if field in ("id", "tome_id"):
                    continue
                val = metadata_dict.get(field)
                if val is not None and str(val).strip():
                    setattr(meta, field, str(val))
        if not meta.PageCount and page_count:
            meta.PageCount = str(page_count)

    except Exception as e:
        tome.status = "error"
        tome.error_msg = str(e)[:500]

    await db.flush()
    return tome
