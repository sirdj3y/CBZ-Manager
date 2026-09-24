"""
Verrous en mémoire par chemin de fichier — sérialise les mutations concurrentes du même
album (édition de métadonnées, conversion...) : sans ça, deux opérations sur le même tome
pouvaient s'entrelacer et se remplacer avec un état obsolète (voir metadata_writer.py,
converter_service.py). Un seul process uvicorn pour toute l'app (voir CLAUDE.md) : un
registre en mémoire de ce process suffit, pas besoin d'un verrou distribué type fichier .lock
ou Redis.
"""
import asyncio
import time
from pathlib import Path

_locks: dict[str, asyncio.Lock] = {}
_last_used: dict[str, float] = {}


def get_file_lock(filepath: str) -> asyncio.Lock:
    """Toujours la même instance de Lock pour un chemin donné (résolu, pour que deux
    représentations différentes du même fichier ne contournent pas le verrou)."""
    key = str(Path(filepath).resolve())
    _last_used[key] = time.monotonic()
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    # Purge opportuniste des verrous inactifs et non pris depuis longtemps — le dict ne
    # grossit pas indéfiniment sur la durée de vie du process pour une grosse bibliothèque.
    if len(_locks) > 500:
        cutoff = time.monotonic() - 3600
        for k in list(_locks.keys()):
            if k != key and not _locks[k].locked() and _last_used.get(k, 0) < cutoff:
                _locks.pop(k, None)
                _last_used.pop(k, None)
    return lock
