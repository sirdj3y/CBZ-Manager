from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import ActivityLog

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(auth_required)])


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
        }
        for l in logs
    ]


@router.delete("")
async def clear_logs(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete
    await db.execute(delete(ActivityLog))
    await db.commit()
    return {"deleted": True}
