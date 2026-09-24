# CBZ Manager

CBZ Manager est une interface web qui permet de gérer, enrichir et lire une bibliothèque de BD et comics.

Organisez votre bibliothèque de façon structurée et élégante. L'app permet l'import, la conversion, le renommage, l'édition de métadonnées et la lecture dans une seule interface fluide. Elle automatise les tâches chronophages (organisation, tagging, compression) tout en laissant un contrôle fin à l'utilisateur, le tout sans dépendance cloud.

## Fonctionnalités

### Bibliothèque
- 📚 Organisation automatique par série (détection par dossier)
- 🖼 Grille de couvertures avec chargement lazy (jusqu'à 8 colonnes)
- 🎨 Cover personnalisée par série (choix parmi les couvertures des albums via un modal dédié)
- 👁 Masquer/afficher des séries sans les supprimer
- 🗑 Suppression de séries ou d'albums depuis l'interface (fichiers + DB, avec confirmation)
- 🔍 Filtres et recherche par auteur, éditeur, tag, format
- 👤 Page Auteurs : liste tous les scénaristes/dessinateurs/éditeurs avec compteurs séries et albums, clic → filtre Albums
- ‹ › Navigation par chevrons entre séries et entre albums

### Import
- 📥 Import depuis l'interface — wizard en 3 étapes :
  1. **Sélection** : cliquer ou glisser-déposer un dossier ou des fichiers individuels (CBZ, CBR, PDF) ; préremplissage automatique du nom de série depuis le nom du dossier
  2. **Options** (3 blocs, un seul ouvert à la fois) :
     - **Métadonnées** : édition par lot (Série, Scénariste, Dessinateur, Éditeur, Langue) avec case "Seulement si vide" ; langue `fr` par défaut ; scraping Google Books / ComicVine par fichier (bouton 🔍) ; navigation clavier ↑/↓
     - **Renommer les fichiers** : pattern avec tokens (`{Série}`, `{Numéro}`, `{Titre}`, `{Dessinateur}`, `{Scénariste}`, `{Éditeur}`, `{Fichier}`), Rechercher/Remplacer, aperçu interactif avec overrides manuels, détection des doublons
     - **Convertir / Recompresser en CBZ** : 4 presets qualité (Light / Medium / HQ / Original) ; comparateur visuel (icône ⓘ) ; résolution de la 1ère image affichée ; taille estimée par fichier
  3. **Import** : traitement séquentiel fichier par fichier (upload → conversion → suivant) ; barre de progression conversion avec compteur de pages `X/Y` ; scan automatique ; redirection vers la série importée

### Métadonnées
- ✏️ Édition des métadonnées ComicInfo.xml (par album ou par série entière) — écrites dans le fichier CBZ
- 🔎 Scraping automatique Google Books / ComicVine
- 🏷 Tags, notes personnelles, filtres
- 📝 Métadonnées saisies à l'import automatiquement intégrées dans le CBZ converti (CBR/PDF → CBZ)

### Lecture
- 📖 Lecteur intégré : page simple, double page, zoom largeur, plein écran, raccourcis clavier
- Icône de lecture visible au survol de la couverture (page album et page série)

### Outils
- ⚡ Conversion CBR/PDF → CBZ (4 presets qualité : Light / Medium / HQ / Original) avec comparateur visuel
- ✎ Renommage de fichiers par pattern avec aperçu et overrides manuels
- 📊 Statistiques animées (KPIs, graphiques, top séries/auteurs)
- 📋 Journal d'activité (scans, imports, éditions, suppressions)

### Technique
- 🔄 Cache de couvertures avec invalidation automatique (`Cache-Control: no-cache` + ETag + versioning URL)
- 🔓 Accès libre — pas de mot de passe (usage réseau local)
- 🐳 Docker prêt pour déploiement sur NAS ou serveur

---

## Formats de fichiers supportés

| Format | Lecture métadonnées | Conversion |
|--------|--------------------|-----------:|
| CBZ / ZIP | ✅ ComicInfo.xml | — |
| CBR / RAR | ✅ ComicInfo.xml | → CBZ |
| PDF | — | → CBZ |

---

## Installation

Il y a deux façons de lancer l'app :

- **Mode dev** : nécessite Python et Node.js
- **Mode Docker** : une seule commande, nécessite Docker

---

### Mode dev (Python + Node.js)

#### Étape 1 — Installer les prérequis

- **Python 3.11+** : https://www.python.org/downloads/
- **Node.js 20+** : https://nodejs.org/

Vérifiez que l'installation est correcte :
```bash
python3 --version   # doit afficher 3.11 ou plus
node --version      # doit afficher v20 ou plus
```

#### Étape 2 — Configurer l'environnement

```bash
cp .env.example .env
```

Ouvrez `.env` et définissez `MEDIA_ROOT` pour pointer vers votre dossier de comics :

```
MEDIA_ROOT=/chemin/vers/vos/comics
```

#### Étape 3 — Installer les dépendances backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

> Sur Windows, remplacez `.venv/bin/` par `.venv\Scripts\`

#### Étape 4 — Lancer le backend

```bash
DEV_MODE=true .venv/bin/uvicorn backend.main:app --reload --port 8000
```

#### Étape 5 — Lancer le frontend (nouveau terminal)

```bash
cd frontend
npm install
npm run dev
```

Ouvrez http://localhost:5173 dans votre navigateur.

---

### Mode Docker

#### Étape 1 — Installer Docker

Téléchargez et installez Docker : https://www.docker.com/products/docker-desktop/

#### Étape 2 — Configurer le volume

Ouvrez `docker-compose.yml` et remplacez le chemin du volume par celui de votre dossier de comics :

```yaml
- /chemin/vers/vos/comics:/media:ro
```

Le second volume (`./data:/data`) n'a rien à configurer : c'est le dossier `data/` créé automatiquement à côté de `docker-compose.yml`, où l'app stocke sa base de données et le cache des couvertures. Comme c'est un dossier normal (pas un volume Docker géré en interne), il est visible et peut être inclus dans vos sauvegardes habituelles.

#### Étape 3 — Lancer

```bash
docker compose up --build
```

Ouvrez http://localhost:5173.

Pour arrêter : `Ctrl+C`
Pour relancer sans reconstruire : `docker compose up`

---

## Déploiement sur un NAS / serveur distant

### 1. Transférer le projet

```bash
rsync -av --exclude '.venv' --exclude 'node_modules' --exclude 'data' \
  /chemin/local/cbz-manager/ user@serveur:/chemin/docker/cbz-manager/
```

### 2. Configurer le volume

Ouvrez `docker-compose.yml` et définissez le chemin vers votre dossier de comics :

```yaml
- /chemin/vers/vos/comics:/media:ro
```

> Pour restreindre l'app à un sous-dossier, configurez `LIBRARY_SUBDIR` depuis la page **Configuration** de l'app.

Le volume `./data:/data` (base de données + cache des couvertures) n'a besoin d'aucune configuration : il se crée automatiquement dans `data/` à côté de `docker-compose.yml` sur le NAS/serveur. Sur Synology avec Container Manager, ce dossier apparaît normalement dans File Station et peut être inclus dans Hyper Backup comme n'importe quel autre dossier.

### 3. Lancer

```bash
docker compose up -d --build
```

L'app est disponible sur `http://adresse-serveur:5173` depuis n'importe quel appareil du réseau.

---

## Structure des dossiers de comics

L'app détecte automatiquement les séries par dossier. Chaque dossier = une série, chaque fichier dedans = un album.

```
Comics/
├── Akira/
│   ├── Akira - T01 - Akira.cbz
│   ├── Akira - T02 - Structures de combat.cbz
│   └── ...
├── Blacksad/
│   ├── Blacksad - T01 - Quelque part entre les ombres.cbz
│   └── ...
```

### Formats de noms de fichiers reconnus

| Exemple | Résultat |
|---------|----------|
| `Akira - T01 - Akira.cbz` | série=Akira, n°=1, titre=Akira |
| `Blacksad - T03 - Âme rouge.cbz` | série=Blacksad, n°=3, titre=Âme rouge |
| `SérieSanstiret T01 - Titre.cbz` | série=SérieSanstiret, n°=1, titre=Titre |

Le pattern recommandé est `{Série} - T{Numéro} - {Titre}`.

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MEDIA_ROOT` | `/media` | Point de montage du dossier de comics |
| `LIBRARY_SUBDIR` | — | Sous-dossier à utiliser (configurable dans l'app) |
| `DB_PATH` | `/data/cbzmanager.db` | Base de données SQLite |
| `COVER_CACHE_DIR` | `/data/covers` | Cache des couvertures |
| `GOOGLE_BOOKS_API_KEY` | — | Clé API Google Books (optionnel) |
| `COMICVINE_API_KEY` | — | Clé API ComicVine (optionnel) |
| `DEV_MODE` | `false` | Active CORS + docs Swagger (`/docs`) |
| `PORT` | `32123` | Port d'écoute interne du conteneur |
| `PUID` / `PGID` | `1000` / `1000` | UID/GID Linux utilisés par l'app dans le conteneur (Docker uniquement, non-root). Alignez-les sur votre propre utilisateur NAS (`id votre_user`) pour que le dossier `data/` reste lisible/modifiable avec ce compte en dehors de Docker. |

---

## Raccourcis clavier (lecteur)

| Touche | Action |
|--------|--------|
| `→` / `Espace` | Page suivante |
| `←` | Page précédente |
| `↑` | Zoom largeur de l'écran |
| `↓` | Retour vue page entière |
| `d` | Toggle double page |
| `f` | Plein écran |
| `Échap` | Fermer le lecteur / fermer un modal |

---

## Structure du projet

```
cbz-manager/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Variables d'environnement
│   ├── database.py          # SQLAlchemy async + SQLite
│   ├── dependencies.py      # Dépendances FastAPI
│   ├── models/
│   │   ├── db_models.py     # Modèles SQLAlchemy (Series, Tome, Metadata, ScanJob…)
│   │   └── schemas.py       # Schémas Pydantic
│   ├── routers/             # Routes API par domaine
│   │   ├── library.py       # Scan, séries, navigation
│   │   ├── tomes.py         # Albums, métadonnées, renommage
│   │   ├── covers.py        # Cache couvertures (ETag, no-cache)
│   │   ├── reader.py        # Pages lecteur
│   │   ├── scraper.py       # Google Books / ComicVine
│   │   ├── converter.py     # CBR/PDF → CBZ
│   │   ├── import_router.py # Import de fichiers
│   │   ├── settings.py      # Configuration
│   │   ├── activity.py      # Journal d'activité
│   │   └── stats.py         # Statistiques
│   └── services/            # Logique métier
│       ├── scanner.py
│       ├── metadata_writer.py
│       ├── cover_cache.py
│       ├── converter_service.py
│       ├── scraper_google.py
│       ├── scraper_comicvine.py
│       ├── activity.py
│       └── filename_parser.py
├── frontend/
│   └── src/
│       ├── views/           # Pages Vue
│       ├── components/      # Composants réutilisables
│       ├── stores/          # Pinia
│       ├── api/             # Clients Axios
│       └── router/          # Vue Router
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
