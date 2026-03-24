import re
from typing import Optional


# Primary pattern: "{Série} - T{nn} - {Titre}"
# Matches: "Akira - T01 - Akira", "Blacksad - T03 - Âme rouge"
_PRIMARY_PATTERN = re.compile(
    r"^(?P<series>.+?)\s*-\s*[Tt](?P<number>\d+)\s*-\s*(?P<title>.+)$"
)

# Secondary pattern: "{Série} T{nn} - {Titre}" (no dash before number)
# Matches: "Le retour à la terre T01 - La vraie vie"
_SECONDARY_PATTERN = re.compile(
    r"^(?P<series>.+?)\s+[Tt](?P<number>\d+)\s*-\s*(?P<title>.+)$"
)

# Fallback pattern: "{Série} - {Titre}" (no tome number)
_FALLBACK_PATTERN = re.compile(
    r"^(?P<series>.+?)\s*-\s*(?P<title>.+)$"
)

# Number-only pattern for generic filenames: "Série 01 Titre"
_NUMBER_INLINE = re.compile(r"\b(\d{1,3})\b")


def parse_filename(stem: str) -> dict:
    """
    Parse a comic filename stem into series / number / title parts.

    Supported formats:
      - "Akira - T01 - Akira"                       → {series: "Akira", number: "1", title: "Akira"}
      - "Le retour à la terre T01 - La vraie vie"   → {series: "Le retour à la terre", number: "1", title: "La vraie vie"}
      - "Akira - Akira"                             → {series: "Akira", number: None, title: "Akira"}
      - "Akira"                                     → {series: "Akira", number: None, title: None}

    Returns a dict with keys: series, number, title (all Optional[str])
    """
    stem = stem.strip()

    m = _PRIMARY_PATTERN.match(stem)
    if m:
        return {
            "series": m.group("series").strip(),
            "number": m.group("number").lstrip("0") or "0",
            "title": m.group("title").strip(),
        }

    m = _SECONDARY_PATTERN.match(stem)
    if m:
        return {
            "series": m.group("series").strip(),
            "number": m.group("number").lstrip("0") or "0",
            "title": m.group("title").strip(),
        }

    m = _FALLBACK_PATTERN.match(stem)
    if m:
        title = m.group("title").strip().lstrip("- ").strip()
        return {
            "series": m.group("series").strip(),
            "number": None,
            "title": title if title else None,
        }

    return {"series": stem, "number": None, "title": None}


def natural_sort_key(number: Optional[str]) -> tuple:
    """Sort key for tome numbers: numeric-aware."""
    if number is None:
        return (9999, "")
    try:
        return (int(number), "")
    except ValueError:
        return (9999, number)
