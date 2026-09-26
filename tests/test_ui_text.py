"""Pas de tiret long « — » dans les messages du serveur que l'interface affiche (erreurs,
entrées de l'Historique) — voir aussi frontend/tests/uiText.test.js."""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def test_aucun_tiret_long_dans_les_messages():
    found = []
    for f in BACKEND.rglob("*.py"):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            code = line.split("#")[0]
            if "—" not in code or code.strip().startswith(('"""', "'''")):
                continue
            # Chaînes de messages uniquement (f-strings et littéraux), pas les docstrings.
            if re.search(r'f?"[^"\n]*—[^"\n]*"', code) and re.search(r"detail|activity_log|log\(|msg|message|label|raise|print|return|\+", code):
                found.append(f"{f.relative_to(BACKEND)}:{n} : {line.strip()[:100]}")
    assert found == []
