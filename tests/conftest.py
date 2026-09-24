"""Base commune des tests backend.

Les chemins de l'app (média, base, cache) sont redirigés vers un dossier temporaire AVANT
tout import de `backend` : config.settings est lu une seule fois, à l'import.
"""
import atexit
import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="cbz-tests-"))
atexit.register(shutil.rmtree, _ROOT, ignore_errors=True)
MEDIA = _ROOT / "media"
DATA = _ROOT / "data"
MEDIA.mkdir()
DATA.mkdir()
os.environ.update(
    MEDIA_ROOT=str(MEDIA),
    LIBRARY_SUBDIR="",
    DB_PATH=str(DATA / "cbzmanager.db"),
    COVER_CACHE_DIR=str(DATA / "covers"),
    DEV_MODE="false",
)

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

ADMIN_PASSWORD = "motdepasse-de-test"


def page_bytes(color=(200, 30, 30), size=(60, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def make_cbz(path: Path, pages: int = 3, comicinfo: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(pages):
            zf.writestr(f"page{i + 1:03d}.jpg", page_bytes((40 * i % 255, 80, 120)))
        if comicinfo is not None:
            zf.writestr("ComicInfo.xml", comicinfo)
    return path


def make_pdf(path: Path, pages: int = 2) -> Path:
    import fitz  # PyMuPDF

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=200, height=300)
        page.insert_image(page.rect, stream=page_bytes())
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="session")
def library() -> Path:
    """Petite bibliothèque de test, une série par dossier (convention du scanner)."""
    make_cbz(MEDIA / "Akira" / "Akira - T01 - Akira.cbz")
    make_cbz(MEDIA / "Akira" / "Akira - T02 - Tetsuo.cbz", pages=4)
    make_cbz(
        MEDIA / "Blacksad" / "Blacksad - T03 - Âme rouge.cbz",
        comicinfo=(
            '<?xml version="1.0" encoding="utf-8"?><ComicInfo>'
            "<Series>Blacksad</Series><Number>3</Number><Title>Âme rouge</Title>"
            "<Writer>Juan Díaz Canales</Writer><Penciller>Juanjo Guarnido</Penciller>"
            "<Publisher>Dargaud</Publisher><Year>2005</Year></ComicInfo>"
        ),
    )
    make_cbz(MEDIA / "Horimiya" / "Horimiya - T10.cbz")
    make_pdf(MEDIA / "One shot" / "Leave them alone.pdf")
    return MEDIA


@pytest.fixture(scope="session")
def client(library):
    """Client HTTP sur l'app complète (lifespan compris), connecté en admin, mot de passe
    provisoire admin/admin déjà changé."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200, r.text
        assert r.json()["must_change_password"] is True
        r = c.put("/api/auth/credentials", json={"current_password": "admin", "new_password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture(scope="session")
def scanned(client):
    """Scan complet de la bibliothèque de test. Avec TestClient, la tâche de fond du scan
    s'exécute avant que la réponse ne soit rendue : le scan est terminé au retour."""
    job_id = client.post("/api/scan").json()["job_id"]
    status = client.get(f"/api/scan/{job_id}").json()
    assert status["status"] == "done", status
    return client
