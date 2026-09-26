"""Client HTTP commun des services tiers (services/http_client.py) et ses effets sur les
scrapers : rythme, reprises, erreurs typées — et le bug corrigé du scan des albums manquants
(une panne passagère de Bedetheque ne doit plus rien casser sur une série)."""
import asyncio
import os
import sqlite3
import time

import httpx
import pytest

from backend.services import http_client
from backend.services.http_client import ServiceError, ThrottledClient


def _client(handler, **kw):
    kw.setdefault("min_interval", 0)
    kw.setdefault("backoff", 0.01)
    return ThrottledClient("Test", transport=httpx.MockTransport(handler), **kw)


def _run(coro):
    return asyncio.run(coro)


def test_succes_et_user_agent():
    seen = {}

    def handler(req):
        seen["ua"] = req.headers["user-agent"]
        return httpx.Response(200, text="ok")

    resp = _run(_client(handler).get("https://exemple.test/"))
    assert resp.text == "ok"
    assert seen["ua"].startswith(f"CBZManager/{http_client.APP_VERSION} ")
    assert seen["ua"].isascii()


def test_reprise_apres_503():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503 if len(calls) < 2 else 200, text="ok")

    assert _run(_client(handler).get("https://exemple.test/")).status_code == 200
    assert len(calls) == 2


def test_introuvable_sans_reprise():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(ServiceError) as e:
        _run(_client(handler).get("https://exemple.test/"))
    assert e.value.kind == "not_found" and len(calls) == 1


def test_cle_refusee():
    with pytest.raises(ServiceError) as e:
        _run(_client(lambda req: httpx.Response(401)).get("https://exemple.test/"))
    assert e.value.kind == "unauthorized"
    assert "clé API" in e.value.message


def test_quota_apres_reprises_et_retry_after():
    calls = []

    def handler(req):
        calls.append(time.monotonic())
        return httpx.Response(429, headers={"Retry-After": "0"})

    with pytest.raises(ServiceError) as e:
        _run(_client(handler, max_attempts=3).get("https://exemple.test/"))
    assert e.value.kind == "quota" and len(calls) == 3


def test_erreur_reseau():
    def handler(req):
        raise httpx.ConnectError("injoignable")

    with pytest.raises(ServiceError) as e:
        _run(_client(handler, max_attempts=2).get("https://exemple.test/"))
    assert e.value.kind == "unavailable"
    assert "ne répond pas" in e.value.message


def test_rythme_entre_requetes_meme_concurrentes():
    stamps = []

    def handler(req):
        stamps.append(time.monotonic())
        return httpx.Response(200)

    c = _client(handler, min_interval=0.15)

    async def both():
        await asyncio.gather(c.get("https://exemple.test/a"), c.get("https://exemple.test/b"))

    _run(both())
    assert len(stamps) == 2 and stamps[1] - stamps[0] >= 0.14


# ── Effets sur l'app ─────────────────────────────────────────────────────────────────


@pytest.fixture
def bedetheque(monkeypatch):
    """Remplace le réseau de Bedetheque.com par une réponse choisie par le test."""
    state = {"status": 503}
    monkeypatch.setattr(http_client.BEDETHEQUE, "transport",
                        httpx.MockTransport(lambda req: httpx.Response(state["status"], text="<html></html>")))
    monkeypatch.setattr(http_client.BEDETHEQUE, "min_interval", 0)
    monkeypatch.setattr(http_client.BEDETHEQUE, "backoff", 0.01)
    return state


def _db(sql, *args):
    con = sqlite3.connect(os.environ["DB_PATH"])
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.fetchall()
    finally:
        con.close()


URL = "https://www.bedetheque.com/serie-59-BD-Blacksad.html"


def test_panne_bedetheque_ne_casse_pas_la_serie(scanned, bedetheque):
    sid = next(s["id"] for s in scanned.get("/api/series").json() if s["name"] == "Blacksad")
    # URL saisie à la main (confirmée), pendant que Bedetheque est en panne.
    r = scanned.put(f"/api/missing-albums/series/{sid}/bedetheque-url", json={"url": URL})
    assert r.status_code == 200, r.text
    assert r.json()["bedetheque_match_status"] == "found"
    _db("insert into missing_albums (series_id, number, title, detected_at) values (?, '4', 'Âme rouge', '2026-01-01')", sid)

    # Revérification pendant la panne : rien ne doit changer (avant : URL marquée introuvable).
    assert scanned.post(f"/api/missing-albums/series/{sid}/recheck").status_code == 200
    assert _db("select bedetheque_url, bedetheque_match_status from series where id = ?", sid) == [(URL, "found")]
    assert _db("select count(*) from missing_albums where series_id = ?", sid) == [(1,)]

    # Page réellement introuvable (404) : là, la série est bien marquée introuvable.
    bedetheque["status"] = 404
    scanned.post(f"/api/missing-albums/series/{sid}/recheck")
    assert _db("select bedetheque_match_status from series where id = ?", sid) == [("not_found",)]


def test_panne_bedetheque_message_clair_pour_completer(scanned, bedetheque):
    sid = next(s["id"] for s in scanned.get("/api/series").json() if s["name"] == "Blacksad")
    _db("update series set bedetheque_url = ?, bedetheque_match_status = 'found' where id = ?", URL, sid)
    r = scanned.get(f"/api/series/{sid}/enrich-preview")
    assert r.status_code == 503
    assert "Bedetheque.com ne répond pas" in r.json()["detail"]


def test_google_books_quota_message_clair(scanned, monkeypatch):
    monkeypatch.setattr(http_client.GOOGLE_BOOKS, "transport", httpx.MockTransport(lambda req: httpx.Response(429)))
    monkeypatch.setattr(http_client.GOOGLE_BOOKS, "min_interval", 0)
    monkeypatch.setattr(http_client.GOOGLE_BOOKS, "backoff", 0.01)
    r = scanned.post("/api/scrape/googlebooks", json={"query": "Blacksad"})
    assert r.status_code == 503
    assert "limite de requêtes" in r.json()["detail"]
