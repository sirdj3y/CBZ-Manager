from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, AsyncSessionLocal
from .services.scraper_bedetheque import ensure_index_bootstrapped
from .services.storage_check import check_media_identity
from .services import auth as auth_service
from .services import smart_lists as smart_lists_service
from .services.http_client import ServiceError
from .routers import health, auth, users, profiles, library, tomes, covers, reader, scraper, converter, settings as settings_router, stats, export, logs, import_router, health_check, missing_albums, opds, opds2, notifications, smart_lists, series_hero
from .routers.health_check import cleanup_stale_scan_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    await init_db()
    ensure_index_bootstrapped()

    async with AsyncSessionLocal() as db:
        await auth_service.get_config(db)
        await auth_service.bootstrap_first_admin(db)
        await auth_service.migrate_personal_data(db)
        await auth_service.seed_default_profiles(db)
        await smart_lists_service.seed_default_smart_lists(db)
        await cleanup_stale_scan_jobs(db)

    mismatch = check_media_identity()
    if mismatch:
        print(
            f"[startup] ATTENTION : le dossier média appartient à "
            f"UID={mismatch['media_uid']}/GID={mismatch['media_gid']}, mais l'application "
            f"tourne en UID={mismatch['app_uid']}/GID={mismatch['app_gid']} — des fichiers "
            f"peuvent être illisibles. Si besoin, réglez PUID={mismatch['media_uid']} et "
            f"PGID={mismatch['media_gid']} dans votre .env, puis redémarrez.",
            flush=True,
        )
    else:
        print("[startup] Identité application OK (UID/GID correspond au dossier média, ou vérification non applicable).", flush=True)

    yield


app = FastAPI(
    title="CBZManager",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEV_MODE else None,
    redoc_url=None,
)

# Service tiers (Bedetheque.com, ComicVine, Google Books) en échec : message clair pour
# l'interface (detail, affiché tel quel par les modales) plutôt qu'une erreur 500 ou une
# liste vide trompeuse. 404 = introuvable ; le reste (panne, quota, clé refusée) = 503.
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=404 if exc.kind == "not_found" else 503, content={"detail": exc.message})


# CORS — dev only (frontend on :5173)
if settings.DEV_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# API routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(library.router)
app.include_router(tomes.router)
app.include_router(covers.router)
app.include_router(reader.router)
app.include_router(scraper.router)
app.include_router(converter.router)
app.include_router(settings_router.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(logs.router)
app.include_router(import_router.router)
app.include_router(health_check.router)
app.include_router(missing_albums.router)
app.include_router(opds.router)
app.include_router(opds2.router)
app.include_router(notifications.router)
app.include_router(smart_lists.router)
app.include_router(series_hero.router)


# SPA fallback — serve index.html for unknown non-API paths
STATIC_DIR = (Path(__file__).parent / "static").resolve()

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        # Serve static files at root (favicon.png, icons.svg, etc.)
        # Resolve + confine to STATIC_DIR to prevent path traversal (e.g. ../../etc/passwd)
        static_file = (STATIC_DIR / full_path).resolve()
        if static_file.is_relative_to(STATIC_DIR) and static_file.is_file():
            return FileResponse(str(static_file))
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built yet"}
