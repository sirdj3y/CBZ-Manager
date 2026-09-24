"""
Extraction d'une page individuelle depuis un CBZ/CBR/PDF, sans jamais décompresser
l'archive entière — utilisé par le lecteur web (routers/reader.py) ET le streaming de page
OPDS-PSE (routers/opds.py). Factorisé ici pour que les deux consommateurs restent
strictement synchronisés (même tri des pages, même extraction), au lieu d'entretenir deux
copies de la même logique.
"""
from pathlib import Path
import zipfile

from .archive_safety import read_entry_bounded

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def get_cbz_pages(filepath: str) -> list[str]:
    """Return sorted list of image filenames inside a CBZ."""
    with zipfile.ZipFile(filepath, "r") as zf:
        names = [
            n for n in zf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTS
            and not n.startswith("__MACOSX")
        ]
        return sorted(names)


def extract_cbz_page(filepath: str, page_index: int) -> bytes:
    pages = get_cbz_pages(filepath)
    if page_index < 0 or page_index >= len(pages):
        raise IndexError(f"Page {page_index} hors limites ({len(pages)} pages)")
    with zipfile.ZipFile(filepath, "r") as zf:
        # Lu en flux (voir archive_safety) plutôt que zf.read() direct : la taille annoncée
        # dans les métadonnées ZIP d'une entrée n'est pas fiable, une archive minuscule peut
        # en déclarer une énorme (zip bomb) — zf.read() la décompresserait entièrement en
        # mémoire avant qu'on ait pu s'en apercevoir.
        with zf.open(pages[page_index]) as entry:
            return read_entry_bounded(entry)


def extract_cbr_page(filepath: str, page_index: int) -> bytes:
    import rarfile
    with rarfile.RarFile(filepath, "r") as rf:
        names = sorted([
            n for n in rf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTS
        ])
        if page_index < 0 or page_index >= len(names):
            raise IndexError(f"Page {page_index} hors limites ({len(names)} pages)")
        with rf.open(names[page_index]) as entry:
            return read_entry_bounded(entry)


def extract_pdf_page(filepath: str, page_index: int) -> bytes:
    import fitz
    doc = fitz.open(filepath)
    if page_index < 0 or page_index >= doc.page_count:
        raise IndexError(f"Page {page_index} hors limites ({doc.page_count} pages)")
    page = doc[page_index]
    mat = fitz.Matrix(1.5, 1.5)  # ~150 DPI
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("jpeg")
    doc.close()
    return img_bytes


def get_page_count(filepath: str, fmt: str) -> int:
    if fmt == "cbz":
        return len(get_cbz_pages(filepath))
    elif fmt == "cbr":
        import rarfile
        with rarfile.RarFile(filepath, "r") as rf:
            return len([n for n in rf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS])
    elif fmt == "pdf":
        import fitz
        doc = fitz.open(filepath)
        count = doc.page_count
        doc.close()
        return count
    return 0


def extract_page(filepath: str, fmt: str, page_index: int) -> bytes:
    """Point d'entrée unique par format — lève IndexError (page hors limites) ou toute
    autre exception d'extraction, à charge de l'appelant de les traduire en réponse HTTP."""
    if fmt == "cbz":
        return extract_cbz_page(filepath, page_index)
    elif fmt == "cbr":
        return extract_cbr_page(filepath, page_index)
    elif fmt == "pdf":
        return extract_pdf_page(filepath, page_index)
    raise ValueError(f"Format non supporté: {fmt}")
