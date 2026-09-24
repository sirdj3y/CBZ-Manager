import asyncio
import io
import json
import shutil
import time
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import require_permission, get_current_user, _profile_permissions
from ..database import get_db
from ..models.db_models import Series, Tome, User
from ..config import settings
from ..services.filename_parser import parse_filename
from ..services import activity as activity_svc

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(require_permission("library.import"))])

ALLOWED_EXTS = {".cbz", ".cbr", ".pdf", ".zip", ".rar"}

# {filepath: (user_id, timestamp)} — fichiers effectivement créés par CE routeur (upload direct
# ou lookup-tomes après upload), pour borner ce que /cancel-cleanup a le droit de supprimer
# avec la seule permission library.import (voir cancel_cleanup ci-dessous). Sans ce suivi,
# cancel-cleanup ne pouvait distinguer "fichier que je viens d'importer" de "n'importe quel
# album déjà présent dont je devine le chemin" — un contributeur pouvait ainsi faire supprimer
# un album préexistant sans avoir library.delete. Volontairement en mémoire (pas en DB) :
# ne sert qu'à couvrir la fenêtre d'un import en cours, jamais consultée après coup.
_recent_imports: dict[str, tuple[int, float]] = {}
_RECENT_IMPORT_TTL = 2 * 3600  # largement plus qu'un import + conversion ne prend jamais


def _remember_import(filepath: str, user_id: int) -> None:
    now = time.time()
    _recent_imports[filepath] = (user_id, now)
    if len(_recent_imports) > 500:
        cutoff = now - _RECENT_IMPORT_TTL
        for k, (_, ts) in list(_recent_imports.items()):
            if ts < cutoff:
                _recent_imports.pop(k, None)


def _is_recent_import_owner(filepath: str, user_id: int) -> bool:
    entry = _recent_imports.get(filepath)
    if entry is None:
        return False
    owner_id, ts = entry
    if time.time() - ts > _RECENT_IMPORT_TTL:
        _recent_imports.pop(filepath, None)
        return False
    return owner_id == user_id


async def _can_delete_freely(db: AsyncSession, user: User) -> bool:
    """Un utilisateur avec library.delete peut déjà supprimer n'importe quel album via les
    routes de suppression normales — pas de raison de le restreindre davantage ici."""
    if user.is_admin:
        return True
    return "library.delete" in await _profile_permissions(db, user)


def _safe_filename(filename: str) -> str:
    """Reject path separators / traversal so a filename can't escape its destination folder."""
    name = filename.strip()
    if not name or any(c in name for c in ("/", "\\")) or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    return name


class ParseIn(BaseModel):
    filename: str

@router.post("/parse")
async def parse_file(body: ParseIn):
    """Parse un nom de fichier et retourne série, numéro, titre."""
    stem = body.filename.rsplit(".", 1)[0]
    return parse_filename(stem)


@router.post("/check")
async def check_file(
    filename: str = Form(...),
    series_id: int | None = Form(None),
    new_series_name: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vérifie si un fichier existe déjà dans la destination."""
    filename = _safe_filename(filename)
    dest_dir = await _resolve_dest(series_id, new_series_name, db, current_user)
    if dest_dir is None:
        return {"duplicate": False}
    return {"duplicate": (dest_dir / filename).exists()}


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    filename: str = Form(...),
    series_id: int | None = Form(None),
    new_series_name: str | None = Form(None),
    metadata: str | None = Form(None),
    is_oneshot: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copie un fichier vers la destination dans MEDIA_ROOT, puis écrit les métadonnées si CBZ."""
    filename = _safe_filename(filename)
    ext = Path(filename).suffix.lower()
    if not ext and file.filename:
        ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Format non supporté : {ext}")

    if not series_id and not new_series_name:
        raise HTTPException(status_code=400, detail="Destination manquante")

    dest_dir = await _resolve_dest(series_id, new_series_name, db, current_user)
    if dest_dir is None:
        raise HTTPException(status_code=400, detail="Destination invalide")

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Impossible de créer le dossier destination : {e}")

    dest_file = dest_dir / filename
    duplicate = dest_file.exists()
    if duplicate:
        # Un fichier EXISTANT à ce chemin ne doit jamais être tronqué silencieusement par un
        # simple upload, qu'il soit ou non déjà indexé en base — son absence de la table
        # Tome ne prouve pas qu'il s'agit d'un résidu sans valeur (ex. déposé manuellement,
        # ou orphelin d'un import interrompu avant l'insertion DB mais dont le contenu est
        # bon). Un vrai remplacement volontaire passe par les routes dédiées (convertir/
        # remplacer), jamais par l'import.
        raise HTTPException(status_code=409, detail=f"Un fichier existe déjà à cet emplacement : {filename}")

    try:
        with open(dest_file, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Impossible d'écrire le fichier : {e}")
    finally:
        await file.close()

    # Écrire les métadonnées dans le CBZ si fournies
    if metadata:
        try:
            meta_dict = {k: v for k, v in json.loads(metadata).items() if v}
            if meta_dict:
                if ext in (".cbz", ".zip"):
                    from ..services.metadata_writer import write_metadata
                    await write_metadata(str(dest_file), meta_dict)
                else:
                    # Pour CBR/PDF : sidecar .meta.json lu par le convertisseur après conversion
                    sidecar = dest_file.with_suffix(".meta.json")
                    sidecar.write_text(json.dumps(meta_dict, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass  # Ne pas bloquer l'import si l'écriture des métadonnées échoue

    # Enregistrer le fichier en DB immédiatement → évite un scan complet pour obtenir le tome_id
    tome_id = None
    try:
        from ..services.scanner import _process_file
        from ..config import settings
        lib = Path(settings.LIBRARY_PATH)
        tome = await _process_file(dest_file, lib, db)
        if tome:
            tome_id = tome.id
            _remember_import(str(dest_file), current_user.id)
            if is_oneshot:
                tome.is_oneshot = True
            # Réconcilie immédiatement la liste des albums manquants de cette série (numéro
            # nouvellement possédé) — sans ça, l'album importé apparaissait en double avec son
            # entrée "manquant" jusqu'au scan Bedetheque suivant, seul à reconstruire
            # entièrement cette liste (voir services/missing_albums.py::_scan_one_series).
            if series_id and tome.number:
                from ..models.db_models import MissingAlbum
                from ..services.missing_albums import _numeric
                n = _numeric(tome.number)
                if n is not None:
                    missing_rows = (await db.execute(
                        select(MissingAlbum).where(MissingAlbum.series_id == series_id)
                    )).scalars().all()
                    for m in missing_rows:
                        if _numeric(m.number) == n:
                            await db.delete(m)
    except Exception:
        pass  # Le scan final le récupèrera

    await activity_svc.log(db, "import", f"Importé : {filename}", "ok")
    await db.commit()

    return {"ok": True, "path": str(dest_file), "duplicate": duplicate, "tome_id": tome_id}


class LookupIn(BaseModel):
    filepaths: list[str]

@router.post("/lookup-tomes")
async def lookup_tomes(body: LookupIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retourne {filepath: tome_id} pour une liste de chemins absolus.
    Si un fichier n'est pas encore indexé (scan pas encore passé), on le scanne à la volée."""
    from ..config import settings

    # Comparer les chemins RÉSOLUS, pas les chaînes brutes reçues : un alias lexical vers un
    # fichier déjà indexé (ex. contenant "..", voir la résolution de _process_file) ne
    # produirait sinon aucune correspondance ici, tomberait dans "missing", puis
    # _process_file le résoudrait et retrouverait le tome existant — ce routeur attribuerait
    # alors à tort au demandeur la propriété d'import de ce fichier PRÉEXISTANT (potentiellement
    # d'une série masquée ou appartenant à quelqu'un d'autre), qu'il pourrait ensuite faire
    # supprimer via cancel-cleanup sans jamais l'avoir réellement importé.
    resolved_by_original: dict[str, str] = {}
    for p in body.filepaths:
        try:
            resolved_by_original[p] = str(Path(p).resolve())
        except Exception:
            resolved_by_original[p] = p

    result = await db.execute(select(Tome).where(Tome.filepath.in_(resolved_by_original.values())))
    by_resolved = {t.filepath: t.id for t in result.scalars().all()}
    found = {orig: by_resolved[resolved] for orig, resolved in resolved_by_original.items() if resolved in by_resolved}

    missing = [p for p in body.filepaths if p not in found]
    for path_str in missing:
        p = Path(resolved_by_original[path_str])
        if p.exists() and p.suffix.lower() in {".cbz", ".cbr", ".pdf", ".zip", ".rar"}:
            try:
                from ..services.scanner import _process_file
                lib = Path(settings.LIBRARY_PATH)
                tome = await _process_file(p, lib, db)
                await db.commit()
                if tome:
                    found[path_str] = tome.id
                    # `path_str` n'était pas dans `by_resolved` juste au-dessus : ce fichier
                    # n'était donc pas déjà indexé avant cet appel, l'attribution de propriété
                    # ne peut viser qu'un fichier réellement nouveau pour cette requête.
                    _remember_import(str(p), current_user.id)
            except Exception:
                pass

    return found


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# 500 Mo — largement suffisant pour un CBZ/CBR entier dont on veut juste mesurer la 1ère
# page ; sans plafond, `await file.read()` chargeait l'intégralité de n'importe quel upload
# en mémoire avant même de regarder son contenu.
MAX_IMAGE_SIZE_UPLOAD_BYTES = 500 * 1024 * 1024


async def _read_upload_bounded(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Fichier trop volumineux")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/image-size")
async def get_image_size(file: UploadFile = File(...)):
    """Retourne la résolution (width x height) de la 1ère image d'un CBZ/CBR/PDF."""
    def _extract_size(data: bytes, ext: str) -> dict:
        try:
            from PIL import Image
            from ..services.archive_safety import read_entry_bounded
            if ext in (".cbz", ".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    names = sorted([n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
                    if not names:
                        return {}
                    # Lu en flux (voir archive_safety) : la taille annoncée dans les
                    # métadonnées ZIP d'une entrée n'est pas fiable (zip bomb).
                    with zf.open(names[0]) as entry:
                        img_data = read_entry_bounded(entry)
                    img = Image.open(io.BytesIO(img_data))
                    return {"width": img.width, "height": img.height}
            elif ext in (".cbr", ".rar"):
                import rarfile
                with rarfile.RarFile(io.BytesIO(data)) as rf:
                    names = sorted([n for n in rf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
                    if not names:
                        return {}
                    with rf.open(names[0]) as entry:
                        img_data = read_entry_bounded(entry)
                    img = Image.open(io.BytesIO(img_data))
                    return {"width": img.width, "height": img.height}
        except Exception:
            pass
        return {}

    data = await _read_upload_bounded(file, MAX_IMAGE_SIZE_UPLOAD_BYTES)
    ext = Path(file.filename or "").suffix.lower()
    result = await asyncio.to_thread(_extract_size, data, ext)
    return result


class CancelCleanupIn(BaseModel):
    paths: list[str]
    is_new_series: bool = False
    new_series_name: str | None = None


@router.post("/cancel-cleanup")
async def cancel_cleanup(body: CancelCleanupIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Nettoie un import annulé. Pour chaque chemin uploadé : si le fichier a déjà été
    indexé (le cas normal, upload_file() insère le Tome dès la copie), supprime le tome
    au sens complet (fichier + cover + entrée DB + série si elle devient vide) via la même
    logique que "Supprimer l'album" — sinon, si l'insertion en DB avait échoué, se contente
    d'unlink() le fichier resté orphelin. Supprime aussi le sidecar .meta.json (CBR/PDF)
    jamais consommé si l'annulation est survenue avant la conversion.
    Si is_new_series=True et que le dossier est vide après nettoyage, le supprime aussi.

    Restreint aux fichiers que CET utilisateur vient lui-même de créer via ce routeur (voir
    _recent_imports) — sans ce contrôle, un compte n'ayant que library.import (pas
    library.delete) pouvait faire supprimer n'importe quel album préexistant en devinant son
    chemin, puisque ce routeur ne vérifiait auparavant que l'appartenance du chemin à la
    bibliothèque, jamais qui avait réellement créé le fichier."""
    import logging
    from ..services.tome_deletion import delete_tome_and_cleanup
    from ..services.hidden_series import get_user_excluded_series_ids
    logger = logging.getLogger(__name__)

    library_path = Path(settings.LIBRARY_PATH).resolve()
    can_delete_freely = await _can_delete_freely(db, current_user)
    excluded_series_ids = await get_user_excluded_series_ids(db, current_user)
    dirs_to_check = set()
    deleted_count = 0

    for path_str in body.paths:
        p = Path(path_str).resolve()
        if not p.is_relative_to(library_path):
            logger.warning(f"[cancel-cleanup] rejected out-of-library path {p}")
            continue
        if not can_delete_freely and not _is_recent_import_owner(str(p), current_user.id):
            logger.warning(f"[cancel-cleanup] rejected path not owned by user {current_user.id}: {p}")
            continue
        dirs_to_check.add(p.parent)

        result = await db.execute(select(Tome).where(Tome.filepath == str(p)))
        tome = result.scalar_one_or_none()
        if tome is not None:
            # Même garde que la suppression normale d'un album (delete_tome_file) : avoir
            # library.delete ne dispense pas de la visibilité, une série masquée/restreinte
            # reste hors de portée même pour un compte qui peut supprimer par ailleurs.
            if tome.series_id in excluded_series_ids:
                logger.warning(f"[cancel-cleanup] rejected path in excluded series for user {current_user.id}: {p}")
                continue
            await delete_tome_and_cleanup(db, tome)
            deleted_count += 1
        elif p.exists() and p.is_file():
            try:
                p.unlink()
                deleted_count += 1
            except OSError as e:
                logger.warning(f"[cancel-cleanup] unlink error {p}: {e}")

        try:
            p.with_suffix(".meta.json").unlink(missing_ok=True)
        except OSError:
            pass

    if body.is_new_series:
        for d in dirs_to_check:
            try:
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
            except OSError as e:
                logger.warning(f"[cancel-cleanup] rmdir error {d}: {e}")

    if deleted_count:
        await activity_svc.log(db, "import", f"Import annulé : {deleted_count} fichier(s) supprimé(s)", "ok")
        await db.commit()

    return {"deleted_count": deleted_count}


async def _resolve_dest(series_id: int | None, new_series_name: str | None, db: AsyncSession, current_user: User) -> Path | None:
    import logging
    from ..services.hidden_series import get_user_excluded_series_ids
    logger = logging.getLogger(__name__)

    if series_id is not None:
        result = await db.execute(select(Series).where(Series.id == series_id))
        series = result.scalar_one_or_none()
        if series:
            # Une série masquée/au-delà du public conseillé de l'utilisateur ne doit pas
            # pouvoir recevoir de nouveaux fichiers en sa présence — sans ce contrôle, un
            # contributeur pouvait importer dans une série qu'il ne peut même pas voir en
            # devinant seulement son id.
            if series.id in await get_user_excluded_series_ids(db, current_user):
                return None
            # Revalider le confinement à chaque utilisation plutôt que de faire confiance à
            # une valeur déjà en base : elle a pu être écrite avant un correctif de
            # confinement (voir scanner.py::_process_file), ou devenir hors-périmètre si
            # LIBRARY_SUBDIR change après coup. Rejeter plutôt qu'écrire hors de la
            # bibliothèque courante.
            folder = Path(series.folder_path).resolve()
            library_path = Path(settings.LIBRARY_PATH).resolve()
            if not folder.is_relative_to(library_path):
                logger.warning(f"[import] resolve_dest rejected out-of-library series_id={series_id} folder_path={series.folder_path!r}")
                return None
            logger.warning(f"[import] resolve_dest series_id={series_id} -> folder_path={series.folder_path!r}")
            return folder

    if new_series_name:
        name = new_series_name.strip()
        # A series is a single folder directly under the library root — no separators/traversal allowed
        if not name or any(c in name for c in ("/", "\\")) or name in (".", ".."):
            return None
        media_root = Path(settings.MEDIA_ROOT).resolve()
        library_path = media_root
        if settings.LIBRARY_SUBDIR:
            library_path = (media_root / settings.LIBRARY_SUBDIR.strip("/")).resolve()
        dest = (library_path / name).resolve()
        if not dest.is_relative_to(library_path):
            return None
        logger.warning(f"[import] resolve_dest new_series={new_series_name!r} MEDIA_ROOT={settings.MEDIA_ROOT!r} -> dest={dest!r}")
        return dest

    return None
