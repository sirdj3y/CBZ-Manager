"""
Passkeys (WebAuthn) : connexion sans mot de passe, en complément de celui-ci.

Une passkey est liée à un nom de domaine (le « Relying Party ID ») : celui de l'adresse
publique de l'app (réglage APP_PUBLIC_URL, ex. https://cbz.example.com). Le navigateur refuse
une passkey hors de ce domaine : via l'IP locale du NAS, seul le mot de passe fonctionne.
WebAuthn exige aussi un contexte sécurisé (HTTPS, ou http://localhost en développement).

Défis : à usage unique, valables 5 minutes, gardés en mémoire (un seul processus uvicorn,
voir Dockerfile). Un redémarrage entre la demande et la réponse fait simplement échouer la
tentative, à refaire.
"""
import secrets
import time
from urllib.parse import urlparse

from ..config import settings

CHALLENGE_TTL = 300
_challenges: dict[str, tuple[bytes, int | None, float]] = {}


class PasskeysUnavailable(Exception):
    pass


def relying_party() -> tuple[str, str]:
    """(rp_id, origin) déduits de APP_PUBLIC_URL, ou PasskeysUnavailable s'il manque ou ne
    convient pas (ni HTTPS, ni localhost ; ou une IP, que WebAuthn n'accepte pas)."""
    url = (settings.APP_PUBLIC_URL or "").strip().rstrip("/")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise PasskeysUnavailable("Adresse publique de l'app non configurée")
    if parsed.scheme != "https" and host != "localhost":
        raise PasskeysUnavailable("Les passkeys exigent une adresse publique en HTTPS")
    if host.replace(".", "").isdigit() or ":" in host:
        raise PasskeysUnavailable("Les passkeys exigent un nom de domaine, pas une adresse IP")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return host, origin


def status() -> dict:
    try:
        rp_id, origin = relying_party()
        return {"enabled": True, "origin": origin, "reason": None}
    except PasskeysUnavailable as e:
        return {"enabled": False, "origin": None, "reason": str(e)}


def new_challenge(user_id: int | None) -> tuple[str, bytes]:
    _purge()
    challenge_id = secrets.token_urlsafe(16)
    challenge = secrets.token_bytes(32)
    _challenges[challenge_id] = (challenge, user_id, time.monotonic() + CHALLENGE_TTL)
    return challenge_id, challenge


def take_challenge(challenge_id: str, user_id: int | None) -> bytes | None:
    """Renvoie le défi et le consomme (usage unique) ; None s'il est inconnu, expiré ou
    émis pour un autre compte."""
    _purge()
    entry = _challenges.pop(challenge_id or "", None)
    if entry is None:
        return None
    challenge, owner, _ = entry
    return challenge if owner == user_id else None


def _purge():
    now = time.monotonic()
    for key in [k for k, (_, _, exp) in _challenges.items() if exp < now]:
        _challenges.pop(key, None)
