from fastapi import APIRouter
from ..models.schemas import AuthStatus

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=AuthStatus)
async def me():
    return AuthStatus(authenticated=True)
