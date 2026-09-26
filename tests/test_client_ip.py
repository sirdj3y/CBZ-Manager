"""IP réelle du client derrière le reverse proxy (routers/auth.py::get_client_ip)."""
import pytest
from starlette.requests import Request

from backend.routers import auth


def _req(peer, xff=None, proto=None):
    headers = []
    if xff:
        headers.append((b"x-forwarded-for", xff.encode()))
    if proto:
        headers.append((b"x-forwarded-proto", proto.encode()))
    return Request({"type": "http", "client": (peer, 5000), "headers": headers,
                    "scheme": "http", "server": ("app", 32123), "path": "/", "query_string": b""})


@pytest.fixture(autouse=True)
def docker_proxy(monkeypatch):
    monkeypatch.setattr(auth, "_TRUSTED_PROXY_NETWORKS", auth._parse_trusted_proxies("127.0.0.1,::1,172.16.0.0/12"))


def test_ip_reelle_via_le_proxy():
    assert auth.get_client_ip(_req("172.22.0.1", "88.12.34.56")) == "88.12.34.56"


def test_ip_inventee_par_le_client_ignoree():
    # Le client envoie lui-même un X-Forwarded-For ; le proxy de DSM ajoute la vraie IP à la fin.
    assert auth.get_client_ip(_req("172.22.0.1", "1.2.3.4, 88.12.34.56")) == "88.12.34.56"


def test_plusieurs_proxys_de_confiance():
    assert auth.get_client_ip(_req("172.22.0.1", "88.12.34.56, 172.22.0.5")) == "88.12.34.56"


def test_sans_proxy_de_confiance_en_tete_ignore():
    assert auth.get_client_ip(_req("192.168.1.20", "1.2.3.4")) == "192.168.1.20"


def test_sans_en_tete():
    assert auth.get_client_ip(_req("172.22.0.1")) == "172.22.0.1"


def test_cookie_https_seulement_via_proxy_de_confiance():
    assert auth._cookie_kwargs(_req("172.22.0.1", proto="https"))["secure"] is True
    assert auth._cookie_kwargs(_req("192.168.1.20", proto="https"))["secure"] is False
