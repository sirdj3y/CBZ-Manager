from pathlib import Path
from PIL import Image
import io

from ..config import settings

# Sous-dossier de COVER_CACHE_DIR (donc déjà sur le volume /data existant) — même
# raisonnement que avatars/covers : pas de nouveau réglage/volume Docker dédié.
_HERO_DIR = Path(settings.COVER_CACHE_DIR).parent / "series_hero"

# Fond : photo/illustration, JPEG (pas de transparence à préserver), large pour couvrir le
# bandeau sur grand écran. Logo/personnage : PNG, transparence préservée (fond de la carte
# visible autour), hauteur plus modeste (affichés à taille contenue, jamais plein cadre).
_KINDS = {
    "background": {"ext": "jpg", "max_width": 1600},
    "logo": {"ext": "png", "max_height": 600},
    "character": {"ext": "png", "max_height": 900},
}


def _validate_kind(kind: str) -> dict:
    spec = _KINDS.get(kind)
    if spec is None:
        raise ValueError(f"Type d'image hero inconnu : {kind}")
    return spec


def get_hero_path(series_id: int, kind: str) -> Path:
    spec = _validate_kind(kind)
    return _HERO_DIR / f"{series_id}_{kind}.{spec['ext']}"


def save_hero_image(series_id: int, kind: str, img_bytes: bytes) -> None:
    spec = _validate_kind(kind)
    img = Image.open(io.BytesIO(img_bytes))

    if spec["ext"] == "jpg":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        max_width = spec["max_width"]
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    else:
        # PNG : préserve la transparence (logo/personnage détouré) plutôt que de forcer RGB.
        if img.mode not in ("RGBA", "LA"):
            img = img.convert("RGBA")
        # Rogne les marges transparentes — des logos uniformisés à un même canevas (fichiers
        # source de tailles identiques, avec du remplissage transparent autour du graphisme
        # réel) affichaient sinon ce vide à l'écran : le site rend le logo en largeur fixe/
        # hauteur automatique, donc la marge intégrée au PNG reste visible telle quelle.
        bbox = img.getchannel("A").getbbox()
        if bbox:
            img = img.crop(bbox)
        max_height = spec["max_height"]
        if img.height > max_height:
            ratio = max_height / img.height
            img = img.resize((int(img.width * ratio), max_height), Image.LANCZOS)

    dest = get_hero_path(series_id, kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if spec["ext"] == "jpg":
        img.save(str(dest), "JPEG", quality=85, optimize=True, progressive=True)
    else:
        img.save(str(dest), "PNG", optimize=True)


def delete_hero_image(series_id: int, kind: str) -> None:
    path = get_hero_path(series_id, kind)
    if path.exists():
        path.unlink()
