from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from ..models.db_models import ActivityLog, User

MAX_LOGS = 500

# ── Signal d'activité suspecte ──────────────────────────────────────────────────
# Règles simples calculées à la demande sur les entrées récentes (pas de table dédiée, pas
# de job de fond) : le volume de logs sur un NAS personnel reste trivial à parcourir en
# Python à chaque consultation.
ALERT_LOOKBACK_HOURS = 24
FAILED_LOGIN_WINDOW_MINUTES = 15
FAILED_LOGIN_BURST_THRESHOLD = 5
SUCCESS_AFTER_FAILURES_THRESHOLD = 3


async def get_security_alerts(db: AsyncSession) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=ALERT_LOOKBACK_HOURS)
    window = timedelta(minutes=FAILED_LOGIN_WINDOW_MINUTES)

    login_rows = (await db.execute(
        select(ActivityLog)
        .where(ActivityLog.action == "login", ActivityLog.created_at >= since)
        .order_by(ActivityLog.created_at)
    )).scalars().all()

    alerts: list[dict] = []

    # Règle 1 — rafale d'échecs de connexion (tous comptes confondus : sur une app perso, un
    # seul faux positif possible — plusieurs personnes qui se trompent en même temps — est un
    # bien meilleur compromis que de rater une vraie rafale en filtrant par identifiant, qui
    # n'est de toute façon pas structuré (seulement dans le texte libre de description).
    failures = [r for r in login_rows if r.status == "error"]
    best_burst = None
    lo = 0
    for hi in range(len(failures)):
        while failures[hi].created_at - failures[lo].created_at > window:
            lo += 1
        count = hi - lo + 1
        if count >= FAILED_LOGIN_BURST_THRESHOLD and (best_burst is None or count > best_burst[2]):
            best_burst = (failures[lo].created_at, failures[hi].created_at, count, failures[hi].ip_address)
    if best_burst:
        start, end, count, ip = best_burst
        alerts.append({
            "severity": "warning",
            "label": "Rafale d'échecs de connexion",
            "detail": f"{count} échecs entre {start:%d/%m %H:%M} et {end:%d/%m %H:%M}" + (f" — IP {ip}" if ip else ""),
            "created_at": end,
        })

    # Règle 2 — le signal le plus fort : une connexion RÉUSSIE juste après plusieurs échecs.
    # Un brute-force qui a fini par passer, potentiellement.
    for idx, r in enumerate(login_rows):
        if r.status != "ok":
            continue
        preceding_failures = [
            p for p in login_rows[:idx]
            if p.status == "error" and r.created_at - p.created_at <= window
        ]
        if len(preceding_failures) >= SUCCESS_AFTER_FAILURES_THRESHOLD:
            alerts.append({
                "severity": "error",
                "label": "Connexion réussie après plusieurs échecs",
                "detail": f"« {r.username_snapshot or '?'} », {len(preceding_failures)} échec(s) juste avant"
                          + (f" — IP {r.ip_address}" if r.ip_address else ""),
                "created_at": r.created_at,
            })

    # Règle 3 — l'historique effacé n'est jamais anodin, toujours remonté.
    clear_rows = (await db.execute(
        select(ActivityLog).where(ActivityLog.action == "clear_logs", ActivityLog.created_at >= since)
    )).scalars().all()
    for r in clear_rows:
        alerts.append({
            "severity": "info",
            "label": "Historique effacé",
            "detail": f"Par « {r.username_snapshot or '?'} »" + (f" — IP {r.ip_address}" if r.ip_address else ""),
            "created_at": r.created_at,
        })

    alerts.sort(key=lambda a: a["created_at"], reverse=True)
    return alerts


async def log(db: AsyncSession, action: str, description: str, status: str = "ok", user: User | None = None, ip: str | None = None) -> None:
    entry = ActivityLog(
        action=action, description=description, status=status,
        user_id=user.id if user else None,
        username_snapshot=user.username if user else None,
        ip_address=ip,
    )
    db.add(entry)
    await db.flush()

    # Purge des entrées les plus anciennes au-delà de MAX_LOGS
    count = (await db.execute(select(func.count()).select_from(ActivityLog))).scalar() or 0
    if count > MAX_LOGS:
        oldest_ids = (await db.execute(
            select(ActivityLog.id).order_by(ActivityLog.id.asc()).limit(count - MAX_LOGS)
        )).scalars().all()
        if oldest_ids:
            await db.execute(delete(ActivityLog).where(ActivityLog.id.in_(oldest_ids)))
