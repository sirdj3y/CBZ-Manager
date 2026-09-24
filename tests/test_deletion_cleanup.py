"""Supprimer un album ou un compte doit supprimer tout ce qui s'y rattache.

SQLite n'applique pas les ON DELETE CASCADE ici (pas de PRAGMA foreign_keys=ON) : seules
les cascades déclarées sur les relations ORM nettoient. Une ligne oubliée est pire qu'un
simple déchet — SQLite réutilise les id libérés, et la ligne orpheline se rattache alors
silencieusement au prochain album ou compte créé (bug déjà vu avec la progression de lecture).
"""
import os
import sqlite3

from fastapi.testclient import TestClient

from conftest import MEDIA, make_cbz

PASSWORD = "autre-mot-de-passe"


def _count(sql, *args):
    con = sqlite3.connect(os.environ["DB_PATH"])
    try:
        return con.execute(sql, args).fetchone()[0]
    finally:
        con.close()


def test_supprimer_un_album_supprime_son_temps_de_lecture(scanned):
    make_cbz(MEDIA / "A supprimer" / "A supprimer - T01 - Adieu.cbz")
    scanned.post("/api/scan")
    sid = next(s["id"] for s in scanned.get("/api/series").json() if s["name"] == "A supprimer")
    tome_id = scanned.get(f"/api/series/{sid}").json()["tomes"][0]["id"]

    assert scanned.post(f"/api/reader/{tome_id}/heartbeat", json={"seconds": 30}).status_code == 200
    assert _count("select count(*) from reading_activity where tome_id = ?", tome_id) == 1

    assert scanned.delete(f"/api/tomes/{tome_id}/file").status_code == 200
    assert _count("select count(*) from tomes where id = ?", tome_id) == 0
    assert _count("select count(*) from reading_activity where tome_id = ?", tome_id) == 0


def test_supprimer_un_compte_supprime_ses_donnees(scanned):
    r = scanned.post("/api/users", json={"username": "invite", "is_admin": True, "password": PASSWORD})
    assert r.status_code == 200, r.text
    user_id = _count("select id from users where username = 'invite'")

    invite = TestClient(scanned.app)
    assert invite.post("/api/auth/login", json={"username": "invite", "password": PASSWORD}).status_code == 200
    invite.put("/api/auth/credentials", json={"current_password": PASSWORD, "new_password": PASSWORD + "-2"})
    tome_id = scanned.get("/api/tomes").json()[0]["id"]
    assert invite.post(f"/api/reader/{tome_id}/heartbeat", json={"seconds": 30}).status_code == 200
    r = invite.post("/api/smart-lists", json={"name": "Mes mangas", "rules": {"groups": [{"conditions": [
        {"source": "series", "field": "classification", "operator": "is", "value": "Manga"}]}]}})
    assert r.status_code == 200, r.text

    assert scanned.delete(f"/api/users/{user_id}").status_code == 200
    assert _count("select count(*) from users where id = ?", user_id) == 0
    assert _count("select count(*) from reading_activity where user_id = ?", user_id) == 0
    assert _count("select count(*) from smart_lists where owner_id = ?", user_id) == 0


def test_diagnostic_detecte_et_nettoie_les_orphelins(scanned):
    """Données laissées par les anciennes versions (avant les cascades) : le Diagnostic les
    signale par type, et « Nettoyer » ne supprime que les lignes orphelines."""
    tome_id = scanned.get("/api/tomes").json()[0]["id"]
    admin_id = _count("select id from users where username = 'admin'")
    con = sqlite3.connect(os.environ["DB_PATH"])
    con.execute("insert into reading_activity (user_id, tome_id, day, seconds, updated_at) values (?, 99999, '2026-01-01', 60, '2026-01-01 00:00:00')", (admin_id,))
    con.execute("insert into reading_activity (user_id, tome_id, day, seconds, updated_at) values (?, ?, '2026-01-02', 60, '2026-01-02 00:00:00')", (admin_id, tome_id))
    con.execute("insert into smart_lists (owner_id, name, shared, rules, is_default, sort_order, result_type, created_at, updated_at) values (88888, 'Fantôme', 0, '{}', 0, 0, 'tome', '2026-01-01', '2026-01-01')")
    con.commit()
    con.close()

    issues = [i for i in scanned.get("/api/health-check").json()["issues"] if i["type"] == "orphaned_data"]
    by_key = {i["orphan_key"]: i for i in issues}
    assert set(by_key) == {"reading_activity_tome", "smart_lists_user"}
    assert "99999" in by_key["reading_activity_tome"]["detail"]

    r = scanned.delete("/api/health-check/orphaned-data/reading_activity_tome")
    assert r.json() == {"deleted": 1}
    assert scanned.delete("/api/health-check/orphaned-data/smart_lists_user").json() == {"deleted": 1}
    assert scanned.delete("/api/health-check/orphaned-data/n_importe_quoi").status_code == 404

    assert not [i for i in scanned.get("/api/health-check").json()["issues"] if i["type"] == "orphaned_data"]
    # La ligne valide (album existant) est intacte
    assert _count("select count(*) from reading_activity where tome_id = ?", tome_id) >= 1
