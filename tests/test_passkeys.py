"""Passkeys (routers/passkeys.py) testées avec un authentificateur logiciel : de vraies
réponses WebAuthn (CBOR, signature ECDSA P-256), sans navigateur. Le parcours dans
l'interface est testé dans e2e/ avec l'authentificateur virtuel de Chromium."""
import base64
import hashlib
import json
import os
import sqlite3

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from backend.config import settings
from backend.services import passkeys as pk

RP_ID = "cbz.example.com"
ORIGIN = f"https://{RP_ID}"


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_dec(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftAuthenticator:
    def __init__(self, rp_id=RP_ID):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.rp_hash = hashlib.sha256(rp_id.encode()).digest()
        self.count = 0

    def _cose(self):
        n = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})

    def register(self, options, origin=ORIGIN):
        client_data = json.dumps({"type": "webauthn.create", "challenge": options["challenge"], "origin": origin}).encode()
        attested = bytes(16) + len(self.cred_id).to_bytes(2, "big") + self.cred_id + self._cose()
        auth_data = self.rp_hash + bytes([0x45]) + (0).to_bytes(4, "big") + attested  # UP|UV|AT
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data), "attestationObject": b64u(att), "transports": ["internal"]}}

    def assert_(self, options, origin=ORIGIN, user_handle=b""):
        self.count += 1
        client_data = json.dumps({"type": "webauthn.get", "challenge": options["challenge"], "origin": origin}).encode()
        auth_data = self.rp_hash + bytes([0x05]) + self.count.to_bytes(4, "big")  # UP|UV
        sig = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data), "authenticatorData": b64u(auth_data),
                             "signature": b64u(sig), "userHandle": b64u(user_handle)}}


@pytest.fixture(autouse=True)
def reset_login_limiter():
    """Les tests enchaînent plus de connexions que la limite (10/min par IP) : compteur remis
    à zéro avant chacun, la limite elle-même reste active."""
    from backend.routers import auth
    auth._login_rate_limiter._buckets.clear()
    yield
    auth._login_rate_limiter._buckets.clear()


@pytest.fixture
def public_url(monkeypatch):
    monkeypatch.setattr(settings, "APP_PUBLIC_URL", ORIGIN)


def _register(client, auth, name="iPhone"):
    r = client.post("/api/auth/passkeys/register/options")
    assert r.status_code == 200, r.text
    opts = r.json()
    assert opts["options"]["rp"]["id"] == RP_ID
    r = client.post("/api/auth/passkeys/register/verify",
                    json={"challenge_id": opts["challenge_id"], "name": name, "credential": auth.register(opts["options"])})
    assert r.status_code == 200, r.text
    return r.json()


def _login(app, auth, origin=ORIGIN, replay=False):
    anon = TestClient(app)
    opts = anon.post("/api/auth/passkeys/login/options").json()
    r = anon.post("/api/auth/passkeys/login/verify", json={"challenge_id": opts["challenge_id"], "credential": auth.assert_(opts["options"], origin)})
    if replay:
        r = anon.post("/api/auth/passkeys/login/verify", json={"challenge_id": opts["challenge_id"], "credential": auth.assert_(opts["options"], origin)})
    return anon, r


@pytest.mark.parametrize("url, enabled", [
    ("", False), ("http://cbz.example.com", False), ("https://192.168.1.10", False),
    ("https://cbz.example.com", True), ("http://localhost:5173", True),
])
def test_statut_selon_adresse_publique(client, monkeypatch, url, enabled):
    monkeypatch.setattr(settings, "APP_PUBLIC_URL", url)
    assert client.get("/api/auth/passkeys/status").json()["enabled"] is enabled


def test_enregistrer_puis_se_connecter(client, public_url):
    auth = SoftAuthenticator()
    created = _register(client, auth)
    assert created["name"] == "iPhone"
    assert [p["name"] for p in client.get("/api/auth/passkeys").json()] == ["iPhone"]

    anon, r = _login(client.app, auth)
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "admin"
    assert anon.get("/api/auth/me").json()["authenticated"] is True
    assert client.get("/api/auth/passkeys").json()[0]["last_used_at"] is not None

    # Défi à usage unique : le rejouer est refusé.
    _, r = _login(client.app, auth, replay=True)
    assert r.status_code == 401

    # Mauvaise origine (site tiers qui relaierait la demande) : refusé.
    _, r = _login(client.app, auth, origin="https://phishing.example.net")
    assert r.status_code == 401

    # Passkey supprimée : plus de connexion possible avec elle.
    assert client.delete(f"/api/auth/passkeys/{created['id']}").status_code == 200
    _, r = _login(client.app, auth)
    assert r.status_code == 401


def test_passkey_inconnue_refusee(client, public_url):
    _, r = _login(client.app, SoftAuthenticator())
    assert r.status_code == 401


def test_desactivees_sans_adresse_publique(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_PUBLIC_URL", "")
    assert client.post("/api/auth/passkeys/register/options").status_code == 409
    assert TestClient(client.app).post("/api/auth/passkeys/login/options").status_code == 409


def test_supprimer_un_compte_supprime_ses_passkeys(client, public_url):
    client.post("/api/users", json={"username": "avecpasskey", "is_admin": True, "password": "motdepasse-1"})
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"username": "avecpasskey", "password": "motdepasse-1"})
    other.put("/api/auth/credentials", json={"current_password": "motdepasse-1", "new_password": "motdepasse-2"})
    _register(other, SoftAuthenticator(), name="Mac")
    con = sqlite3.connect(os.environ["DB_PATH"])
    uid = con.execute("select id from users where username = 'avecpasskey'").fetchone()[0]
    assert con.execute("select count(*) from passkeys where user_id = ?", (uid,)).fetchone()[0] == 1
    assert client.delete(f"/api/users/{uid}").status_code == 200
    assert con.execute("select count(*) from passkeys where user_id = ?", (uid,)).fetchone()[0] == 0
    con.close()


def test_adresse_publique_reglage(client, monkeypatch, tmp_path):
    from backend.routers import settings as settings_router
    monkeypatch.setattr(settings_router, "_env_path", lambda: tmp_path / ".env")
    monkeypatch.setattr(settings, "APP_PUBLIC_URL", "")
    r = client.put("/api/settings", json={"app_public_url": "https://cbz.example.com/"})
    assert r.status_code == 200 and r.json()["app_public_url"] == "https://cbz.example.com"
    assert client.put("/api/settings", json={"app_public_url": "cbz.example.com"}).status_code == 400
    assert client.put("/api/settings", json={"app_public_url": "https://cbz.example.com/chemin"}).status_code == 400
