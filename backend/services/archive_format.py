"""
Détection du format réel d'une archive par ses octets magiques plutôt que par son
extension de fichier.

Nécessaire car un fichier en attente de conversion est renommé en .cbz par l'assistant
d'import (frontend/src/views/ImportView.vue::applyPattern) *avant* que la conversion n'ait
réellement réencodé son contenu — le temps que la conversion tourne, l'extension ne reflète
donc pas encore le contenu réel sur disque. Si la conversion échoue (ex : CBR mal reconnu),
ce décalage devient permanent : ouvrir le fichier en se fiant à son extension (zipfile sur
des octets RAR) échoue silencieusement (page_count=0, aucune métadonnée lue), sans jamais
remonter d'erreur explicite.
"""
from pathlib import Path

_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_RAR_MAGIC = b"Rar!\x1a\x07"
_PDF_MAGIC = b"%PDF-"


def detect_archive_ext(path: Path | str) -> str:
    """Retourne '.cbz', '.cbr', '.pdf' selon les octets magiques du fichier, ou l'extension
    du chemin telle quelle si la lecture échoue ou que le contenu n'est reconnu comme aucun
    des trois (fichier corrompu, format non supporté) — dans ce dernier cas, laisser
    l'appelant échouer avec son message d'erreur habituel plutôt que d'en inventer un ici."""
    p = Path(path)
    try:
        with open(p, "rb") as f:
            head = f.read(8)
    except OSError:
        return p.suffix.lower()

    if head.startswith(_ZIP_MAGICS):
        return ".cbz"
    if head.startswith(_RAR_MAGIC):
        return ".cbr"
    if head.startswith(_PDF_MAGIC):
        return ".pdf"
    return p.suffix.lower()
