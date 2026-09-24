from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import UserTomeData


async def get_user_tome_data(db: AsyncSession, user_id: int, tome_id: int) -> UserTomeData | None:
    return (await db.execute(
        select(UserTomeData).where(UserTomeData.user_id == user_id, UserTomeData.tome_id == tome_id)
    )).scalar_one_or_none()


async def get_or_create_user_tome_data(db: AsyncSession, user_id: int, tome_id: int) -> UserTomeData:
    ud = await get_user_tome_data(db, user_id, tome_id)
    if ud is None:
        ud = UserTomeData(user_id=user_id, tome_id=tome_id)
        db.add(ud)
    return ud
