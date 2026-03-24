from . import core_compat  # must be first — fixes sys.path for core/ imports
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import health, auth, library, tomes, covers, reader, scraper, converter, settings as settings_router, stats, export, logs, import_router, health_check


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    await init_db()
    yield


app = FastAPI(
    title="CBZManager",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEV_MODE else None,
    redoc_url=None,
)

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


# SPA fallback — serve index.html for unknown non-API paths
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        # Serve static files at root (favicon.png, icons.svg, etc.)
        static_file = STATIC_DIR / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built yet"}
