"""Tests de bout en bout : l'app complète (backend + frontend compilé) dans un vrai navigateur.

Prérequis : frontend compilé dans backend/static (`cd frontend && npm run build`) et Chromium
pour Playwright (`python -m playwright install chromium`). Lancement : `python -m pytest e2e`.

Chaque session démarre un serveur uvicorn jetable sur une bibliothèque générée (dossiers et
base temporaires), change le mot de passe provisoire admin/admin et scanne la bibliothèque.
En cas d'échec, une capture d'écran est enregistrée dans e2e/artifacts/.
"""
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "motdepasse-e2e"
WIDTH, HEIGHT = 1400, 900
ARTIFACTS = ROOT / "e2e" / "artifacts"


def _page_bytes(i: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 180), (40 * i % 255, 90, 140)).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(path: Path, pages: int = 3):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(pages):
            zf.writestr(f"page{i:03d}.jpg", _page_bytes(i))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    if not (ROOT / "backend" / "static" / "index.html").exists():
        pytest.exit("Frontend non compilé : lancer `cd frontend && npm run build` d'abord.", 2)
    tmp = Path(tempfile.mkdtemp(prefix="cbz-e2e-"))
    media, data = tmp / "media", tmp / "data"
    for n in range(1, 5):
        _cbz(media / "Horimiya" / f"Horimiya - T{n:02d}.cbz")
    for n in range(1, 3):
        _cbz(media / "Akira" / f"Akira - T{n:02d} - Titre {n}.cbz")
    _cbz(media / "Blacksad" / "Blacksad - T01 - Quelque part entre les ombres.cbz")
    port = _free_port()
    env = {**os.environ, "MEDIA_ROOT": str(media), "LIBRARY_SUBDIR": "", "DB_PATH": str(data / "db.sqlite"),
           "COVER_CACHE_DIR": str(data / "covers"), "DEV_MODE": "false"}
    log = open(tmp / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Le serveur n'a pas démarré :\n" + (tmp / "server.log").read_text())
        with httpx.Client(base_url=base) as c:
            assert c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
            assert c.put("/api/auth/credentials", json={"current_password": "admin", "new_password": PASSWORD}).status_code == 200
            job = c.post("/api/scan").json()["job_id"]
            for _ in range(100):
                if c.get(f"/api/scan/{job}").json()["status"] in ("done", "error"):
                    break
                time.sleep(0.2)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="session")
def auth_state(server, browser, tmp_path_factory):
    ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
    page = ctx.new_page()
    page.goto(f"{server}/login")
    page.fill("input:not([type=password])", "admin")
    page.fill("input[type=password]", PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_url(lambda url: "/login" not in url)
    path = tmp_path_factory.mktemp("auth") / "state.json"
    ctx.storage_state(path=str(path))
    ctx.close()
    return str(path)


@pytest.fixture
def page(server, browser, auth_state, request):
    """Page connectée en admin. Échoue aussi sur toute erreur JavaScript non rattrapée."""
    ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, storage_state=auth_state, base_url=server)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    if request.node.rep_call.failed if hasattr(request.node, "rep_call") else False:
        ARTIFACTS.mkdir(exist_ok=True)
        pg.screenshot(path=str(ARTIFACTS / f"{request.node.name}.png"), full_page=True)
    ctx.close()
    assert not errors, f"Erreurs JavaScript : {errors}"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
