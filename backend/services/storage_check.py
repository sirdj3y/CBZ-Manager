import os
from pathlib import Path
from typing import Optional

from ..config import settings


def check_media_identity() -> Optional[dict]:
    """Compare l'identité (UID/GID) du process applicatif à celle du propriétaire du
    dossier média. Retourne None si tout correspond (ou si la vérification n'a pas de
    sens, ex. non applicable hors Linux), sinon le détail du désaccord — jamais appliqué
    automatiquement, uniquement informatif (voir docker-entrypoint.sh / README pour le
    principe PUID/PGID)."""
    try:
        media_path = Path(settings.MEDIA_ROOT)
        if not media_path.is_dir():
            return None
        st = media_path.stat()
        app_uid, app_gid = os.getuid(), os.getgid()
        if st.st_uid == app_uid and st.st_gid == app_gid:
            return None
        return {
            "app_uid": app_uid,
            "app_gid": app_gid,
            "media_uid": st.st_uid,
            "media_gid": st.st_gid,
        }
    except Exception:
        return None
