"""Dossiers exclus du scan (Paramètres › Bibliothèque) et dossiers système toujours ignorés."""
import shutil

import pytest

from backend.config import settings
from backend.routers import settings as settings_router
from conftest import MEDIA, make_cbz


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    # Les réglages s'écrivent dans /data/.env (ou ./.env hors Docker) : jamais pendant les tests.
    monkeypatch.setattr(settings_router, "_env_path", lambda: tmp_path / ".env")
    monkeypatch.setattr(settings, "SCAN_EXCLUDED_FOLDERS", "[]")


def _series(client):
    job = client.post("/api/scan").json()["job_id"]
    assert client.get(f"/api/scan/{job}").json()["status"] == "done"
    return {s["name"] for s in client.get("/api/series").json()}


def test_dossiers_systeme_et_caches_jamais_scannes(scanned, isolated_settings):
    extra = [MEDIA / "#recycle", MEDIA / "@eaDir", MEDIA / ".cache"]
    try:
        make_cbz(MEDIA / "#recycle" / "Supprimee" / "Supprimee - T01.cbz")
        make_cbz(MEDIA / "@eaDir" / "Miniatures" / "Miniatures - T01.cbz")
        make_cbz(MEDIA / ".cache" / "Cachee - T01.cbz")
        names = _series(scanned)
        assert not names & {"Supprimee", "Miniatures", ".cache", "Cachee"}
        assert "Akira" in names
    finally:
        for d in extra:
            shutil.rmtree(d, ignore_errors=True)


def test_exclure_puis_reinclure_un_dossier(scanned, isolated_settings):
    assert "Horimiya" in _series(scanned)

    r = scanned.put("/api/settings", json={"scan_excluded_folders": ["/Horimiya/", "Horimiya"]})
    assert r.status_code == 200, r.text
    assert r.json()["scan_excluded_folders"] == ["Horimiya"]  # nettoyé, sans doublon
    names = _series(scanned)
    assert "Horimiya" not in names and "Akira" in names
    assert (MEDIA / "Horimiya").exists(), "exclure ne touche jamais aux fichiers"

    scanned.put("/api/settings", json={"scan_excluded_folders": []})
    assert "Horimiya" in _series(scanned)


def test_exclusion_hors_bibliotheque_refusee(scanned, isolated_settings):
    r = scanned.put("/api/settings", json={"scan_excluded_folders": ["../../etc"]})
    assert r.status_code == 403


def test_recherche_de_dossier(scanned):
    extra = MEDIA / "Manga"
    try:
        (extra / "Château ambulant").mkdir(parents=True)
        (MEDIA / ".cache" / "chateau").mkdir(parents=True)
        r = scanned.get("/api/settings/browse/search", params={"q": "CHATEAU"}).json()
        paths = [f["path"] for f in r["folders"]]
        assert paths == ["Manga/Château ambulant"], "accents/casse ignorés, dossiers cachés écartés"
        r = scanned.get("/api/settings/browse/search", params={"q": "a"}).json()
        depths = [f["path"].count("/") for f in r["folders"]]
        assert depths == sorted(depths), "les moins profonds d'abord"
        assert scanned.get("/api/settings/browse/search", params={"q": " "}).json()["folders"] == []
    finally:
        shutil.rmtree(extra, ignore_errors=True)
        shutil.rmtree(MEDIA / ".cache", ignore_errors=True)
