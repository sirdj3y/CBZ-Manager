"""
Empaquetage à la volée de plusieurs fichiers en une seule archive zip, streamée au fur et
à mesure plutôt que construite entièrement en mémoire — les CBZ étant déjà compressés,
stockage sans recompression (ZIP_STORED), rapide et peu coûteux en CPU.
"""
import zipfile
from collections.abc import Iterator
from pathlib import Path

_FLUSH_THRESHOLD = 1024 * 1024  # 1 Mo — taille de buffer avant d'émettre un chunk


class _ChunkedWriter:
    """Cible d'écriture pour zipfile.ZipFile — accumule les octets écrits et les restitue
    par paquets, sans jamais garder toute l'archive en mémoire à la fois."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._offset = 0  # position absolue depuis le début — zipfile en a besoin pour son index

    def write(self, data: bytes) -> int:
        self._buffer += data
        self._offset += len(data)
        return len(data)

    def tell(self) -> int:
        return self._offset

    def flush(self) -> None:
        pass

    def should_flush(self) -> bool:
        return len(self._buffer) >= _FLUSH_THRESHOLD

    def pop(self) -> bytes:
        data = bytes(self._buffer)
        self._buffer.clear()
        return data


def stream_zip(entries: list[tuple[str, str]]) -> Iterator[bytes]:
    """entries : liste de (nom_dans_l_archive, chemin_disque). Un fichier illisible est
    simplement ignoré (pas d'échec de tout le téléchargement pour un seul fichier absent)."""
    writer = _ChunkedWriter()
    with zipfile.ZipFile(writer, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for arcname, filepath in entries:
            path = Path(filepath)
            if not path.is_file():
                continue
            try:
                with open(path, "rb") as src, zf.open(arcname, "w", force_zip64=True) as dest:
                    while chunk := src.read(1024 * 1024):
                        dest.write(chunk)
                        if writer.should_flush():
                            yield writer.pop()
            except OSError:
                continue
            if writer.should_flush():
                yield writer.pop()
    yield writer.pop()
