"""Passkeys : enregistrement (compte connecté), liste, suppression, connexion.
Voir services/passkeys.py pour le principe et les contraintes (domaine, HTTPS)."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    base64url_to_bytes, generate_authentication_options, generate_registration_options,
    options_to_json, verify_authentication_response, verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..clock import utcnow
from ..database import get_db
from ..dependencies import get_current_user
from ..models.db_models import Passkey, User
from ..services import auth as auth_service
from ..services import passkeys as pk
from ..services.activity import log as activity_log
from .auth import _cookie_kwargs, _login_rate_limiter, _status, get_client_ip

router = APIRouter(prefix="/api/auth/passkeys", tags=["passkeys"])


class RegisterVerifyIn(BaseModel):
    challenge_id: str
    name: str
    credential: dict


class LoginVerifyIn(BaseModel):
    challenge_id: str
    credential: dict


def _rp() -> tuple[str, str]:
    try:
        return pk.relying_party()
    except pk.PasskeysUnavailable as e:
        raise HTTPException(status_code=409, detail=str(e))


def _out(p: Passkey) -> dict:
    return {"id": p.id, "name": p.name, "created_at": p.created_at, "last_used_at": p.last_used_at}


@router.get("/status")
async def passkeys_status():
    """Public (page de connexion) : les passkeys sont-elles utilisables, et depuis quelle
    adresse ? L'interface ne propose la passkey que si la page est ouverte depuis celle-ci."""
    return pk.status()


# ── Compte connecté ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_passkeys(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at))).scalars()
    return [_out(p) for p in rows]


@router.post("/register/options")
async def register_options(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rp_id, _ = _rp()
    existing = (await db.execute(select(Passkey.credential_id).where(Passkey.user_id == user.id))).scalars().all()
    challenge_id, challenge = pk.new_challenge(user.id)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="CBZ Manager",
        user_name=user.username,
        user_id=f"cbz-user-{user.id}".encode(),
        challenge=challenge,
        # Passkey « découvrable » : connexion sans saisir d'identifiant.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in existing],
    )
    return {"challenge_id": challenge_id, "options": json.loads(options_to_json(options))}


@router.post("/register/verify")
async def register_verify(body: RegisterVerifyIn, request: Request,
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rp_id, origin = _rp()
    challenge = pk.take_challenge(body.challenge_id, user.id)
    if challenge is None:
        raise HTTPException(status_code=400, detail="Demande expirée. Recommencez.")
    try:
        verified = verify_registration_response(
            credential=body.credential, expected_challenge=challenge, expected_rp_id=rp_id,
            expected_origin=origin, require_user_verification=True,
        )
    except InvalidRegistrationResponse:
        raise HTTPException(status_code=400, detail="Passkey refusée par la vérification.")
    passkey = Passkey(
        user_id=user.id,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=json.dumps(body.credential.get("response", {}).get("transports") or []),
        name=(body.name or "").strip()[:60] or "Passkey",
    )
    db.add(passkey)
    await activity_log(db, "passkey", f"Passkey ajoutée : « {passkey.name} »", user=user, ip=get_client_ip(request))
    await db.commit()
    await db.refresh(passkey)
    return _out(passkey)


@router.delete("/{passkey_id}")
async def delete_passkey(passkey_id: int, request: Request,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    passkey = (await db.execute(select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id))).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=404, detail="Passkey introuvable")
    await db.delete(passkey)
    await activity_log(db, "passkey", f"Passkey supprimée : « {passkey.name} »", user=user, ip=get_client_ip(request))
    await db.commit()
    return {"ok": True}


# ── Connexion (public) ───────────────────────────────────────────────────────────────


@router.post("/login/options")
async def login_options(request: Request):
    _login_rate_limiter.check(get_client_ip(request) or "unknown")
    rp_id, _ = _rp()
    challenge_id, challenge = pk.new_challenge(None)
    # Pas de liste d'identifiants autorisés : l'appareil propose les passkeys qu'il connaît
    # pour ce domaine (passkeys découvrables), sans saisie d'identifiant.
    options = generate_authentication_options(
        rp_id=rp_id, challenge=challenge, user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {"challenge_id": challenge_id, "options": json.loads(options_to_json(options))}


@router.post("/login/verify")
async def login_verify(body: LoginVerifyIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip = get_client_ip(request)
    _login_rate_limiter.check(ip or "unknown")
    rp_id, origin = _rp()
    challenge = pk.take_challenge(body.challenge_id, None)
    passkey = (await db.execute(
        select(Passkey).where(Passkey.credential_id == str(body.credential.get("id", "")))
    )).scalar_one_or_none()
    user = await db.get(User, passkey.user_id) if passkey else None
    ok = False
    if challenge is not None and passkey is not None and user is not None:
        try:
            verified = verify_authentication_response(
                credential=body.credential, expected_challenge=challenge, expected_rp_id=rp_id,
                expected_origin=origin, credential_public_key=passkey.public_key,
                credential_current_sign_count=passkey.sign_count, require_user_verification=True,
            )
            ok = True
        except InvalidAuthenticationResponse:
            ok = False
    if not ok:
        await activity_log(db, "login", "Échec de connexion par passkey", status="error", ip=ip)
        await db.commit()
        raise HTTPException(status_code=401, detail="Connexion par passkey refusée")

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    secret_key = await auth_service.get_secret_key(db)
    token = auth_service.create_session_token(user.id, user.token_version, secret_key)
    response.set_cookie(auth_service.SESSION_COOKIE_NAME, token, **_cookie_kwargs(request))
    await activity_log(db, "login", f"Connexion par passkey : utilisateur « {user.username} »", status="ok", user=user, ip=ip)
    await db.commit()
    return await _status(db, user)
