"""Parsing des pages Bedetheque.com sur des copies de pages réelles (tests/fixtures/bedetheque/,
enregistrées depuis un navigateur après la refonte d'octobre 2026). Si Bedetheque change encore
sa structure, ces tests ne le verront pas : il faudra réenregistrer les pages. Mais ils
garantissent que le parseur lit bien la structure connue, au lieu de renvoyer « 0 album »."""
import asyncio
import json
from pathlib import Path

import httpx

from backend.services import http_client
from backend.services import scraper_bedetheque as bd

FIXTURES = Path(__file__).parent / "fixtures" / "bedetheque"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_page_serie_tous_les_albums():
    albums = bd._parse_series_page(_html("serie.html"))
    assert len(albums) == 16
    assert [a["number"] for a in albums][-6:] == ["FL1", "FL2", "HS1", "HS2", "HS3", "INT"]

    t1 = albums[0]
    assert t1["number"] == "1" and t1["title"] == "Journal Infime"
    assert t1["url"] == "https://www.bedetheque.com/BD-Lou-Tome-1-Journal-Infime-37024.html"
    assert t1["writer"] == t1["penciller"] == "Julien Neel"  # « Neel, Julien » remis en ordre
    assert t1["authors"] == ["Julien Neel"]
    assert t1["publisher"] == "Glénat"
    assert t1["year"] == "2004"
    assert t1["isbn"] == "2723442756"
    assert (t1["rating"], t1["rating_count"]) == (4.3, 125)
    assert t1["cover_url"] == "https://www.bedetheque.com/cache/thb_couv/louglenatcouv01.jpg"


def test_page_serie_album_sans_note():
    albums = bd._parse_series_page(_html("serie.html"))
    petit_monde = next(a for a in albums if a["title"].startswith("Le petit monde de Lou"))
    assert petit_monde["rating"] is None and petit_monde["rating_count"] is None
    assert petit_monde["year"] == "2019"


def test_page_serie_infos():
    info = bd._parse_series_info(_html("serie.html"))
    assert info["status"] == "Série finie"
    assert info["genre"] == "Jeunesse"
    assert info["resume"].startswith("Lou est une petite fille")
    assert "Lire la suite" not in info["resume"]


def test_resume_album():
    resume = bd._parse_album_summary(_html("album.html"))
    assert resume.startswith("Lou est une petite fille")
    assert "<" not in resume


def test_index_alphabetique(monkeypatch):
    monkeypatch.setattr(http_client.BEDETHEQUE, "transport",
                        httpx.MockTransport(lambda req: httpx.Response(200, text=_html("index_B.html"))))
    monkeypatch.setattr(http_client.BEDETHEQUE, "min_interval", 0)
    path = bd._index_path()
    before = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        assert asyncio.run(bd.build_index(["B"])) >= 4
        index = json.loads(path.read_text(encoding="utf-8"))
        assert index["B-BoY BomB"] == "https://www.bedetheque.com/serie-35356-BD-B-BoY-BomB.html"
        assert index["B comme bricoleur"] == "https://www.bedetheque.com/serie-18407-BD-B-comme-bricoleur.html"
    finally:
        if before is None:
            path.unlink()
        else:
            path.write_text(before, encoding="utf-8")


def test_completion_globale_import(client, monkeypatch):
    """Endpoint de complétion globale de l'import : année et fiche album renvoyées."""
    monkeypatch.setattr(http_client.BEDETHEQUE, "transport",
                        httpx.MockTransport(lambda req: httpx.Response(200, text=_html("serie.html"))))
    monkeypatch.setattr(http_client.BEDETHEQUE, "min_interval", 0)
    r = client.post("/api/scrape/bedetheque-bulk", json={"url": "https://www.bedetheque.com/serie-9623-BD-Lou.html"})
    assert r.status_code == 200, r.text
    t1 = r.json()[0]
    assert t1["number"] == "1" and t1["year"] == "2004"
    assert t1["url"] == "https://www.bedetheque.com/BD-Lou-Tome-1-Journal-Infime-37024.html"
