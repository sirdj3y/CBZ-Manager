import re
from typing import Optional


# "T" (abrégé) ou "Tome"/"tome" (en toutes lettres), avec ou sans espace avant le numéro —
# "T01", "T 01", "Tome 01" reconnus indifféremment. re.IGNORECASE couvre aussi "TOME".
_TOME_MARKER = r"T(?:ome)?\.?\s*"

# Numéro de tome : soit un nombre (avec décimale optionnelle et suffixe alphabétique
# optionnel — "13", "13.5", "13b", "7bis"), soit un marqueur spécial purement alphabétique
# avec chiffres optionnels à la fin ("INT" pour intégrale, "HS1" pour hors-série). Sans le
# second cas, un fichier "Série - TINT - Titre" ne matchait aucun motif numéroté : tout le
# "TINT - Titre" finissait avalé dans le titre, et le tome ressortait sans numéro du tout.
# Branche alphabétique volontairement restreinte aux MAJUSCULES ((?-i:...) annule
# re.IGNORECASE localement, actif sur tout le motif par ailleurs) : les vrais marqueurs
# spéciaux sont des sigles en capitales (INT, HS1). Sans cette restriction, un nom de série
# à deux mots dont le second commence par "T" ("Achille Talon", motif sans tiret devant le
# marqueur — voir _SECONDARY_PATTERN) se faisait couper en plein milieu : "T" pris comme
# marqueur de tome, "alon" (minuscules) comme "numéro" — série tronquée en "Achille" seul et
# numéro sans aucun rapport avec le vrai numéro du tome.
_NUMBER_TOKEN = r"(?:\d+(?:\.\d+)?[a-zA-Z]*|(?-i:[A-Z]+)\d*)"

# Primary pattern: "{Série} - T{nn} - {Titre}"
# Matches: "Akira - T01 - Akira", "Blacksad - T03 - Âme rouge"
_PRIMARY_PATTERN = re.compile(
    rf"^(?P<series>.+?)\s*-\s*{_TOME_MARKER}(?P<number>{_NUMBER_TOKEN})\s*-\s*(?P<title>.+)$",
    re.IGNORECASE,
)

# Secondary pattern: "{Série} T{nn} - {Titre}" (no dash before number)
# Matches: "Le retour à la terre T01 - La vraie vie", "Code Breaker Tome 01 - Titre"
_SECONDARY_PATTERN = re.compile(
    rf"^(?P<series>.+?)\s+{_TOME_MARKER}(?P<number>{_NUMBER_TOKEN})\s*-\s*(?P<title>.+)$",
    re.IGNORECASE,
)

# Numéro sans titre (convention courante pour les mangas/séries sans titre par tome) :
# "{Série} - T{nn}" ou "{Série} T{nn}". Doit être tenté avant _FALLBACK_PATTERN, sinon
# celui-ci interprète le "T01" comme un titre et le numéro est perdu.
_NUMBER_ONLY_PATTERN = re.compile(
    rf"^(?P<series>.+?)\s*-\s*{_TOME_MARKER}(?P<number>{_NUMBER_TOKEN})\s*$",
    re.IGNORECASE,
)
_SECONDARY_NUMBER_ONLY_PATTERN = re.compile(
    rf"^(?P<series>.+?)\s+{_TOME_MARKER}(?P<number>{_NUMBER_TOKEN})\s*$",
    re.IGNORECASE,
)

# Fallback pattern: "{Série} - {Titre}" (no tome number)
_FALLBACK_PATTERN = re.compile(
    r"^(?P<series>.+?)\s*-\s*(?P<title>.+)$"
)

# Number-only pattern for generic filenames: "Série 01 Titre"
_NUMBER_INLINE = re.compile(r"\b(\d{1,3})\b")


def _normalize_number(raw: str) -> str:
    """Retire les zéros de tête d'un numéro purement numérique ("013" -> "13", "00" -> "0",
    ré-affiché avec son padding d'origine par fmtNumber() côté frontend). Laissé tel quel
    pour un numéro alphanumérique ("13b", "INT") : un lstrip("0") aveugle tronquerait par
    erreur un cas comme "0b" en "b", perdant le chiffre."""
    if raw.isdigit():
        return raw.lstrip("0") or "0"
    return raw


def parse_filename(stem: str) -> dict:
    """
    Parse a comic filename stem into series / number / title parts.

    Supported formats:
      - "Akira - T01 - Akira"                       → {series: "Akira", number: "1", title: "Akira"}
      - "Le retour à la terre T01 - La vraie vie"   → {series: "Le retour à la terre", number: "1", title: "La vraie vie"}
      - "Horimiya - T01"                             → {series: "Horimiya", number: "1", title: None}
      - "Code Breaker Tome 01"                       → {series: "Code Breaker", number: "1", title: None}
      - "Akira - Akira"                             → {series: "Akira", number: None, title: "Akira"}
      - "Leave them alone"                          → {series: None, number: None, title: "Leave them alone"}

    Returns a dict with keys: series, number, title (all Optional[str])
    """
    stem = stem.strip()

    m = _PRIMARY_PATTERN.match(stem)
    if m:
        return {
            "series": m.group("series").strip(),
            "number": _normalize_number(m.group("number")),
            "title": m.group("title").strip(),
        }

    m = _SECONDARY_PATTERN.match(stem)
    if m:
        return {
            "series": m.group("series").strip(),
            "number": _normalize_number(m.group("number")),
            "title": m.group("title").strip(),
        }

    m = _NUMBER_ONLY_PATTERN.match(stem) or _SECONDARY_NUMBER_ONLY_PATTERN.match(stem)
    if m:
        return {
            "series": m.group("series").strip(),
            "number": _normalize_number(m.group("number")),
            "title": None,
        }

    m = _FALLBACK_PATTERN.match(stem)
    if m:
        title = m.group("title").strip().lstrip("- ").strip()
        return {
            "series": m.group("series").strip(),
            "number": None,
            "title": title if title else None,
        }

    # Aucun motif reconnu (pas de tiret, pas de numéro de tome) : un nom de fichier "plat"
    # est bien plus souvent un titre seul (cas typique d'un one-shot) qu'un nom de série
    # sans titre — l'ancien comportement (tout dans "series") laissait "title" à None
    # indéfiniment, y compris après renommage sur {Titre} pour un one-shot.
    return {"series": None, "number": None, "title": stem if stem else None}


def natural_sort_key(number: Optional[str]) -> tuple:
    """Sort key for tome numbers: numeric-aware."""
    if number is None:
        return (9999, "")
    try:
        return (int(number), "")
    except ValueError:
        return (9999, number)
