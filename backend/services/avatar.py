from pathlib import Path
from PIL import Image
import io

from ..config import settings

# Sous-dossier de COVER_CACHE_DIR (donc déjà sur le volume /data existant) plutôt qu'un
# nouveau réglage/volume Docker dédié — même raisonnement que covers/thumbs.
_AVATAR_DIR = Path(settings.COVER_CACHE_DIR).parent / "avatars"

# Préréglages livrés avec l'app (donc dans le code, pas sur /data qui est un volume monté
# par l'utilisateur et exclu de Git/l'image Docker) — backend/assets, à côté du code qui les
# lit, plutôt que frontend/src/assets dont les noms de fichiers sont hashés au build et pas
# stables pour une lecture serveur.
PRESET_DIR = Path(__file__).resolve().parent.parent / "assets" / "avatar_presets"
PRESET_COUNT = 10


def get_avatar_path(user_id: int) -> Path:
    return _AVATAR_DIR / f"{user_id}.jpg"


def get_preset_path(n: int) -> Path:
    return PRESET_DIR / f"avatar-{n}.jpg"


def save_avatar(user_id: int, img_bytes: bytes) -> None:
    """Recadre en carré (centré) et redimensionne — mêmes réglages JPEG que cover_cache."""
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))

    max_side = 256
    if side > max_side:
        img = img.resize((max_side, max_side), Image.LANCZOS)

    dest = get_avatar_path(user_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPEG", quality=88, optimize=True)


def delete_avatar(user_id: int) -> None:
    path = get_avatar_path(user_id)
    if path.exists():
        path.unlink()
