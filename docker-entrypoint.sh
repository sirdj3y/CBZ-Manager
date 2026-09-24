#!/bin/sh
# Runs as root (container default), adjusts the app user's UID/GID to match the host
# (PUID/PGID — same convention as linuxserver.io images, familiar to NAS users), fixes
# ownership of /data, then drops privileges before exec'ing the actual app.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -g appuser)" != "$PGID" ]; then
    groupmod -o -g "$PGID" appuser
fi
if [ "$(id -u appuser)" != "$PUID" ]; then
    usermod -o -u "$PUID" appuser
fi

mkdir -p /data
# Sauvegarde de la base si la version a changé, avant que l'app n'en modifie le schéma
# (data/backups/, 5 dernières). Avant le chown, qui rend aussi les sauvegardes à appuser.
python /app/backend/db_backup.py
chown -R appuser:appuser /data

exec gosu appuser "$@"
