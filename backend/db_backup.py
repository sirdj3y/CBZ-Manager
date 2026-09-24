"""Sauvegarde de la base SQLite au démarrage du conteneur, quand la version de l'app change.

Appelé par docker-entrypoint.sh avant le lancement d'uvicorn, donc avant que init_db()
n'applique ses ALTER TABLE : avec Watchtower, une nouvelle version démarre seule, et revenir
à l'image précédente ne défait pas ce qu'elle a fait à la base. Restauration : voir README (Sauvegarde automatique de la base).

Script autonome (aucun import de `backend`) : il tourne avant l'app, avec la stdlib seule.
Ne fait jamais échouer le démarrage — une sauvegarde ratée est signalée dans les logs.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

KEEP = 5


def main() -> None:
    db_path = Path(os.environ.get("DB_PATH", "/data/cbzmanager.db"))
    version_file = Path(os.environ.get("APP_VERSION_FILE", "/app/VERSION"))
    version = version_file.read_text().strip() if version_file.exists() else "inconnue"
    marker = db_path.parent / ".last_version"
    backup_dir = db_path.parent / "backups"

    previous = marker.read_text().strip() if marker.exists() else None
    if previous == version:
        return
    if not db_path.exists():
        # Premier démarrage : rien à sauvegarder.
        marker.write_text(version)
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    # Nommé d'après la version qui a écrit la base, c'est-à-dire celle vers laquelle on reviendrait.
    target = backup_dir / f"cbzmanager-v{previous or 'avant-' + version}-{stamp}.db"

    # API de sauvegarde SQLite : copie cohérente même en mode WAL (un simple cp ne l'est pas).
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    backups = sorted(backup_dir.glob("cbzmanager-v*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP:]:
        old.unlink()

    marker.write_text(version)
    print(f"[db-backup] {previous or '?'} → {version} : base sauvegardée dans {target}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — ne jamais bloquer le démarrage
        print(f"[db-backup] ÉCHEC de la sauvegarde, démarrage quand même : {exc}", file=sys.stderr, flush=True)
