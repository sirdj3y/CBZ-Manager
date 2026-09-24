from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import require_admin, require_permission
from ..models.db_models import ActivityLog, User
from ..models.schemas import SecurityAlertOut
from ..services.activity import get_security_alerts
from .auth import get_client_ip

# clear_logs (purge de l'historique, destructif) exige explicitement require_admin en plus,
# voir plus bas.
router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_permission("library.settings"))])


@router.get("/alerts", response_model=list[SecurityAlertOut])
async def get_alerts(db: AsyncSession = Depends(get_db)):
    return await get_security_alerts(db)


@router.get("")
async def get_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActivityLog).order_by(ActivityLog.id.desc()).limit(500)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "description": l.description,
            "status": l.status,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "username_snapshot": l.username_snapshot,
            "ip_address": l.ip_address,
        }
        for l in logs
    ]


@router.delete("")
async def clear_logs(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    from sqlalchemy import delete
    await db.execute(delete(ActivityLog))
    await db.commit()

    # Journalisée APRÈS la purge (dans une transaction séparée) plutôt qu'avant, sinon cette
    # entrée elle-même serait effacée par le DELETE qui la précède — elle doit survivre comme
    # seule trace du fait que l'historique a été vidé, par qui et quand.
    from ..services.activity import log as activity_log
    await activity_log(db, "clear_logs", "Historique effacé", user=current_user, ip=get_client_ip(request))
    await db.commit()

    return {"deleted": True}
