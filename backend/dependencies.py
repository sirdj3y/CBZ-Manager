from fastapi import Request
from .database import get_db

__all__ = ["get_db", "auth_required"]


async def auth_required(request: Request) -> None:
    pass
