"""
Détection des cases (panels) d'une page de BD par un modèle YOLO léger (ONNX), pour
l'option "Zoom sur les cases" du lecteur (désactivée par défaut) — voir routers/reader.py.
Résultats mis en cache en base (TomePagePanels), jamais recalculés deux fois pour la même
page.

Modèle : manga-panel-detector-yolo26n (huggingface.co/leoxs22), 2 classes (0=case, 1=bulle
de texte — seule la classe "case" nous intéresse ici), exporté en ONNX avec NMS intégré
(model.export(format="onnx", nms=True)) pour éviter la dépendance ultralytics/torch en
production (~1 Go à elle seule) — onnxruntime seul suffit à l'inférence.
"""
import io
from pathlib import Path

from PIL import Image

MODEL_PATH = Path(__file__).resolve().parent.parent / "assets" / "models" / "manga_panel_detector.onnx"
INPUT_SIZE = 640
CONF_THRESHOLD = 0.25
PANEL_CLASS = 0

# Chargé à la demande — l'option est désactivée par défaut, inutile de payer le coût de
# chargement du modèle pour tout le monde au démarrage de l'app.
_session = None


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort
        _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    return _session


def _letterbox(img: Image.Image, size: int = INPUT_SIZE):
    """Redimensionne en conservant le ratio et complète avec du gris (114) — le
    prétraitement standard YOLO. Un simple resize qui déforme l'image fausse la détection
    (vérifié : produit des cases dupliquées/mal placées)."""
    w, h = img.size
    scale = min(size / w, size / h)
    new_w, new_h = round(w * scale), round(h * scale)
    resized = img.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas.paste(resized, (pad_x, pad_y))
    return canvas, scale, pad_x, pad_y


def _center(box: list[float], axis: int) -> float:
    lo, hi = axis, axis + 2
    return (box[lo] + box[hi]) / 2


def _find_gutter(boxes: list[list[float]], axis: int) -> float | None:
    """Cherche une coordonnée qui sépare les boîtes en deux groupes non vides sans qu'aucune
    ne la chevauche (le plus grand espace vide sur cet axe), ou None si aucune coupure nette
    n'existe (boîtes qui se chevauchent sur tout l'axe)."""
    lo_idx, hi_idx = axis, axis + 2
    intervals = sorted((b[lo_idx], b[hi_idx]) for b in boxes)
    merged: list[list[float]] = []
    for lo, hi in intervals:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    if len(merged) < 2:
        return None
    best_gap, best_cut = -1.0, None
    for i in range(len(merged) - 1):
        gap = merged[i + 1][0] - merged[i][1]
        if gap > best_gap:
            best_gap, best_cut = gap, (merged[i][1] + merged[i + 1][0]) / 2
    return best_cut


def _xycut(boxes: list[list[float]], ltr: bool = True) -> list[list[float]]:
    """Trie des boîtes [x1,y1,x2,y2] dans l'ordre de lecture par découpe récursive
    horizontale puis verticale (algorithme xy-cut, technique standard d'analyse de mise en
    page pour une grille irrégulière — validé à la main sur une vraie page avant
    implémentation : coupe d'abord les bandes horizontales, puis à l'intérieur de chacune
    les colonnes verticales, gauche-à-droite pour ltr). Repli trivial (tri y puis x) si des
    cases se chevauchent sur les deux axes, cas non rencontré en pratique."""
    if len(boxes) <= 1:
        return list(boxes)

    cut_y = _find_gutter(boxes, axis=1)
    if cut_y is not None:
        top = [b for b in boxes if _center(b, 1) < cut_y]
        bottom = [b for b in boxes if _center(b, 1) >= cut_y]
        if top and bottom:
            return _xycut(top, ltr) + _xycut(bottom, ltr)

    cut_x = _find_gutter(boxes, axis=0)
    if cut_x is not None:
        left = [b for b in boxes if _center(b, 0) < cut_x]
        right = [b for b in boxes if _center(b, 0) >= cut_x]
        if left and right:
            first, second = (left, right) if ltr else (right, left)
            return _xycut(first, ltr) + _xycut(second, ltr)

    return sorted(boxes, key=lambda b: (b[1], b[0]))


def detect_panels_sync(image_bytes: bytes, ltr: bool = True) -> list[list[float]]:
    """Retourne les cases d'une page, triées dans l'ordre de lecture, en coordonnées
    normalisées [0,1] (indépendantes de la résolution réelle de l'image — le frontend les
    applique via un simple transform CSS sur l'image déjà chargée, pas de recadrage serveur)."""
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_w, orig_h = img.size
    canvas, scale, pad_x, pad_y = _letterbox(img)

    arr = np.asarray(canvas).astype(np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[None, :, :, :]

    sess = _get_session()
    outputs = sess.run(None, {sess.get_inputs()[0].name: arr})
    dets = outputs[0][0]

    boxes: list[list[float]] = []
    for x1, y1, x2, y2, conf, cls in dets:
        # numpy float32 (pas nativement sérialisable en JSON) -> float Python dès la sortie
        x1, y1, x2, y2, conf, cls = float(x1), float(y1), float(x2), float(y2), float(conf), int(cls)
        if conf < CONF_THRESHOLD or cls != PANEL_CLASS:
            continue
        x1, x2 = (x1 - pad_x) / scale, (x2 - pad_x) / scale
        y1, y2 = (y1 - pad_y) / scale, (y2 - pad_y) / scale
        boxes.append([
            max(0.0, min(1.0, x1 / orig_w)), max(0.0, min(1.0, y1 / orig_h)),
            max(0.0, min(1.0, x2 / orig_w)), max(0.0, min(1.0, y2 / orig_h)),
        ])

    return _xycut(boxes, ltr=ltr)
