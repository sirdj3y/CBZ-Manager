"""Moteur de règles pour les smart lists — construit dynamiquement une expression SQLAlchemy
à partir d'un arbre de règles (OU entre groupes, ET entre conditions d'un même groupe),
jamais une liste de résultats précalculée à recalculer en tâche de fond : toute smart list
est réévaluée à la demande, donc reste toujours à jour sans job de maintenance."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import Metadata, Series, Tome, UserTomeData
from .classification import CLASSIFICATIONS


# ── Catalogue de champs exposé à l'UI (générateur de règles) ──────────────────────────────

FIELDS: list[dict] = [
    {"source": "file", "field": "title", "label": "Titre", "type": "text"},
    {"source": "file", "field": "filename", "label": "Nom de fichier", "type": "text"},
    {"source": "file", "field": "file_format", "label": "Extension", "type": "text", "choices": ["cbz", "cbr", "pdf"]},
    {"source": "file", "field": "file_size_mb", "label": "Taille du fichier (Mo)", "type": "numeric"},
    {"source": "file", "field": "page_count", "label": "Nombre de pages", "type": "numeric"},
    {"source": "file", "field": "created_at", "label": "Ajouté le", "type": "date"},
    {"source": "file", "field": "updated_at", "label": "Mis à jour le", "type": "date"},
    {"source": "file", "field": "is_oneshot", "label": "One-shot", "type": "boolean"},
    {"source": "file", "field": "tag", "label": "Étiquette", "type": "text"},
    {"source": "metadata", "field": "Title", "label": "Titre (métadonnées)", "type": "text"},
    {"source": "metadata", "field": "Notes", "label": "Notes", "type": "text"},
    {"source": "metadata", "field": "Genre", "label": "Genre", "type": "text"},
    {"source": "metadata", "field": "Writer", "label": "Scénariste", "type": "text"},
    {"source": "metadata", "field": "Penciller", "label": "Dessinateur", "type": "text"},
    {"source": "metadata", "field": "Publisher", "label": "Éditeur", "type": "text"},
    {"source": "metadata", "field": "Year", "label": "Année", "type": "text"},
    {"source": "metadata", "field": "Month", "label": "Mois de parution", "type": "text"},
    {"source": "metadata", "field": "Day", "label": "Jour de parution", "type": "text"},
    {"source": "metadata", "field": "LanguageISO", "label": "Langue (ISO)", "type": "text"},
    {"source": "metadata", "field": "ISBN", "label": "ISBN", "type": "text"},
    {"source": "metadata", "field": "Summary", "label": "Résumé", "type": "text"},
    {"source": "series", "field": "name", "label": "Nom de la série", "type": "text"},
    {"source": "series", "field": "classification", "label": "Classification", "type": "text", "choices": CLASSIFICATIONS},
]

OPERATORS_BY_TYPE: dict[str, list[str]] = {
    "text":    ["contains", "not_contains", "is", "is_not", "is_empty", "is_not_empty"],
    "numeric": ["is", "is_not", "is_empty", "is_not_empty", "gt", "lt", "between"],
    "date":    ["is", "is_not", "is_empty", "is_not_empty", "gt", "lt", "between"],
    "boolean": ["is"],
}

_FIELD_INDEX = {(f["source"], f["field"]): f for f in FIELDS}

_TOME_TEXT_COLUMNS = {"title": Tome.title, "filename": Tome.filename, "file_format": Tome.file_format}
_TOME_NUMERIC_COLUMNS = {"page_count": Tome.page_count}
_TOME_DATE_COLUMNS = {"created_at": Tome.created_at, "updated_at": Tome.updated_at}
_TOME_BOOL_COLUMNS = {"is_oneshot": Tome.is_oneshot}

_METADATA_TEXT_COLUMNS = {
    name: getattr(Metadata, name)
    for name in (
        "Title", "Notes", "Genre", "Writer", "Penciller", "Publisher", "Year", "Month", "Day",
        "LanguageISO", "ISBN", "Summary",
    )
}

_SERIES_TEXT_COLUMNS = {"name": Series.name, "classification": Series.classification}


def get_fields_catalog() -> list[dict]:
    return [{**f, "operators": OPERATORS_BY_TYPE[f["type"]]} for f in FIELDS]


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _text_expr(col, operator: str, value):
    value = (value or "").strip()
    if operator == "is_empty":
        return or_(col.is_(None), col == "")
    if operator == "is_not_empty":
        return and_(col.isnot(None), col != "")
    pattern = f"%{_escape_like(value)}%"
    if operator == "contains":
        return col.ilike(pattern, escape="\\")
    if operator == "not_contains":
        return or_(col.is_(None), ~col.ilike(pattern, escape="\\"))
    if operator == "is":
        return func.lower(col) == value.lower()
    if operator == "is_not":
        return or_(col.is_(None), func.lower(col) != value.lower())
    raise ValueError(f"Opérateur texte invalide : {operator}")


def _to_number(value) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"Valeur numérique invalide : {value!r}")


def _numeric_expr(col, operator: str, value, value2, scale: float = 1):
    if operator == "is_empty":
        return col.is_(None)
    if operator == "is_not_empty":
        return col.isnot(None)
    n = _to_number(value) * scale
    if operator == "is":
        return col == n
    if operator == "is_not":
        return or_(col.is_(None), col != n)
    if operator == "gt":
        return col > n
    if operator == "lt":
        return col < n
    if operator == "between":
        n2 = _to_number(value2) * scale
        lo, hi = sorted([n, n2])
        return and_(col >= lo, col <= hi)
    raise ValueError(f"Opérateur numérique invalide : {operator}")


def _parse_day(value) -> datetime:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError(f"Date invalide (AAAA-MM-JJ attendu) : {value!r}")


def _date_expr(col, operator: str, value, value2):
    if operator == "is_empty":
        return col.is_(None)
    if operator == "is_not_empty":
        return col.isnot(None)
    day = _parse_day(value)
    day_start, day_end = day, day + timedelta(days=1)
    if operator == "is":
        return and_(col >= day_start, col < day_end)
    if operator == "is_not":
        return or_(col.is_(None), col < day_start, col >= day_end)
    if operator == "gt":
        return col >= day_end
    if operator == "lt":
        return col < day_start
    if operator == "between":
        day2 = _parse_day(value2)
        lo, hi = sorted([day_start, day2 + timedelta(days=1)])
        return and_(col >= lo, col < hi)
    raise ValueError(f"Opérateur date invalide : {operator}")


def _boolean_expr(col, operator: str, value):
    if operator != "is":
        raise ValueError("Seul l'opérateur 'est' est valide pour ce champ")
    truthy = str(value).strip().lower() in ("1", "true", "vrai", "oui", "yes")
    return col == truthy


def _tag_expr(operator: str, value, current_user_id: int):
    """Étiquettes personnelles (UserTomeData.tag_list, JSON list) de l'utilisateur courant —
    correspondance par sous-chaîne sur la représentation JSON, approximation suffisante pour
    un filtrage (les étiquettes ne contiennent ni guillemet ni caractère JSON spécial, elles
    viennent d'AutocompleteInput en texte libre court)."""
    value = (value or "").strip()
    base = select(UserTomeData.tome_id).where(
        UserTomeData.user_id == current_user_id, UserTomeData.tome_id == Tome.id
    )
    if operator == "is_empty":
        sub = base.where(or_(UserTomeData.tag_list.is_(None), UserTomeData.tag_list == "[]"))
        return ~sub.exists()
    if operator == "is_not_empty":
        sub = base.where(UserTomeData.tag_list.isnot(None), UserTomeData.tag_list != "[]")
        return sub.exists()
    if operator == "is":
        pattern = f'%"{_escape_like(value)}"%'
    elif operator in ("contains", "not_contains", "is_not"):
        pattern = f"%{_escape_like(value)}%"
    else:
        raise ValueError(f"Opérateur invalide pour étiquette : {operator}")
    sub = base.where(UserTomeData.tag_list.ilike(pattern, escape="\\"))
    if operator in ("is", "contains"):
        return sub.exists()
    return ~sub.exists()


def _build_condition(cond: dict, current_user_id: int):
    if not isinstance(cond, dict):
        raise ValueError("Chaque condition doit être un objet")
    source = cond.get("source")
    field = cond.get("field")
    operator = cond.get("operator")
    value = cond.get("value")
    value2 = cond.get("value2")

    meta = _FIELD_INDEX.get((source, field))
    if meta is None:
        raise ValueError(f"Champ inconnu : {source}.{field}")
    if operator not in OPERATORS_BY_TYPE[meta["type"]]:
        raise ValueError(f"Opérateur '{operator}' invalide pour ce champ")

    if source == "file" and field == "tag":
        return _tag_expr(operator, value, current_user_id)
    if source == "file" and field == "file_size_mb":
        return _numeric_expr(Tome.file_size, operator, value, value2, scale=1024 * 1024)
    if source == "file":
        col = {**_TOME_TEXT_COLUMNS, **_TOME_NUMERIC_COLUMNS, **_TOME_DATE_COLUMNS, **_TOME_BOOL_COLUMNS}[field]
    elif source == "metadata":
        col = _METADATA_TEXT_COLUMNS[field]
    elif source == "series":
        col = _SERIES_TEXT_COLUMNS[field]
    else:
        raise ValueError(f"Source inconnue : {source}")

    if meta["type"] == "text":
        return _text_expr(col, operator, value)
    if meta["type"] == "numeric":
        return _numeric_expr(col, operator, value, value2)
    if meta["type"] == "date":
        return _date_expr(col, operator, value, value2)
    if meta["type"] == "boolean":
        return _boolean_expr(col, operator, value)
    raise ValueError("Type de champ non géré")  # pragma: no cover — FIELDS ne déclare que ces 4 types


def rules_to_expression(rules: dict, current_user_id: int):
    """Retourne l'expression WHERE (OU de groupes, ET de conditions), ou None si aucune règle
    n'est définie (la smart list matche alors tout). Lève ValueError si les règles sont
    malformées — jamais d'exception d'un autre type, pour que l'appelant puisse répondre 400."""
    if not isinstance(rules, dict):
        raise ValueError("'rules' doit être un objet")
    groups = rules.get("groups") or []
    if not isinstance(groups, list):
        raise ValueError("'groups' doit être une liste")

    group_exprs = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Chaque groupe doit être un objet")
        conditions = group.get("conditions") or []
        if not isinstance(conditions, list):
            raise ValueError("'conditions' doit être une liste")
        cond_exprs = [_build_condition(c, current_user_id) for c in conditions]
        if cond_exprs:
            group_exprs.append(and_(*cond_exprs))

    if not group_exprs:
        return None
    return or_(*group_exprs)


def validate_rules(rules: dict, current_user_id: int) -> None:
    """Valide la structure sans exécuter de requête — appelé à la création/modification
    d'une smart list pour rejeter immédiatement une règle malformée (400) plutôt qu'à la
    première consultation de la liste."""
    rules_to_expression(rules, current_user_id)


async def build_smart_list_query(db: AsyncSession, smart_list, current_user):
    """Requête Tome+Metadata correspondant aux règles de la smart list, déjà filtrée par
    visibilité (albums/séries masqués — mêmes règles que la navigation par défaut, pas de
    bascule 'afficher les masqués' pour une smart list). Toujours recalculée à la demande."""
    from .hidden_series import get_user_hidden_series_ids, get_user_age_restricted_series_ids

    try:
        rules = json.loads(smart_list.rules) if smart_list.rules else {}
    except json.JSONDecodeError:
        rules = {}
    expr = rules_to_expression(rules, current_user.id)

    q = (
        select(Tome, Metadata)
        .join(Series, Series.id == Tome.series_id)
        .outerjoin(Metadata, Metadata.tome_id == Tome.id)
        .where(Tome.hidden == False, Series.hidden == False)
    )
    if not current_user.is_admin:
        excluded_ids = await get_user_hidden_series_ids(db, current_user.id)
        excluded_ids |= await get_user_age_restricted_series_ids(db, current_user.age_rating_limit)
        if excluded_ids:
            q = q.where(Tome.series_id.notin_(excluded_ids))
    if expr is not None:
        q = q.where(expr)
    return q.order_by(Series.name, Tome.number)


async def get_smart_list_series_ids(db: AsyncSession, smart_list, current_user) -> list[int]:
    """Ids des séries ayant au moins un tome correspondant aux règles — pour les smart lists
    en result_type='series' : les critères restent évalués album par album (y compris ceux
    qui n'ont de sens qu'à ce niveau — nombre de pages, taille, date d'ajout, étiquette...),
    'au moins un album de la série remplit la condition' fait alors office de critère série."""
    tome_q = await build_smart_list_query(db, smart_list, current_user)
    ids_q = tome_q.order_by(None).with_only_columns(Tome.series_id).distinct()
    return list((await db.execute(ids_q)).scalars().all())


# ── Listes par défaut ───────────────────────────────────────────────────────────────────

DEFAULT_SMART_LISTS: list[tuple[str, dict]] = [
    ("BD franco-belge", {"groups": [{"conditions": [
        {"source": "series", "field": "classification", "operator": "is", "value": "BD franco-belge"}
    ]}]}),
    ("Comics", {"groups": [{"conditions": [
        {"source": "series", "field": "classification", "operator": "is", "value": "Comics"}
    ]}]}),
    ("Manga", {"groups": [{"conditions": [
        {"source": "series", "field": "classification", "operator": "is", "value": "Manga"}
    ]}]}),
    ("One-shot", {"groups": [{"conditions": [
        {"source": "file", "field": "is_oneshot", "operator": "is", "value": "true"}
    ]}]}),
]


async def seed_default_smart_lists(db: AsyncSession) -> None:
    """Listes de départ (classification + one-shot), pour ne pas laisser un admin devant un
    écran Collections vide au premier démarrage. Idempotent comme seed_default_profiles : ne
    fait rien si une smart list existe déjà — y compris si l'admin en a supprimé depuis, on
    ne les recrée jamais après coup."""
    from ..models.db_models import SmartList, User

    existing = (await db.execute(select(SmartList).limit(1))).scalar_one_or_none()
    if existing is not None:
        return
    admin = (await db.execute(select(User).where(User.is_admin == True).order_by(User.id).limit(1))).scalar_one_or_none()
    if admin is None:
        return
    for i, (name, rules) in enumerate(DEFAULT_SMART_LISTS):
        db.add(SmartList(
            name=name, owner_id=admin.id, shared=True, is_default=True, sort_order=i,
            rules=json.dumps(rules, ensure_ascii=False),
        ))
    await db.commit()
