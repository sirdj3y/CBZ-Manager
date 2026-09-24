from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db

router = APIRouter(prefix="/api", tags=["health"])

_VERSION_FILE = Path(__file__).parent.parent.parent / "VERSION"


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"
    version = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "0.0.0"
    return {"status": "ok", "version": version, "db": db_status}
