"""
Port of batch_edit_dialog._write_metadata_to_cbz and _build_comicinfo_xml.
Writes/updates ComicInfo.xml inside a CBZ archive.
"""
import asyncio
import uuid
import zipfile
import shutil
from pathlib import Path

from .archive_safety import check_entry_count, read_entry_bounded, BoundedTotalReader
from .file_locks import get_file_lock


COMICINFO_FIELDS = [
    "Title", "Series", "Number", "Count", "Volume",
    "AlternateSeries", "AlternateNumber", "StoryArc", "SeriesGroup",
    "Publisher", "Imprint", "Year", "Month", "Day",
    "LanguageISO", "Format", "Web",
    "Writer", "Penciller", "Inker", "Colorist", "Letterer",
    "CoverArtist", "Editor", "Translator",
    "Genre", "Tags", "AgeRating",
    "Characters", "Teams", "Locations",
    "Summary", "Notes", "PageCount",
    "BlackAndWhite", "Manga", "ScanInformation",
    "CommunityRating", "GTIN", "ISBN",
]


def build_comicinfo_xml(fields: dict) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
    ]
    for key in COMICINFO_FIELDS:
        val = fields.get(key)
        if val is not None and str(val).strip():
            escaped = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"  <{key}>{escaped}</{key}>")
    lines.append("</ComicInfo>")
    return "\n".join(lines)


# Formats déjà compressés — inutile (et coûteux en CPU) de les repasser par DEFLATE,
# ça ne réduit quasiment jamais leur taille. Stockées telles quelles (ZIP_STORED),
# seul ComicInfo.xml (texte, minuscule) profite réellement de la compression.
_PRECOMPRESSED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _write_sync(filepath: str, fields: dict) -> None:
    path = Path(filepath)
    if not path.suffix.lower() in (".cbz", ".zip"):
        raise ValueError("Seuls les fichiers CBZ peuvent être modifiés directement")

    new_xml = build_comicinfo_xml(fields).encode("utf-8")

    # Read entire archive into memory, excluding old ComicInfo.xml. Budget mémoire (voir
    # archive_safety) : la taille annoncée dans les métadonnées ZIP d'une entrée n'est pas
    # fiable, une archive corrompue ou malveillante pourrait en déclarer une énorme.
    entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(filepath, "r") as zf:
        names = [n for n in zf.namelist() if n.lower() != "comicinfo.xml"]
        check_entry_count(len(names))
        budget = BoundedTotalReader()
        for name in names:
            with zf.open(name) as entry:
                data = read_entry_bounded(entry)
            budget.add(len(data))
            entries.append((name, data))

    # Nom temporaire unique (pas seulement ".tmp.cbz" fixe) : deux écritures concurrentes sur
    # le même album ne se marchent plus sur le même fichier temporaire même en cas de course
    # (voir aussi le verrou par chemin dans write_metadata, ceinture et bretelles).
    tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp.cbz")
    try:
        with zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr("ComicInfo.xml", new_xml)
            for name, data in entries:
                compress_type = zipfile.ZIP_STORED if Path(name).suffix.lower() in _PRECOMPRESSED_EXTS else zipfile.ZIP_DEFLATED
                out.writestr(name, data, compress_type=compress_type)
        shutil.move(str(tmp), filepath)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


async def write_metadata(filepath: str, fields: dict) -> None:
    """Async wrapper: rewrites ComicInfo.xml inside a CBZ. Verrouillé par chemin : une
    conversion en cours sur le même album (voir converter_service.py::run_convert_job, même
    registre de verrous) ne doit jamais s'exécuter en même temps qu'une écriture de
    métadonnées, sous peine de lire/écraser un état obsolète de l'un ou l'autre."""
    async with get_file_lock(filepath):
        await asyncio.to_thread(_write_sync, filepath, fields)
