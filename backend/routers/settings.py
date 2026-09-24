import re
import shutil
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sql_update

from ..dependencies import require_admin, require_permission
from ..models.db_models import User
from .auth import get_client_ip
from ..models.schemas import SettingsOut, SettingsIn
from ..config import settings
from ..database import get_db
from ..services import scraper_bedetheque
from ..services import auth as auth_service

# library.settings couvre l'onglet Général (ce routeur) — /reset-db (Sauvegarde & BDD,
# destructif) exige explicitement require_admin en plus, voir plus bas.
router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_permission("library.settings"))])


def _env_path() -> Path:
    # /data is the Docker-mounted persistent volume — write there when available so
    # settings survive a container recreate/rebuild, not just a restart.
    data_dir = Path("/data")
    if data_dir.is_dir():
        return data_dir / ".env"
    return Path(".env")


def _rewrite_env(key: str, value: str) -> None:
    # value vient de champs utilisateur (rename_pattern, clés API, sous-dossier de
    # bibliothèque) : un retour à la ligne dedans permettrait d'injecter une seconde ligne
    # "AUTRE_CLE=..." dans le .env, relue avec priorité au prochain démarrage (voir
    # config.py) — donc de contourner tous les contrôles de confinement faits ici, en écrivant
    # par exemple une valeur de LIBRARY_SUBDIR jamais passée par update_settings. On refuse
    # plutôt que d'échapper : aucun de ces champs n'a de raison légitime de contenir une
    # nouvelle ligne.
    if "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail="La valeur ne peut pas contenir de retour à la ligne")
    env_path = _env_path()
    content = env_path.read_text() if env_path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    # re.sub interprète les antislashs du texte de remplacement (\1, \g<0>, etc.) — une valeur
    # utilisateur contenant un antislash suivi d'un chiffre serait donc altérée silencieusement
    # si on la passait telle quelle en second argument. lambda _: new_line renvoie la chaîne
    # littéralement, sans repasser par cette interprétation.
    new_line = f"{key}={value}"
    if pattern.search(content):
        content = pattern.sub(lambda _: new_line, content)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(content)


@router.get("/browse")
async def browse_folders(path: str = ""):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    target = (media_root / path).resolve() if path else media_root
    if not target.is_relative_to(media_root):
        raise HTTPException(status_code=403, detail="Accès refusé : chemin hors de MEDIA_ROOT")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Dossier introuvable : {path}")
    folders = sorted(
        [
            {
                "name": item.name,
                "path": str(item.relative_to(media_root)),
                "has_children": any(child.is_dir() for child in item.iterdir()),
            }
            for item in target.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ],
        key=lambda f: f["name"].lower(),
    )
    return {
        "current_path": str(target.relative_to(media_root)) if target != media_root else "",
        "parent_path": str(target.parent.relative_to(media_root)) if target != media_root else None,
        "media_root_name": media_root.name,
        "folders": folders,
    }


@router.get("/bedetheque-index")
async def bedetheque_index_status():
    return scraper_bedetheque.index_status()


@router.get("/bedetheque-index/progress")
async def bedetheque_index_progress():
    return scraper_bedetheque.get_build_progress()


@router.post("/bedetheque-index/refresh")
async def refresh_bedetheque_index(background_tasks: BackgroundTasks):
    if scraper_bedetheque.get_build_progress().get("status") == "running":
        raise HTTPException(status_code=409, detail="Un rafraîchissement est déjà en cours")
    background_tasks.add_task(scraper_bedetheque.build_index)
    return {"started": True}


@router.get("/about")
async def about():
    from ..config import settings as cfg
    cover_dir = Path(cfg.COVER_CACHE_DIR)
    cover_size = sum(f.stat().st_size for f in cover_dir.rglob("*") if f.is_file()) if cover_dir.exists() else 0
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "0.0.0"
    return {
        "version": version,
        "cover_cache_size": cover_size,
    }


@router.delete("/reset-db")
async def reset_database(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    from ..services.activity import log as activity_log
    from ..database import engine, init_db
    from .library import _scan_progress
    from ..services.converter_service import _progress as _convert_progress

    # Refuse pendant un scan/import ou une conversion en cours : ces tâches lisent/écrivent
    # la même base en tâche de fond, sans lien avec la session `db` injectée ici — les
    # supprimer sous leurs pieds produirait des écritures sur un fichier qui vient de
    # disparaître (voir SQLite: https://www.sqlite.org/howtocorrupt.html).
    scan_running = any(j.get("status") in ("pending", "running") for j in _scan_progress.values())
    convert_running = any(
        t.get("status") in ("pending", "running")
        for job in _convert_progress.values()
        for t in job.values()
    )
    if scan_running or convert_running:
        raise HTTPException(status_code=409, detail="Un scan ou une conversion est en cours — réessayez une fois terminé(e)")

    await activity_log(db, "delete_series", "Base de données réinitialisée (toutes les données supprimées)", status="ok", user=current_user, ip=get_client_ip(request))
    await db.commit()

    # Rendre la session courante son unique connexion avant de fermer tout le pool — sinon
    # `engine.dispose()` ci-dessous couperait sous ses pieds la connexion encore tenue par
    # `db` (ouverte via la dépendance get_db pour toute la durée de la requête).
    await db.close()

    db_path = Path(settings.DB_PATH)
    cover_dir = Path(settings.COVER_CACHE_DIR)

    # `engine` est un singleton applicatif partagé par toutes les requêtes (voir database.py) :
    # le vider de son pool de connexions avant de supprimer le fichier évite qu'une connexion
    # déjà ouverte continue de viser un fichier disparu, ou qu'une écriture concurrente rate
    # entre le unlink() et la recréation ci-dessous (SQLite déconseille explicitement de
    # supprimer/renommer un fichier de base en cours d'utilisation).
    await engine.dispose()

    if db_path.exists():
        db_path.unlink()
    # WAL laisse deux fichiers compagnons (-wal, -shm) à côté de la base ; les laisser traîner
    # ferait repartir la nouvelle base avec un journal d'écriture obsolète au prochain accès.
    for suffix in ("-wal", "-shm"):
        companion = db_path.with_name(db_path.name + suffix)
        companion.unlink(missing_ok=True)

    if cover_dir.exists():
        shutil.rmtree(cover_dir)
    cover_dir.mkdir(parents=True, exist_ok=True)

    # Recrée le schéma tout de suite sur le fichier neuf : sans ça, `engine` continuerait de
    # pointer sur un chemin qui n'a plus aucune table jusqu'au prochain redémarrage du
    # conteneur, et toute requête suivante échouerait avec "no such table".
    await init_db()

    # bootstrap_first_admin (normalement appelé une seule fois, au tout premier démarrage de
    # l'app — voir main.py::lifespan) doit être rejoué ici : la base neuve n'a plus aucun User
    # ni AuthConfig, donc plus personne ne pourrait jamais se reconnecter avant un redémarrage
    # manuel du conteneur. Nouvelle session dédiée : `db` a déjà été fermée plus haut, et de
    # toute façon elle daterait d'avant la recréation du schéma.
    from ..database import AsyncSessionLocal
    async with AsyncSessionLocal() as fresh_db:
        await auth_service.bootstrap_first_admin(fresh_db)

    return {"ok": True}


@router.get("", response_model=SettingsOut)
async def get_current_settings():
    return SettingsOut(
        library_subdir=settings.LIBRARY_SUBDIR,
        media_root_name=Path(settings.MEDIA_ROOT).name,
        google_books_configured=bool(settings.GOOGLE_BOOKS_API_KEY),
        comicvine_configured=bool(settings.COMICVINE_API_KEY),
        rename_pattern=settings.RENAME_PATTERN,
    )


@router.put("", response_model=SettingsOut)
async def update_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    if body.library_subdir is not None:
        subdir = body.library_subdir.strip().strip("/")
        if subdir:
            media_root = Path(settings.MEDIA_ROOT).resolve()
            p = (media_root / subdir).resolve()
            # Même garde-fou que GET /settings/browse — sans elle, un "../.." dans subdir
            # (ex. depuis un appel API direct, en dehors du sélecteur de dossier de l'UI qui
            # ne le permettrait jamais) ferait pointer toute la bibliothèque en dehors de
            # MEDIA_ROOT, n'importe où d'accessible sur le NAS par le process app.
            if not p.is_relative_to(media_root):
                raise HTTPException(status_code=403, detail="Accès refusé : chemin hors de MEDIA_ROOT")
            if not p.exists() or not p.is_dir():
                raise HTTPException(status_code=400, detail=f"Sous-dossier introuvable : {subdir}")
        if subdir != settings.LIBRARY_SUBDIR:
            # Vider le cache covers quand le dossier change
            cover_dir = Path(settings.COVER_CACHE_DIR)
            if cover_dir.exists():
                for f in cover_dir.glob("*.jpg"):
                    f.unlink(missing_ok=True)
            # Reset cover_cached flag in DB so covers get regenerated
            from ..models.db_models import Tome
            await db.execute(sql_update(Tome).values(cover_cached=False))
            await db.commit()
        _rewrite_env("LIBRARY_SUBDIR", subdir)
        settings.LIBRARY_SUBDIR = subdir

    if body.google_books_api_key is not None:
        _rewrite_env("GOOGLE_BOOKS_API_KEY", body.google_books_api_key)
        settings.GOOGLE_BOOKS_API_KEY = body.google_books_api_key

    if body.comicvine_api_key is not None:
        _rewrite_env("COMICVINE_API_KEY", body.comicvine_api_key)
        settings.COMICVINE_API_KEY = body.comicvine_api_key

    if body.rename_pattern is not None:
        _rewrite_env("RENAME_PATTERN", body.rename_pattern)
        settings.RENAME_PATTERN = body.rename_pattern

    return SettingsOut(
        library_subdir=settings.LIBRARY_SUBDIR,
        google_books_configured=bool(settings.GOOGLE_BOOKS_API_KEY),
        comicvine_configured=bool(settings.COMICVINE_API_KEY),
        rename_pattern=settings.RENAME_PATTERN,
    )
