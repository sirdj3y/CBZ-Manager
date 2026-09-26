# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (from `frontend/`)
```bash
npm run dev      # Dev server on :5173 with HMR
npm run build    # Production build → outputs to ../backend/static/
npm run preview  # Preview production build
```

### Backend (from repo root)
```bash
DEV_MODE=true .venv/bin/uvicorn backend.main:app --reload --port 8000
```
In DEV_MODE: CORS is enabled for `localhost:5173`, Swagger UI is available at `/api/docs`, and SQLAlchemy logs queries.

### Tests
```bash
.venv/bin/python -m pytest          # backend — from repo root (tests/, pytest.ini)
cd frontend && npm test             # frontend — vitest (frontend/tests/)
```
CI runs both before every image build (`.github/workflows/docker.yml`, job `tests`, Python 3.11 like the image, Node 22); a failure blocks publication, so nothing untested reaches preprod or prod. **Every fix or feature adds or extends a test** — a regression test for a bug fix (see the `Achille Talon` case in `tests/test_filename_parser.py`, `13.5`/`7bis` in `frontend/tests/renamePattern.test.js`). `tests/conftest.py` points MEDIA_ROOT/DB_PATH/COVER_CACHE_DIR at a temp dir *before* importing `backend` (settings are read at import), generates real CBZ/PDF files, and gives a `client` fixture (full app with lifespan, logged-in admin) and a `scanned` one (library already scanned — TestClient runs the scan's background task before returning).

### Docker (production — Synology DS423+)
Images are built by GitHub Actions (`.github/workflows/docker.yml`, linux/amd64 — DS423+ is Intel x86_64) and published to GHCR — no more local `buildx` + `docker save` to `.tar.gz`:
- push to `main` → `ghcr.io/sirdj3y/cbz-manager:latest` + `:<VERSION>` → **production**, pulled automatically by Watchtower on the NAS within ~5 min
- push to `develop` → `:preprod` → **preprod** container on the NAS (port 5174, own empty data, dedicated test library `/volume1/divers/BD-preprod`, read-write)
- other branches / PRs → build only (checks the Dockerfile), nothing published
- `*.md`, `design-tests/`, `docker-compose*.yml` changes don't trigger a build

NAS projects (Container Manager → Projet): `/volume1/docker/cbz-manager` (`docker-compose.synology.yml`, includes Watchtower) and `/volume1/docker/cbz-manager-preprod` (`docker-compose.preprod.synology.yml`). The NAS pulls GHCR with `sudo docker login ghcr.io` credentials (`/root/.docker/config.json`, classic token `read:packages`) — Container Manager's Registre tab can't talk to ghcr.io, that's expected.

Local Docker (`docker-compose.yml`, arm64 on the Mac) is still fine for quick checks: `docker compose build && docker compose up -d --force-recreate`.

The Dockerfile is a two-stage build: Node 20 builds the frontend, then Python 3.11-slim runs the backend. The frontend build outputs directly to `backend/static/` (configured in `vite.config.js`). `unrar` (non-free, from Debian bookworm non-free) is installed for RAR5/CBR support — `unrar-free` is not sufficient.

Docker volumes to map on Synology (or any deployment):
- `/media` ← comics folder (read-only ok)
- `/data` ← database + cover cache (read-write required)

Both are bind mounts to plain host folders (`docker-compose.yml` default: `./data:/data`), not named Docker volumes — deliberately, so the data is visible/backupable like any other folder (matches how Synology Container Manager, Portainer, Unraid etc. present volume mapping to users). Don't reintroduce a named volume for `/data`.

The container runs as a non-root user (`appuser`), not root. `docker-entrypoint.sh` runs as root at container start, adjusts `appuser`'s UID/GID from the `PUID`/`PGID` env vars (default 1000:1000, linuxserver.io convention), `chown -R`s `/data`, then `exec gosu appuser "$@"` to drop privileges before running uvicorn. When touching the Dockerfile/entrypoint, keep this drop-privileges flow intact — don't add a bare `USER` directive instead, it would hardcode one UID and break the "match your NAS user" use case.

Before the `chown`, the entrypoint runs `backend/db_backup.py` (stdlib only, never fails the start): if `VERSION` differs from `data/.last_version`, it copies the DB with SQLite's backup API to `data/backups/` (5 kept) — before `init_db()` runs its `ALTER TABLE`s. Watchtower deploys unattended, so keep this step ahead of the app start.

App listens on port `32123` internally. `docker-compose.yml` maps it to the host.

### Environment variables
Key vars (`.env` or Docker env — `LIBRARY_SUBDIR` is also configurable from the app's Settings UI):
| Variable | Default | Description |
|---|---|---|
| `MEDIA_ROOT` | `/media` | Comics folder mount point |
| `LIBRARY_SUBDIR` | — | Optional subfolder within MEDIA_ROOT |
| `DB_PATH` | `/data/cbzmanager.db` | SQLite database |
| `COVER_CACHE_DIR` | `/data/covers` | Cover cache |
| `GOOGLE_BOOKS_API_KEY` | — | Optional scraping |
| `COMICVINE_API_KEY` | — | Optional scraping |
| `DEV_MODE` | `false` | Enables CORS + Swagger at `/api/docs` |
| `PORT` | `32123` | Internal listen port |

---

## Architecture

### Data model
Library is organized as **Series → Tomes (albums)**. A series = a folder on disk; tomes = comic files within. SQLite tables: `series`, `tomes`, `metadata` (ComicInfo.xml fields, 1:1 with tome), `reading_progress`, `convert_jobs`, `convert_job_tomes`, `activity_log`, `scan_jobs`.

`backend/models/db_models.py` — all ORM models  
`backend/database.py` — async SQLAlchemy engine (WAL mode), `get_db()` dependency, manual `ALTER TABLE` migrations at startup

### Backend structure (`backend/`)
- `main.py` — FastAPI app wiring: lifespan, CORS, routers, SPA fallback (`/{full_path:path}` serves `backend/static/index.html`)
- `config.py` — Pydantic Settings, env-loaded, cached via `@lru_cache`
- `routers/library.py` — series CRUD, scan trigger (`/api/scan`), scan SSE stream (`/api/scan/{id}/stream`)
- `routers/tomes.py` — tome CRUD, metadata read/write
- `routers/converter.py` — conversion job management, abort
- `routers/import_router.py` — multipart file upload, triggers immediate DB insert then async conversion
- `routers/reader.py` — page-by-page image serving from zip/rar/pdf
- `services/scanner.py` — walks LIBRARY_PATH, upserts Series/Tome/Metadata into DB, extracts cover cache
- `services/converter_service.py` — CBR/PDF→CBZ conversion with quality presets (Light/Medium/HQ/Original); PDF uses native image extraction via PyMuPDF (`page.get_images()`) to avoid double JPEG compression; in-memory `_progress` dict for real-time conversion progress
- `services/cover_cache.py` — extracts first image from comic file, writes to `COVER_CACHE_DIR/{tome_id}.jpg`
- `services/metadata_writer.py` — writes/updates `ComicInfo.xml` inside a CBZ

### Frontend structure (`frontend/src/`)
- **Stores (Pinia):** `library.js` is the main store — holds all series, scan progress via SSE, filters, author autocomplete pool (`authors` = objects with counts; `authorNames` computed = flat string arrays for autocomplete). `tomes.js` holds all tomes flat. `reader.js` manages reading state.
- **API layer** (`api/`): thin wrappers over axios. `api/client.js` is the base axios instance. All API calls go through here.
- **Views** (`views/`): one Vue SFC per route. Main views: `HomeView`, `SeriesView`, `SeriesDetailView`, `BooksView`, `ImportView`, `AuthorsView`, `ReaderView`, `StatsView`, settings sub-views.
- **Components** (`components/`): organized by domain — `library/` (SeriesCard, CoverPickerModal), `metadata/` (MetadataForm), `converter/` (ConverterModal), `rename/` (RenameModal), `layout/` (AppLayout, Notification), `ui/` (AutocompleteInput).
- **Routing:** `vue-router` with HTML5 history. SPA fallback is handled by the backend.
- **AutocompleteInput:** multi-value comma-separated input (`components/ui/AutocompleteInput.vue`). The autocomplete pool for Writer/Penciller merges both fields (an author like Peyo who writes and draws appears in both).

### shadcn-vue components (`frontend/src/components/shadcn/`, issues #6–#12)
Adopted progressively (plan in issues #7–#12): pages keep their own CSS and identity; interactive pieces (dialogs, menus, tooltips, search, selects, sheets) become shadcn-vue components. Showcase: `/labo/shadcn` (`src/labs/shadcn/`, not in the menu).
- `shadcn.css` is loaded app-wide (`main.js`, after `style.css`): Tailwind v4 **without preflight**, a minimal reset scoped to `[data-slot]` (every shadcn element, portals included), utilities **unlayered** (the app's global `* { padding: 0; margin: 0 }` is unlayered and would beat layered utilities) and generated from all of `src/`.
- shadcn colors/radii/font map to the app's tokens in `@theme inline` — never hardcode colors; dark mode follows `data-theme` on `<html>`. App `:root` tokens (unlayered) win over Tailwind's own theme variables of the same name (`--shadow-lg`, `--radius-sm`…), so `shadow-lg` etc. already use the app's values.
- A file that imports from `@/components/shadcn` may use Tailwind utilities; other files must not. `frontend/tests/tailwindCollisions.test.js` fails if an app CSS class, or a template class in a non-shadcn file, is also a Tailwind utility.
- z-index scale (edited in the copied components): dialogs/sheets `z-[500]` (same level as the app's own modals), menus/popovers/selects/tooltips `z-[1000]`, `AutocompleteInput`'s suggestion list 1100 (it's used inside popovers and modals).
- A portalled component's **root** (`PopoverContent`, `DropdownMenuContent`…) doesn't get the parent's scoped-CSS attribute: style it with utilities, or make it transparent (`w-auto border-0 bg-transparent p-0 shadow-none`) and put the styled panel in an inner `<div>` written in the page (see `ContentToolbar.vue`). Elements written in the page's template inside the slot do get scoped styles.
- Window-level key handlers must ignore keys typed inside a shadcn layer (`if (e.target?.closest?.('[data-slot$="-content"]')) return`): Reka closes the menu/dialog on Escape *before* the window listener runs, so without the guard Escape also clears the selection or leaves the reader (see `ReaderView.vue::onKey`, `onSelectionEscape` in the grid views). An `<a>` used as a menu item gets the global link style (vermilion, underline on hover) — neutralise it (`text-foreground no-underline hover:no-underline`).
- **Modals:** wrap the modal's own box in `<AppDialog title="…" @close="…">` (`components/ui/AppDialog.vue`) instead of a hand-made `Teleport` + backdrop + Escape handler. It keeps the box's scoped CSS, lays the dialog out without `transform` (so `position: fixed` children still refer to the viewport), lets clicks next to the box close it, ignores clicks in `.autocomplete-list` and in shadcn layers opened from the modal, focuses `[autofocus]`. Props: `dismissible=false` (nothing closes it, e.g. during a conversion), `close-on-outside-click=false` (long forms). A Dialog blocks pointer events and focus everywhere else: anything a modal renders in `<body>` must be a shadcn layer or be listed in `onInteractOutside` (and have `pointer-events: auto`). Migration in progress (issue #11).
- **Tooltips:** an icon-only button gets `<Hint label="…">` (`components/ui/Hint.vue`, one global `TooltipProvider` in `App.vue`), not `title="…"` — it also sets the button's `aria-label`. Directives (`v-if`, `v-for`, `:key`) go on `<Hint>`, whose content must be a single element. **Never combine `Hint` with a menu/popover trigger** (in either order): Reka can't anchor a Tooltip and a DropdownMenu/Popover on the same button — with the Tooltip outside, the menu registers its anchor with the Tooltip's popper and stays off-screen (`translate(0,-200%)`); inside, the trigger's events and ref don't reach the button. Such buttons use plain `title` + `aria-label`. Buttons with visible text keep a plain `title` when it only adds detail. Hover previews with rich content (quality comparison) use `HoverCard`.
- Add components with `npx shadcn-vue@latest add <name>` (`frontend/components.json`, JS, alias `@` → `src`). The copied code is ours to adapt (e.g. `GlobalSearchModal.vue` uses Reka's `ListboxFilter` with its own filtering instead of `CommandInput`, whose built-in filter needs every item rendered).

### File naming convention (scanner)
The scanner (`services/scanner.py`) parses filenames via `services/filename_parser.py`. Recommended pattern: `{Série} - T{Numéro} - {Titre}.cbz`. Examples recognized:
- `Akira - T01 - Akira.cbz` → series=Akira, number=01, title=Akira
- `Blacksad - T03 - Âme rouge.cbz` → series=Blacksad, number=3, title=Âme rouge

### Reader keyboard shortcuts
`→`/`Space` next page, `←` previous, `↑` fit width, `↓` fit height, `d` cycle mode (page → double → scroll), `f` fullscreen, `Esc` close. Zoom (1×-2.5×, via trackpad/Ctrl+wheel pinch or the toolbar slider) always applies on whichever axis `fit` currently frames (width or height) — never a no-op regardless of fit/mode.

### Key cross-cutting patterns

**Scan flow:** `library.triggerScan()` → POST `/api/scan` → receives `job_id` → opens EventSource on `/api/scan/{id}/stream` → SSE pushes `{processed, total, status}` → on `done`, re-fetches series.

**Conversion flow:** Upload file (multipart) → backend inserts tome in DB immediately, returns `tome_id` → frontend polls `/api/convert/{job_id}` every second → progress comes from `_progress` in-memory store (not DB). Jobs are purged from `_progress` after 5 minutes.

**Cover URLs:** Served at `/api/covers/{tome_id}` with `Cache-Control: no-cache` + ETag. Frontend appends `?v={cover_url_version}` to bust cache after cover changes.

**Metadata writing:** `ComicInfo.xml` is written directly into the CBZ archive. For CBR/PDF imports, a `.meta.json` sidecar is created at upload time; the converter reads it post-conversion, writes the XML, then deletes the sidecar.

**Menus and popovers:** use `DropdownMenu` (action menus — shared `SeriesActionsMenu`/`TomeActionsMenu` for card "⋯" menus) or `Popover` (small panels: sort, filters, smart-list flyout) from `@/components/shadcn`, never a hand-positioned `Teleport` + `position: fixed` + `getBoundingClientRect()`. Reka UI renders them in `<body>` and positions them, so they're never clipped by `overflow` (scroll rows, `.subbar`, `.sidebar`). Menus are `:modal="false"` (a click elsewhere closes the menu *and* acts, like before).

**Author filter OR logic:** In `BooksView.vue`, if `writer === penciller` in the active filters (polyvalent author like Peyo), the query uses OR instead of AND.

**Version:** Single source of truth is the `VERSION` file at repo root. Vite reads it at build time (`vite.config.js`) and injects `__APP_VERSION__`. Backend doesn't read it directly. When bumping version, update `VERSION`, `CHANGELOG.md`, and `frontend/package.json`.

---

## Rules — check before touching these areas

These come from real bugs; each one has bitten before.

- **New metadata field shown/editable in the UI → also add it to the Smart List catalog**, in `backend/services/smart_lists.py`: an entry in `FIELDS` *and* the name in `_METADATA_TEXT_COLUMNS` (a field in `FIELDS` but missing from that whitelist silently never filters). The frontend fetches the catalog from `GET /api/smart-lists/fields`, nothing to touch there.
- **New table pointing at `tomes`, `series` or `users` → declare the cascade on the parent's ORM relationship** (`relationship("X", cascade="all, delete-orphan")` on `Tome`/`Series`/`User` in `backend/models/db_models.py`). SQLite does **not** enforce `ondelete="CASCADE"` here (no `PRAGMA foreign_keys=ON`), and it reuses freed ids: a forgotten row silently attaches to the next album/account created (seen with reading progress, then reading time and smart lists). Add the case to `tests/test_deletion_cleanup.py`. Delete through the ORM (`db.delete(obj)`), never a bulk SQL `delete(Tome)` — it skips the cascades.
- **Writing a comic file in place → temp file with a unique name + `shutil.move`, under `get_file_lock(path)`** (`services/file_locks.py`), as `metadata_writer.py` and `converter_service.py` do. Writing straight to the source corrupted CBZs racing with the scanner.
- **Never run a full scan to get one tome's id** — call `scanner._process_file()` on that file (import used to rescan 2000+ files per upload).
- **RAR:** the image needs `unrar` (non-free), never `unrar-free` (no RAR5).
- **`backend/static/` stays in `.dockerignore`** — otherwise a stale local frontend build ships in the image.

### Synology gotchas (DS423+)

- Container user must own the files: **prod `PUID=1026`/`PGID=100`** (owner of `/volume1/divers/BD`), **preprod `PUID=1030`** (owner of `/volume1/divers/BD-preprod`, copied with another account). The app detects a mismatch and says which values to use (startup log + banner). Compose files must pass `PUID`/`PGID` through — once hardcoded to 1000, `.env` values were silently ignored.
- No `.env` on the NAS: everything is in the compose (`env_file: .env` makes project creation fail there).
- Container Manager: the **Registre** tab can't talk to ghcr.io (expected — pulls use the SSH `docker login`). A project whose container was never created fails on **Démarrer** ("no container found"): delete and recreate it with "Démarrer le projet une fois sa création terminée" ticked.

---

## Repository & deployment

**GitHub:** `https://github.com/sirdj3y/CBZ-Manager.git` (private repo)  
**Branches:** work on `develop` (→ preprod). **Pushing to `main` deploys production** — only merge `develop` into `main` when the user asks (version ritual / "mets en prod"), never push fixes straight to `main`.  
**Git identity:** `sirdj3y <241156680+sirdj3y@users.noreply.github.com>` (GitHub noreply address — keep email private)  
**`.gitignore` excludes:** `backups/`, `.venv/`, `node_modules/`, `backend/static/`, `data/`

Session logs are saved in `divers/backups/cbz-manager-session-<DATE>.html`. Old manual Docker images (before GHCR) are in `divers/Images/`.

---

## Backlog — GitHub issues

The plan lives in the open issues (`gh issue list`), not in this file nor in memory. Before starting a feature or fix, make sure an issue describes it (create or update one — check for duplicates); anything agreed but not started gets an issue too. Reference it in commits and close it with `Closes #n` in the commit that finishes it — note the issue only closes automatically once that commit reaches `main` (prod), so work merged on `develop` stays open until the next release. Label `plus tard` = accepted idea, not a priority.
