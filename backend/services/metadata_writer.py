"""
Port of batch_edit_dialog._write_metadata_to_cbz and _build_comicinfo_xml.
Writes/updates ComicInfo.xml inside a CBZ archive.
"""
import asyncio
import zipfile
import shutil
from pathlib import Path


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


def _write_sync(filepath: str, fields: dict) -> None:
    path = Path(filepath)
    if not path.suffix.lower() in (".cbz", ".zip"):
        raise ValueError("Seuls les fichiers CBZ peuvent être modifiés directement")

    new_xml = build_comicinfo_xml(fields).encode("utf-8")

    # Read entire archive into memory, excluding old ComicInfo.xml
    entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(filepath, "r") as zf:
        for name in zf.namelist():
            if name.lower() == "comicinfo.xml":
                continue
            entries.append((name, zf.read(name)))

    # Write to temp file
    tmp = path.with_suffix(".tmp.cbz")
    try:
        with zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr("ComicInfo.xml", new_xml)
            for name, data in entries:
                out.writestr(name, data)
        shutil.move(str(tmp), filepath)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


async def write_metadata(filepath: str, fields: dict) -> None:
    """Async wrapper: rewrites ComicInfo.xml inside a CBZ."""
    await asyncio.to_thread(_write_sync, filepath, fields)
