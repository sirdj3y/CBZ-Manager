import runpy
import sqlite3
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parents[1] / "backend" / "db_backup.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "cbzmanager.db"
    con = sqlite3.connect(db)
    con.execute("create table series (name text)")
    con.execute("insert into series values ('Akira')")
    con.commit()
    con.close()
    version = tmp_path / "VERSION"
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("APP_VERSION_FILE", str(version))

    def start(v):
        version.write_text(v + "\n")
        runpy.run_path(SCRIPT, run_name="__main__")

    return tmp_path, start


def _backups(tmp_path):
    return sorted(p.name for p in (tmp_path / "backups").glob("*.db")) if (tmp_path / "backups").exists() else []


def test_sauvegarde_au_changement_de_version_seulement(env):
    tmp_path, start = env
    start("1.24.0")
    assert len(_backups(tmp_path)) == 1 and _backups(tmp_path)[0].startswith("cbzmanager-vavant-1.24.0-")
    start("1.24.0")  # simple redémarrage
    assert len(_backups(tmp_path)) == 1
    start("1.25.0")
    assert any(n.startswith("cbzmanager-v1.24.0-") for n in _backups(tmp_path))
    assert (tmp_path / ".last_version").read_text() == "1.25.0"


def test_sauvegarde_lisible_et_complete(env):
    tmp_path, start = env
    start("1.0.0")
    backup = tmp_path / "backups" / _backups(tmp_path)[0]
    con = sqlite3.connect(backup)
    assert con.execute("pragma integrity_check").fetchone() == ("ok",)
    assert con.execute("select name from series").fetchall() == [("Akira",)]


def test_rotation_garde_les_5_dernieres(env, monkeypatch):
    tmp_path, start = env
    import os
    for i in range(8):
        start(f"1.{i}.0")
        # mtime distincts sans attendre : la rotation trie sur la date de modification
        for j, p in enumerate(sorted((tmp_path / "backups").glob("*.db"))):
            os.utime(p, (1_000_000 + j, 1_000_000 + j))
    assert len(_backups(tmp_path)) == 5


def test_premier_demarrage_sans_base(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "absente.db"))
    (tmp_path / "VERSION").write_text("1.0.0")
    monkeypatch.setenv("APP_VERSION_FILE", str(tmp_path / "VERSION"))
    runpy.run_path(SCRIPT, run_name="__main__")
    assert not (tmp_path / "backups").exists()
    assert (tmp_path / ".last_version").read_text() == "1.0.0"


def test_un_echec_ne_bloque_pas_le_demarrage(env, capsys):
    tmp_path, start = env
    (tmp_path / "backups").write_text("un fichier à la place du dossier")
    start("2.0.0")  # ne lève pas
    assert "ÉCHEC" in capsys.readouterr().err
