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
chown -R appuser:appuser /data

exec gosu appuser "$@"
