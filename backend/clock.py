"""Heure courante de l'app : UTC, sans fuseau attaché (« naïve »), comme toutes les dates
stockées en base (voir models.db_models.UTCDateTime, qui les rend explicitement UTC à la
lecture). Remplace datetime.utcnow(), dépréciée depuis Python 3.12, sans rien changer aux
valeurs produites."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
