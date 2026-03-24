"""
Les modules CBZManager/core/ utilisent des imports absolus du style:
  from core.models import ...
  from core.reader import ...

Ce module ajoute le dossier parent de core/ au sys.path afin que ces
imports fonctionnent que ce soit en dev (symlink) ou dans le container Docker
(COPY CBZManager/core/ ./backend/core/).
"""
import sys
from pathlib import Path

# backend/ est le dossier courant de ce fichier
_backend_dir = Path(__file__).parent

# Ajoute backend/ dans sys.path pour que "from core.xxx import" fonctionne
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
