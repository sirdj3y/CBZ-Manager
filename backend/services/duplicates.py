"""
Détection de doublons par contenu — hash SHA-256 de chaque fichier, calculé à la demande
(scan dédié, jamais lors du scan normal de la bibliothèque : lire tout le contenu de chaque
fichier est bien plus coûteux en I/O que la lecture de ComicInfo.xml faite par le scan
habituel, ça ralentirait chaque scan de routine pour un besoin ponctuel).

Même squelette que services/missing_albums.py::scan_all — un seul point d'entrée
(scan_duplicates) appelé par le routeur avec un callback de progression, qui gère lui-même
la création du job/l'orchestration en tâche de fond.
"""
import asyncio
import hashlib
import zipfile
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import Tome, Series

_HASH_CHUNK_SIZE = 1024 * 1024  # 1 Mo — jamais tout le fichier en mémoire à la fois


def _hash_file_sync(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def _check_integrity_sync(filepath: str, file_format: str) -> str | None:
    """Ouvre réellement l'archive et vérifie les CRC de chaque entrée (zf.testzip()) —
    contrairement à un simple Path.exists(), qui ne vérifie que la traversée des dossiers
    parents, pas la validité du contenu. Retourne un message d'erreur si corrompu, None sinon.
    Volontairement ici (pas dans le scan normal ni GET /api/health-check) : lit tout le
    contenu compressé de chaque fichier, même coût que le hashing juste au-dessus — seulement
    à la demande, via "Lancer une analyse complète"."""
    try:
        if file_format == "cbz":
            with zipfile.ZipFile(filepath, "r") as zf:
                bad = zf.testzip()
                return f"Entrée corrompue dans l'archive : {bad}" if bad else None
        elif file_format == "cbr":
            import rarfile
            with rarfile.RarFile(filepath, "r") as rf:
                bad = rf.testrar()
                return f"Entrée corrompue dans l'archive : {bad}" if bad else None
        elif file_format == "pdf":
            import fitz
            doc = fitz.open(filepath)
            _ = doc.page_count
            doc.close()
            return None
    except Exception as e:
        return str(e)[:500]
    return None


async def scan_duplicates(db: AsyncSession, progress_cb: Callable[[int, int], None]) -> None:
    """Hache tous les tomes dont content_hash est encore NULL (jamais hachés, ou remis à
    None par le scanner suite à un remplacement de fichier — voir scanner.py::_process_file),
    et en profite pour vérifier l'intégrité réelle de l'archive au passage (même fichier, même
    coût d'I/O déjà engagé). Une exécution répétée est donc bon marché : seuls les fichiers
    nouveaux/modifiés depuis le dernier passage sont retraités."""
    result = await db.execute(select(Tome).where(Tome.content_hash.is_(None)))
    tomes = list(result.scalars().all())
    progress_cb(0, len(tomes))

    for i, tome in enumerate(tomes):
        try:
            if Path(tome.filepath).is_file():
                tome.content_hash = await asyncio.to_thread(_hash_file_sync, tome.filepath)
                error = await asyncio.to_thread(_check_integrity_sync, tome.filepath, tome.file_format)
                if error:
                    tome.status = "error"
                    tome.error_msg = error
                elif tome.status == "error":
                    tome.status = "ok"
                    tome.error_msg = None
        except Exception:
            pass  # fichier illisible/verrouillé — laissé à None, retenté au prochain scan
        await db.commit()
        progress_cb(i + 1, len(tomes))


async def get_duplicate_groups(db: AsyncSession) -> list[dict]:
    """Groupes de 2+ tomes partageant le même content_hash, triés par taille de fichier
    décroissante (les plus gros doublons — donc les plus rentables à nettoyer — en premier)."""
    from sqlalchemy import func

    hash_rows = (await db.execute(
        select(Tome.content_hash)
        .where(Tome.content_hash.isnot(None))
        .group_by(Tome.content_hash)
        .having(func.count() > 1)
    )).scalars().all()
    if not hash_rows:
        return []

    tomes_result = await db.execute(
        select(Tome, Series.name)
        .join(Series, Series.id == Tome.series_id)
        .where(Tome.content_hash.in_(hash_rows))
        .order_by(Tome.content_hash, Tome.filepath)
    )
    by_hash: dict[str, list[dict]] = {}
    for tome, series_name in tomes_result.all():
        by_hash.setdefault(tome.content_hash, []).append({
            "tome_id": tome.id,
            "filename": tome.filename,
            "filepath": tome.filepath,
            "file_size": tome.file_size,
            "series_id": tome.series_id,
            "series_name": series_name,
            "cover_url": f"/api/covers/{tome.id}",
        })

    groups = [
        {"content_hash": h, "file_size": items[0]["file_size"], "tomes": items}
        for h, items in by_hash.items()
    ]
    groups.sort(key=lambda g: g["file_size"] or 0, reverse=True)
    return groups
