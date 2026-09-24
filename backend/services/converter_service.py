"""
Conversion job management.
Converts CBR/PDF to CBZ with image recompression.
"""
import asyncio
import ctypes
import uuid
import zipfile
import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models.db_models import ConvertJob, ConvertJobTome, Tome, User
from ..database import AsyncSessionLocal
from .archive_format import detect_archive_ext
from .archive_safety import check_entry_count, read_entry_bounded, BoundedTotalReader
from .file_locks import get_file_lock

# In-memory progress store: {job_id: {tome_id: {progress, total, status}}}
_progress: dict[int, dict] = {}
# Abort flags: {job_id: ctypes.c_bool}
_abort_flags: dict[int, ctypes.c_bool] = {}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

QUALITY_PRESETS = {
    "Light":    {"quality": 60, "max_width": 1200},
    "Medium":   {"quality": 75, "max_width": 1600},
    "HQ":       {"quality": 85, "max_width": 2048},
    "Original": {"quality": 95, "max_width": 9999},
}


def _extract_images(src: Path) -> list[tuple[str, bytes]]:
    """Extract (name, bytes) image pairs from CBR, CBZ or PDF."""
    # Octets magiques plutôt que l'extension — voir archive_format.py : un fichier en
    # attente de conversion est déjà renommé en .cbz avant que son contenu ne soit
    # réellement réencodé, sinon un vrai CBR mal reconnu échouait ici silencieusement.
    ext = detect_archive_ext(src)
    images = []

    # Budget mémoire (voir archive_safety) : la taille annoncée dans les métadonnées d'une
    # archive n'est pas fiable, une archive minuscule peut en déclarer une énorme (zip bomb).
    # Lues en flux et comptées entrée par entrée, plutôt que zf.read()/rf.read() direct qui
    # décompresserait aveuglément la taille annoncée en mémoire.
    budget = BoundedTotalReader()

    if ext in (".cbz", ".zip"):
        with zipfile.ZipFile(str(src), "r") as zf:
            names = sorted([
                n for n in zf.namelist()
                if Path(n).suffix.lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX")
            ])
            check_entry_count(len(names))
            for name in names:
                with zf.open(name) as entry:
                    data = read_entry_bounded(entry)
                budget.add(len(data))
                images.append((name, data))

    elif ext in (".cbr", ".rar"):
        import rarfile
        with rarfile.RarFile(str(src), "r") as rf:
            names = sorted([
                n for n in rf.namelist()
                if Path(n).suffix.lower() in IMAGE_EXTS
            ])
            check_entry_count(len(names))
            for name in names:
                with rf.open(name) as entry:
                    data = read_entry_bounded(entry)
                budget.add(len(data))
                images.append((name, data))

    elif ext == ".pdf":
        import fitz
        doc = fitz.open(str(src))
        for i in range(doc.page_count):
            page = doc[i]
            page_imgs = page.get_images(full=True)
            if len(page_imgs) == 1:
                # Page = 1 image embarquée → extraction native, aucune perte
                xref = page_imgs[0][0]
                info = doc.extract_image(xref)
                img_ext = info["ext"] if info["ext"] in ("jpeg", "jpg", "png") else "jpg"
                images.append((f"page_{i+1:04d}.{img_ext}", info["image"]))
            else:
                # Page composite ou sans image → rendu haute résolution en PNG (lossless)
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                images.append((f"page_{i+1:04d}.png", pix.tobytes("png")))
        doc.close()

    return images


class ConversionCancelled(Exception):
    """Levée par _convert_sync dès que abort_flag passe à True en cours de traitement —
    jamais un simple retour normal. Sans ce signal explicite, run_convert_job ne peut pas
    distinguer une annulation d'un succès et finit par marquer le tome "done", supprimer la
    source (si delete_source) et republier le chemin du tome vers une destination qui n'a
    jamais été créée."""
    pass


def _recompress_image(img_bytes: bytes, quality: int, max_width: int) -> bytes:
    """Recompress image bytes to JPEG with given quality and max width."""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    # Capturé avant convert() (qui renvoie une nouvelle Image sans l'attribut .format) — sert
    # à décider plus bas si on peut retomber sur les octets d'origine sans se retrouver avec
    # un contenu non-JPEG écrit sous une extension .jpg (voir appelant, out_name en .jpg fixe).
    src_format = (img.format or "").upper()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # Always resize if above max_width
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        # After resize, always save recompressed (smaller by definition)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        return out.getvalue()
    # No resize needed — recompress and return smallest
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    result = out.getvalue()
    if len(result) < len(img_bytes):
        return result
    # Ne retomber sur les octets d'origine que si la source était déjà un JPEG : l'appelant
    # écrit toujours sous une extension .jpg forcée, un contenu PNG/WebP/GIF d'origine sous
    # cette extension serait un fichier dont le contenu ne correspond plus à son extension.
    return img_bytes if src_format in ("JPEG", "JPG") else result


def _convert_sync(src: str, dest: str, preset: str, progress_cb: Callable, abort_flag) -> None:
    """Convert src file to CBZ at dest with given quality preset. Ne retourne normalement
    qu'en cas de succès complet : lève ConversionCancelled si abort_flag passe à True en
    cours de route, l'appelant (run_convert_job) ne doit jamais traiter cela comme un
    succès (voir ConversionCancelled)."""
    import logging, shutil
    src_path = Path(src)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Un fichier différent porte déjà ce nom (ex. Album.pdf converti alors qu'Album.cbz
    # existe déjà) — refuser plutôt que l'écraser silencieusement. La recompression en
    # place (src == dest) reste autorisée.
    if dest_path.exists() and dest_path != src_path:
        raise FileExistsError(f"Le fichier de destination existe déjà : {dest_path.name}")

    # Preset Original sur un CBZ source : aucune recompression, mais pas une copie brute non
    # plus — ne conserve que les entrées reconnues comme pages (mêmes filtres que le lecteur,
    # voir _extract_images), octets d'image inchangés. Sert aussi de routine de nettoyage
    # pour une archive contenant des fichiers/dossiers parasites (HTML, __MACOSX, etc.),
    # invisibles à la lecture mais qui gonflaient inutilement le fichier jusqu'ici.
    if preset == "Original" and detect_archive_ext(src_path) in (".cbz", ".zip"):
        images = _extract_images(src_path)
        existing_xml: bytes | None = None
        try:
            with zipfile.ZipFile(str(src_path), "r") as src_zf:
                ci_names = [n for n in src_zf.namelist() if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    with src_zf.open(ci_names[0]) as entry:
                        existing_xml = read_entry_bounded(entry)
        except Exception:
            pass

        # Nom temporaire unique (pas ".converting.cbz" fixe) : deux opérations concurrentes
        # ciblant la même destination (ex. deux jobs de conversion mal formés, ou une
        # conversion et une réécriture de métadonnées qui se chevauchent malgré le verrou —
        # voir run_convert_job) ne se marchent plus sur le même fichier temporaire.
        tmp_path = dest_path.with_name(f"{dest_path.stem}.{uuid.uuid4().hex[:8]}.converting.cbz")
        try:
            with zipfile.ZipFile(str(tmp_path), "w", zipfile.ZIP_STORED) as zout:
                total = len(images)
                for i, (name, img_bytes) in enumerate(images):
                    if abort_flag.value:
                        raise ConversionCancelled()
                    # Nom de sortie séquentiel unique (000001.ext, 000002.ext, ...) plutôt que
                    # le seul nom de fichier d'origine : deux dossiers sources différents (ex.
                    # chapter1/001.jpg et chapter2/001.jpg dans l'archive d'origine) peuvent
                    # partager le même nom une fois aplatis dans le CBZ de sortie, ce qui fait
                    # qu'un lecteur ouvrant par nom affiche deux fois la même page. L'extension
                    # d'origine est conservée : ce sont ici les octets bruts, non ré-encodés.
                    out_name = f"{i + 1:06d}{Path(name).suffix.lower()}"
                    zout.writestr(out_name, img_bytes)
                    progress_cb(i + 1, total)
                if existing_xml is not None:
                    zout.writestr("ComicInfo.xml", existing_xml)
            shutil.move(str(tmp_path), str(dest_path))
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return

    params = QUALITY_PRESETS.get(preset, QUALITY_PRESETS["Original"])
    quality = params["quality"]
    max_width = params["max_width"]

    images = _extract_images(src_path)
    total = len(images)

    # Conserver le ComicInfo.xml existant si la source est un CBZ
    existing_xml: bytes | None = None
    if detect_archive_ext(src_path) in (".cbz", ".zip"):
        try:
            with zipfile.ZipFile(str(src_path), "r") as src_zf:
                ci_names = [n for n in src_zf.namelist() if n.lower().endswith("comicinfo.xml")]
                if ci_names:
                    with src_zf.open(ci_names[0]) as entry:
                        existing_xml = read_entry_bounded(entry)
        except Exception:
            pass

    # Écriture vers un fichier temporaire pour éviter de corrompre la source
    # si src == dest (recompression en place) ou en cas d'erreur/scan concurrent.
    # Nom unique (voir la branche Original ci-dessus pour le détail du raisonnement).
    tmp_path = dest_path.with_name(f"{dest_path.stem}.{uuid.uuid4().hex[:8]}.converting.cbz")
    try:
        with zipfile.ZipFile(str(tmp_path), "w", zipfile.ZIP_STORED) as zout:
            for i, (name, img_bytes) in enumerate(images):
                if abort_flag.value:
                    raise ConversionCancelled()
                try:
                    recompressed = _recompress_image(img_bytes, quality, max_width)
                except Exception:
                    recompressed = img_bytes
                # Même correctif de nom séquentiel unique que la branche Original ci-dessus.
                out_name = f"{i + 1:06d}.jpg"
                zout.writestr(out_name, recompressed)
                progress_cb(i + 1, total)
            if existing_xml is not None:
                zout.writestr("ComicInfo.xml", existing_xml)
        shutil.move(str(tmp_path), str(dest_path))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def estimate_size(src: Path, preset: str) -> int:
    """Estimate output size based on empirical ratios per preset."""
    # Ratios empiriques basés sur extraction native (1 compression, résolution source)
    EMPIRICAL_RATIOS = {
        "Light":    0.22,  # 1200px, q60 → ~22% de l'original
        "Medium":   0.45,  # 1600px, q75 → ~45% de l'original
        "HQ":       0.70,  # 2048px, q85 → ~70% de l'original
        "Original": 0.95,  # résolution native, q95 → ~95% de l'original
    }
    try:
        original = src.stat().st_size
        if preset == "Original" and detect_archive_ext(src) in (".cbz", ".zip"):
            return original
        ratio = EMPIRICAL_RATIOS.get(preset, 1.0)
        return int(original * ratio)
    except Exception:
        return 0


async def create_convert_job(
    tome_ids: list[int],
    preset: str,
    dest_path: Optional[str],
    db: AsyncSession,
    delete_source: bool = False,
    user_id: Optional[int] = None,
) -> int:
    job = ConvertJob(preset=preset, dest_path=dest_path, delete_source=delete_source, total=len(tome_ids), user_id=user_id)
    db.add(job)
    await db.flush()

    for tome_id in tome_ids:
        db.add(ConvertJobTome(job_id=job.id, tome_id=tome_id))

    await db.commit()
    await db.refresh(job)

    _progress[job.id] = {}
    for tome_id in tome_ids:
        _progress[job.id][tome_id] = {"progress": 0, "total": 0, "status": "pending"}

    return job.id


async def run_convert_job(job_id: int, user_id: int | None = None, ip: str | None = None) -> None:
    """Background task: run all conversion jobs sequentially. user_id/ip transmis
    explicitement depuis start_convert (routers/converter.py) — tâche de fond définie dans
    un autre module, ne peut pas capturer current_user par fermeture lexicale comme les
    scans (voir routers/library.py::start_scan)."""
    import logging
    logging.warning(f"RUN_CONVERT_JOB start job_id={job_id}")
    abort_flag = ctypes.c_bool(False)
    _abort_flags[job_id] = abort_flag

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ConvertJob).where(ConvertJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logging.warning(f"RUN_CONVERT_JOB job not found job_id={job_id}")
            return

        tomes_result = await db.execute(
            select(ConvertJobTome).where(ConvertJobTome.job_id == job_id)
        )
        job_tomes = tomes_result.scalars().all()
        logging.warning(f"RUN_CONVERT_JOB job_id={job_id} preset={job.preset} tomes_count={len(job_tomes)}")

        await db.execute(
            update(ConvertJob).where(ConvertJob.id == job_id).values(status="running")
        )
        await db.commit()

        for jt in job_tomes:
            if abort_flag.value:
                break

            tome_result = await db.execute(select(Tome).where(Tome.id == jt.tome_id))
            tome = tome_result.scalar_one_or_none()
            if tome is None:
                continue

            _progress[job_id][jt.tome_id] = {"progress": 0, "total": 0, "status": "running"}

            src = Path(tome.filepath)
            if job.dest_path:
                dest = Path(job.dest_path) / (src.stem + ".cbz")
            else:
                dest = src.parent / (src.stem + ".cbz")

            def progress_cb(current: int, total: int):
                _progress[job_id][jt.tome_id] = {
                    "progress": current,
                    "total": total,
                    "status": "running",
                }

            try:
                # Verrouillé sur le chemin ACTUEL du tome (src) : une édition de métadonnées
                # sur le même album (voir metadata_writer.py::write_metadata, même registre
                # de verrous) ne doit jamais s'exécuter en même temps qu'une conversion,
                # sous peine de lire/écraser un état obsolète de l'un ou l'autre.
                async with get_file_lock(str(src)):
                    await asyncio.to_thread(
                        _convert_sync,
                        str(src), str(dest), job.preset, progress_cb, abort_flag
                    )
                _progress[job_id][jt.tome_id]["status"] = "done"
                jt.status = "done"
                jt.progress = _progress[job_id][jt.tome_id].get("total", 0)
                jt.total = jt.progress
                if job.delete_source and src != dest and src.exists():
                    src.unlink()

                # Faire pointer le tome existant vers le fichier converti au lieu de laisser
                # l'ancienne ligne orpheline (pointant vers un fichier supprimé si
                # delete_source) — sinon le scan suivant crée un second tome pour le CBZ,
                # avec perte de la progression de lecture / notes / notation attachées à
                # l'ancien tome_id.
                if src != dest:
                    tome.filepath = str(dest)
                    tome.filename = dest.name
                    tome.file_format = "cbz"
                    tome.status = "no_metadata"
                    tome.updated_at = datetime.utcnow()

                # Sidecar .meta.json : écrire les métadonnées dans le CBZ converti
                sidecar = src.with_suffix(".meta.json")
                if not sidecar.exists():
                    sidecar = dest.with_suffix(".meta.json")
                if sidecar.exists():
                    try:
                        import json as _json
                        meta_dict = _json.loads(sidecar.read_text(encoding="utf-8"))
                        if meta_dict and dest.exists():
                            # write_metadata (pas _write_sync direct) : passe par le même
                            # verrou par chemin que toute autre écriture de métadonnées (voir
                            # file_locks.py) et libère la boucle d'événements pendant la
                            # réécriture du zip au lieu de la bloquer en synchrone.
                            from .metadata_writer import write_metadata
                            await write_metadata(str(dest), meta_dict)
                    except Exception as _e:
                        logging.warning(f"SIDECAR META write error: {_e}")
                    finally:
                        try:
                            sidecar.unlink()
                        except Exception:
                            pass

            except ConversionCancelled:
                # Jamais traité comme un succès : pas de delete_source, pas de repointage du
                # tome vers `dest` (voir ConversionCancelled) — ce bloc s'arrête avant tout ça.
                # Statut "error" (pas un nouveau "cancelled") pour rester compatible avec les
                # consommateurs existants qui ne connaissent que pending/running/done/error
                # (ConversionProgress.vue, l'agrégation de convert_status/convert_stream) —
                # seule la CAUSE loggée diffère, le comportement de sécurité ci-dessus ne
                # dépend jamais de ce libellé.
                logging.warning(f"CONVERT CANCELLED tome={jt.tome_id}")
                _progress[job_id][jt.tome_id] = {"progress": 0, "total": 0, "status": "error", "error": "Conversion annulée"}
                jt.status = "error"
            except Exception as e:
                import logging
                logging.warning(f"CONVERT ERROR tome={jt.tome_id}: {e}")
                _progress[job_id][jt.tome_id] = {
                    "progress": 0, "total": 0,
                    "status": "error",
                    "error": str(e),
                }
                jt.status = "error"
                # Nettoyer le sidecar si la conversion a échoué
                for _sidecar in (src.with_suffix(".meta.json"), dest.with_suffix(".meta.json")):
                    if _sidecar.exists():
                        try:
                            _sidecar.unlink()
                        except Exception:
                            pass

            await db.commit()

        # "done" seulement si CHAQUE tome a réellement réussi — pas seulement "annulation non
        # demandée". Un job dont un ou plusieurs tomes sont en erreur (ou encore "pending" si
        # annulé avant d'être traités) ne doit jamais s'afficher comme un succès complet, y
        # compris après la purge de la progression en mémoire (voir convert_status, qui
        # retombe sur ce statut persisté une fois le cache en mémoire expiré).
        tome_statuses = [jt.status for jt in job_tomes]
        final_status = "done" if tome_statuses and all(s == "done" for s in tome_statuses) else "error"
        final_progress = sum(1 for s in tome_statuses if s == "done")
        await db.execute(
            update(ConvertJob)
            .where(ConvertJob.id == job_id)
            .values(status=final_status, progress=final_progress, total=len(tome_statuses), finished_at=datetime.utcnow())
        )
        await db.commit()

        from .activity import log as activity_log
        done_count = sum(1 for v in _progress.get(job_id, {}).values() if v.get("status") == "done")
        err_count  = sum(1 for v in _progress.get(job_id, {}).values() if v.get("status") == "error")
        msg = f"Conversion terminée — {done_count} fichier(s) convertis"
        if err_count: msg += f", {err_count} erreur(s)"
        convert_user = await db.get(User, user_id) if user_id is not None else None
        await activity_log(db, "convert", msg, status="ok" if final_status == "done" else "error", user=convert_user, ip=ip)
        await db.commit()

    _abort_flags.pop(job_id, None)

    async def _cleanup_progress():
        await asyncio.sleep(300)
        _progress.pop(job_id, None)

    asyncio.create_task(_cleanup_progress())


def abort_job(job_id: int) -> bool:
    flag = _abort_flags.get(job_id)
    if flag is not None:
        flag.value = True
        return True
    return False


def get_progress(job_id: int) -> dict:
    return _progress.get(job_id, {})
