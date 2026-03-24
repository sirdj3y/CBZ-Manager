# Changelog — CBZManager

---

## v1.5.0 — 2026-03-24 — Page Auteurs & autocomplétion

### Nouveau
- **Page Auteurs** (`/authors`) : tableau liste avec 2 onglets (Auteurs / Éditeurs), tri alphabétique, recherche via la barre globale, compteurs Séries et Albums par auteur/éditeur
- **Autocomplétion** sur les champs Scénariste, Dessinateur, Éditeur dans le formulaire de métadonnées (MetadataForm), l'import (étape 2) et les filtres de la bibliothèque — multi-valeurs séparées par virgule
- **Pool commun** writers+pencillers pour l'autocomplétion : un auteur polyvalent (ex. Peyo) apparaît dans les deux champs
- **Liens cliquables** Scénariste / Dessinateur / Éditeur sur la page série → filtre Albums
- **Clic auteur** depuis la page Auteurs → Albums filtrés (writer OU penciller pour les auteurs, publisher pour les éditeurs)
- **Page Diagnostic** : détection de doublons par taille+nom au lieu de MD5 synchrone (résout le chargement infini sur les grosses bibliothèques)

### Corrections
- Page Diagnostic chargeait indéfiniment : calcul MD5 synchrone bloquait asyncio (~22s/requête) → remplacé par clé taille+nom (instantané)
- Filtre Albums : writer+penciller identiques appliqués en OR au lieu de AND (auteur polyvalent)

---

## v1.4.0 — 2026-03-23 — UI & Settings

### Nouveau
- **Navigation Settings** : remplacement des onglets par un sous-menu sidebar collapsible avec 5 pages (Configuration, Sauvegarde & BDD, Diagnostic, Historique, À propos)
- **Page Diagnostic** (ex-Health) : chargement automatique au montage, colonnes Série + Album + Format + Détail, style unifié avec Historique, URL `/settings/diagnostic`
- **Page À propos** : description de l'app, auteur, version, stack, taille cache covers
- **Presets conversion renommés** : Légère→Light / Équilibrée→Medium / Haute→HQ / Originale→Original (frontend + backend)
- **Comparateur visuel qualité** : icône `info.svg` au survol de "Qualité :" dans le bloc Convertir (Import et ConverterModal) — popover avec 2 images Light vs Original
- **Sidebar réduite** : icône app proportionnelle (28px), centrée ; sous-menu Configuration centré quand sidebar réduite
- **Journal d'activité** : ajout des actions masquer/afficher série et album, cover personnalisée, réinitialisation DB ; icônes SVG à la place des emojis

### Corrections
- Bug #21 : renommer une série ne mettait pas à jour `Series.name` en base de données
- Bloc Conversion fermé par défaut à l'étape 2 de l'import (seul Métadonnées ouvert)
- Icône app sidebar tronquée en mode réduit (CSS scoped + binding de classe direct)
- Icône `info.svg` absente dans ImportView (uniquement ajoutée dans ConverterModal initialement)

---

## v1.3.0 — 2026-03-22 — Import UX & corrections

### Nouveau
- **Barre de progression conversion** : uniquement lors de la conversion (pas à l'upload), avec compteur de pages `X/Y` à droite
- **Progression live** : le polling `/api/convert/{job_id}` lit désormais le store en mémoire (`_progress`) pour un suivi temps réel page par page
- **Icône de lecture** sur les covers au survol dans SeriesDetailView (grande icône centrée)
- **Menu "Plus d'options"** dans SeriesCard : détection de bord droit pour ouverture à gauche (évite la sortie d'écran)
- **Popup avertissement** au clic "Importer" si des fichiers non-CBZ ont des métadonnées sans conversion activée

### Corrections
- Import séquentiel : chaque fichier est uploadé puis converti avant de passer au suivant
- `delete_source: true` passé à l'API de conversion — le fichier source est supprimé après conversion réussie
- Preset "Originale" sélectionné automatiquement quand on coche un fichier sans preset choisi
- Erreur "Read-only file system" : `.env` avait le placeholder `/chemin/vers/vos/comics` au lieu du chemin réel ; la variable `MEDIA_ROOT=/media` est maintenant forcée dans `docker-compose.yml`
- Progression conversion toujours à 0% (lecture DB au lieu du store en mémoire) — corrigé
- Colonne `delete_source` manquante dans SQLite : migration manuelle `ALTER TABLE convert_jobs ADD COLUMN delete_source`
- Label "✓ Importé et converti" remplacé par "✓ Terminé"

---

## v1.2.0 — 2026-03-21 — Import wizard

### Nouveau
- **Wizard d'import en 3 étapes**
  - Étape 1 — Sélection : cliquer ou glisser-déposer un dossier ou des fichiers individuels (CBZ, CBR, PDF) ; préremplissage automatique du nom de série depuis le nom du dossier ; liste triée alphabétiquement ; scroll si nombreux fichiers
  - Étape 2 — Options (3 blocs accordion, un seul ouvert à la fois) :
    - **Métadonnées** : édition par lot (Série, Scénariste, Dessinateur, Éditeur, Langue) avec case "Seulement si vide" ; langue `fr` par défaut ; scraping Google Books / ComicVine par fichier (bouton 🔍) ; navigation clavier ↑/↓ dans le tableau
    - **Renommer les fichiers** : pattern `{Série} - T{Numéro} - {Titre}` par défaut, tokens cliquables, Rechercher/Remplacer, aperçu interactif avec overrides manuels, détection des doublons
    - **Convertir / Recompresser en CBZ** : 4 presets (Légère / Équilibrée / Haute / Originale) ; résolution de la 1ère image affichée ; taille estimée par fichier ; aucune conversion par défaut ; sélection d'un preset coche tous les fichiers automatiquement
  - Étape 3 — Import : tableau unifié par fichier avec colonnes Upload / Conversion ; scan automatique ; redirection vers la série importée
- **Icônes SVG** `folder-open` et `upload` dans la zone de dépôt et le menu
- **Logs d'activité** : chaque fichier importé génère une entrée dans le journal
- Endpoint `POST /api/import/lookup-tomes` — résolution filepath → tome_id pour la conversion post-import
- Endpoint `POST /api/import/image-size` — résolution de la 1ère image d'un CBZ/CBR

### Corrections
- Préfixe `[CONVERTED]` supprimé : les fichiers convertis gardent leur nom d'origine
- Bug édition par lot (1 seule lettre affichée) : comparaison sur les valeurs d'origine au lieu des valeurs courantes
- Réactivité du watcher métadonnées corrigée
- Trait du stepper déplacé en bas des indicateurs (ne barre plus le texte)

---

## v1.1.0 — 2026-03-21 — Améliorations UI

### Nouveau
- **Navigation chevrons ‹ ›** entre séries et entre albums dans le fil d'ariane
- **Overlay lecture** au survol de la couverture sur la page d'un album
- **Fermeture Escape** sur tous les modals
- Terme **"album/albums"** unifié dans toute l'interface

### Corrections
- **Cache couvertures** : invalidation automatique via `Cache-Control: no-cache` + ETag + versioning URL
- **Nommage des séries** : le scanner utilisait un nom générique pour les fichiers à la racine d'un sous-dossier — remplacé par le nom réel du dossier
- **Cover série** : mise à jour du store local sans refetch complet
- **Icônes menu** : taille unifiée

---

## v1.0.0 — 2026-03-20 — Version initiale

### Fonctionnalités
- Scan automatique de bibliothèque (dossier = série, fichiers = albums)
- Grille de couvertures avec chargement lazy (jusqu'à 8 colonnes)
- Cover personnalisée par série (choix parmi les albums via modal dédié)
- Nettoyage des covers orphelines au scan
- Masquer/afficher des séries sans suppression
- Suppression séries/albums depuis l'interface (fichiers + DB, avec confirmation)
- Filtres et recherche par auteur, éditeur, tag, format
- Lecteur intégré : page simple, double page, zoom largeur, plein écran, raccourcis clavier
- Édition métadonnées ComicInfo.xml (30+ champs) par album ou par série entière
- Scraping automatique Google Books / ComicVine
- Conversion CBR/PDF → CBZ (4 presets qualité)
- Renommage de fichiers par pattern avec aperçu et overrides manuels
- Notes utilisateur, rating 5 étoiles, tags
- Statistiques animées (KPIs, graphiques, top séries/auteurs)
- Journal d'activité (scans, imports, éditions, suppressions)
- Export/import sauvegarde JSON
- Settings dynamiques (sous-dossier bibliothèque, clés API)
- Tri albums par numéro (T01, T02… puis HS01, HS02…)
- Docker multi-stage prêt pour déploiement sur NAS ou serveur
