"""
Garde-fous mémoire pour la lecture d'entrées d'archive (CBZ/CBR).

Sans ça, la taille DÉCLARÉE d'une entrée (ZipInfo.file_size / RarInfo.file_size, lue depuis
les métadonnées de l'archive) est prise pour argent comptant par zf.read()/rf.read() : une
archive de quelques Ko peut annoncer une entrée de plusieurs Go et faire décompresser cette
quantité en mémoire d'un coup (zip bomb classique — voir
https://docs.python.org/3/library/zipfile.html#decompression-pitfalls). Lire en flux et
compter les octets RÉELLEMENT produits, plutôt que de faire confiance à cette taille annoncée,
protège aussi bien contre une archive malveillante que contre une archive simplement corrompue
avec une taille aberrante en en-tête.
"""

MAX_ENTRY_BYTES = 80 * 1024 * 1024                 # 80 Mo — largement au-dessus d'une page scannée HQ
# 800 Mo cumulés — la cible de déploiement documentée (Synology DS423+, voir CLAUDE.md) tourne
# couramment avec 2 Go de RAM ; un plafond à plusieurs Go pour une SEULE opération de
# conversion laisserait trop peu de marge au reste de l'app en cas d'album volumineux ou de
# conversions simultanées. 800 Mo reste largement au-dessus d'un album réel une fois décompressé.
MAX_ARCHIVE_TOTAL_BYTES = 800 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 3000                         # aucun album réel n'approche ce nombre de pages
_CHUNK_SIZE = 1024 * 1024


class ArchiveTooLarge(Exception):
    """Levée quand une archive dépasse un des budgets ci-dessus — à ne jamais rattraper comme
    une erreur de lecture ordinaire par les `except Exception: pass` existants autour des
    lectures d'archive, sous peine de dégrader silencieusement une tentative de zip bomb en
    simple "page vide"/"métadonnées absentes" au lieu de la rejeter franchement."""
    pass


def check_entry_count(count: int) -> None:
    if count > MAX_ARCHIVE_ENTRIES:
        raise ArchiveTooLarge(f"Archive avec trop d'entrées ({count} > {MAX_ARCHIVE_ENTRIES})")


def read_entry_bounded(open_entry, max_bytes: int = MAX_ENTRY_BYTES) -> bytes:
    """open_entry : fichier déjà ouvert en lecture (ex. zf.open(name) ou rf.open(name)),
    refermé par l'appelant (context manager). Lu en flux, en comptant les octets réellement
    produits — jamais la taille annoncée dans les métadonnées de l'archive, falsifiable."""
    chunks = []
    total = 0
    while True:
        chunk = open_entry.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ArchiveTooLarge(f"Entrée d'archive trop volumineuse (> {max_bytes} octets)")
        chunks.append(chunk)
    return b"".join(chunks)


class BoundedTotalReader:
    """Compteur cumulatif à partager entre plusieurs appels à read_entry_bounded, pour
    plafonner la somme de toutes les entrées lues d'une même archive — pas seulement chacune
    individuellement (une archive à 1000 entrées de 50 Mo passerait le plafond par-entrée mais
    représenterait quand même 50 Go une fois toutes décompressées)."""

    def __init__(self, max_total: int = MAX_ARCHIVE_TOTAL_BYTES):
        self.max_total = max_total
        self.total = 0

    def add(self, n: int) -> None:
        self.total += n
        if self.total > self.max_total:
            raise ArchiveTooLarge(
                f"Archive trop volumineuse une fois décompressée (> {self.max_total} octets cumulés)"
            )
