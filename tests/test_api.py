"""Parcours bout en bout sur l'app FastAPI complète : authentification, scan d'une vraie
bibliothèque (fichiers générés), lecture et écriture des métadonnées."""
import zipfile

from fastapi.testclient import TestClient

from conftest import MEDIA


def test_api_fermee_sans_session(client):
    anonyme = TestClient(client.app)
    assert anonyme.get("/api/series").status_code == 401
    assert anonyme.get("/api/auth/me").json() == {"authenticated": False, "username": None, "is_admin": False,
                                                  "must_change_password": False, "permissions": [], "avatar_version": 0}


def test_mauvais_mot_de_passe(client):
    anonyme = TestClient(client.app)
    assert anonyme.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 401


def test_healthcheck(client):
    assert client.get("/api/health").status_code == 200


def test_scan_cree_une_serie_par_dossier(scanned):
    series = {s["name"]: s for s in scanned.get("/api/series").json()}
    assert set(series) == {"Akira", "Blacksad", "Horimiya", "One shot"}
    assert series["Akira"]["tome_count"] == 2
    assert "Juan Díaz Canales" in series["Blacksad"]["writers"]


def _tomes(client, name):
    sid = next(s["id"] for s in client.get("/api/series").json() if s["name"] == name)
    return {t["filename"]: t for t in client.get(f"/api/series/{sid}").json()["tomes"]}


def test_scan_lit_numeros_titres_et_formats(scanned):
    akira = _tomes(scanned, "Akira")
    t2 = akira["Akira - T02 - Tetsuo.cbz"]
    assert (t2["number"], t2["title"], t2["file_format"], t2["page_count"]) == ("2", "Tetsuo", "cbz", 4)
    assert _tomes(scanned, "Horimiya")["Horimiya - T10.cbz"]["number"] == "10"
    pdf = _tomes(scanned, "One shot")["Leave them alone.pdf"]
    assert pdf["file_format"] == "pdf"


def test_scan_lit_comicinfo(scanned):
    tome = _tomes(scanned, "Blacksad")["Blacksad - T03 - Âme rouge.cbz"]
    assert tome["has_metadata"] is True
    meta = scanned.get(f"/api/tomes/{tome['id']}/metadata").json()
    assert (meta["Writer"], meta["Publisher"], meta["Year"]) == ("Juan Díaz Canales", "Dargaud", "2005")


def test_rescan_idempotent(scanned):
    avant = sorted((s["name"], s["tome_count"]) for s in scanned.get("/api/series").json())
    job_id = scanned.post("/api/scan").json()["job_id"]
    assert scanned.get(f"/api/scan/{job_id}").json()["status"] == "done"
    assert sorted((s["name"], s["tome_count"]) for s in scanned.get("/api/series").json()) == avant


def test_edition_metadata_ecrit_dans_le_cbz(scanned):
    tome = _tomes(scanned, "Akira")["Akira - T01 - Akira.cbz"]
    r = scanned.put(f"/api/tomes/{tome['id']}/metadata", json={"Series": "Akira", "Writer": "Katsuhiro Ōtomo"})
    assert r.status_code == 200, r.text
    assert scanned.get(f"/api/tomes/{tome['id']}/metadata").json()["Writer"] == "Katsuhiro Ōtomo"
    with zipfile.ZipFile(MEDIA / "Akira" / "Akira - T01 - Akira.cbz") as zf:
        assert "Katsuhiro Ōtomo" in zf.read("ComicInfo.xml").decode()


def test_edition_metadata_refusee_sur_pdf(scanned):
    pdf = _tomes(scanned, "One shot")["Leave them alone.pdf"]
    assert scanned.put(f"/api/tomes/{pdf['id']}/metadata", json={"Title": "x"}).status_code == 400
