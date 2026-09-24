"""Lignes rattachées à un album, une série ou un compte qui n'existe plus.

SQLite n'applique pas les ON DELETE CASCADE ici (pas de PRAGMA foreign_keys=ON) : seules les
cascades ORM nettoient, et une relation oubliée laisse des lignes derrière elle. Comme SQLite
réutilise les id libérés, ces lignes se rattachent ensuite au prochain album/compte créé
(progression de lecture, temps de lecture, listes intelligentes d'un autre). Les causes
connues sont corrigées à la source (voir tests/test_deletion_cleanup.py) ; cette vérification
nettoie ce qu'elles ont laissé en base avant correctif, et sert de filet de sécurité.

Une nouvelle table rattachée à tomes/series/users s'ajoute à CHECKS.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_PARENT_LABELS = {"tomes": "un album supprimé", "series": "une série supprimée", "users": "un compte supprimé"}

# (clé, libellé, table, colonne, table parente). Tout le SQL est construit à partir de ces
# constantes uniquement — jamais d'une valeur reçue par l'API (voir delete_orphans).
CHECKS: list[tuple[str, str, str, str, str]] = [
    ("user_tome_data_tome", "Progression, notes et étiquettes d'album", "user_tome_data", "tome_id", "tomes"),
    ("user_tome_data_user", "Progression, notes et étiquettes d'album", "user_tome_data", "user_id", "users"),
    ("reading_activity_tome", "Temps de lecture", "reading_activity", "tome_id", "tomes"),
    ("reading_activity_user", "Temps de lecture", "reading_activity", "user_id", "users"),
    ("smart_lists_user", "Listes intelligentes", "smart_lists", "owner_id", "users"),
    ("user_hidden_series_series", "Séries masquées", "user_hidden_series", "series_id", "series"),
    ("user_hidden_series_user", "Séries masquées", "user_hidden_series", "user_id", "users"),
    ("ignored_missing_albums", "Albums manquants ignorés", "ignored_missing_albums", "series_id", "series"),
    ("missing_albums", "Albums manquants", "missing_albums", "series_id", "series"),
    ("metadata", "Métadonnées d'album", "metadata", "tome_id", "tomes"),
    ("tome_page_panels", "Cases détectées (zoom sur les cases)", "tome_page_panels", "tome_id", "tomes"),
]
_BY_KEY = {c[0]: c for c in CHECKS}


def _where(column: str, parent: str) -> str:
    return f"{column} IS NOT NULL AND {column} NOT IN (SELECT id FROM {parent})"


async def find_orphans(db: AsyncSession) -> list[dict]:
    """Une entrée par vérification qui trouve au moins une ligne orpheline."""
    found = []
    for key, label, table, column, parent in CHECKS:
        rows = (await db.execute(text(
            f"SELECT DISTINCT {column} FROM {table} WHERE {_where(column, parent)} ORDER BY {column}"
        ))).scalars().all()
        if not rows:
            continue
        count = (await db.execute(text(f"SELECT count(*) FROM {table} WHERE {_where(column, parent)}"))).scalar()
        found.append({
            "key": key,
            "label": label,
            "count": count,
            "detail": f"{count} ligne(s) rattachée(s) à {_PARENT_LABELS[parent]} ({column} {', '.join(map(str, rows[:10]))}{'…' if len(rows) > 10 else ''})",
        })
    return found


async def delete_orphans(db: AsyncSession, key: str) -> int:
    """Supprime les lignes orphelines d'une vérification. KeyError si la clé est inconnue."""
    _, _, table, column, parent = _BY_KEY[key]
    result = await db.execute(text(f"DELETE FROM {table} WHERE {_where(column, parent)}"))
    await db.commit()
    return result.rowcount
