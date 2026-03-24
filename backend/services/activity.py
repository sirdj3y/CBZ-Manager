from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from ..models.db_models import ActivityLog

MAX_LOGS = 500


async def log(db: AsyncSession, action: str, description: str, status: str = "ok") -> None:
    entry = ActivityLog(action=action, description=description, status=status)
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
