# Changelog — CBZManager

---

## Non publié (branche develop)

### Nouveau

- **Déploiement automatique** : image construite par GitHub Actions et publiée sur GHCR, mise à jour du NAS par Watchtower (branche `main` → prod, `develop` → préprod sur le port 5174).
- **Sauvegarde automatique de la base** au démarrage d'une nouvelle version, avant toute modification de schéma (`data/backups/`, 5 dernières conservées).
- **Tests automatisés** : 50 tests backend (pytest : analyse des noms de fichiers, sécurité des archives, écriture ComicInfo, sauvegarde, parcours API connexion → scan → édition) et 35 tests frontend (vitest : règles Smart List, modèle de renommage, tri des tomes, recherche). Ils bloquent la publication de l'image en cas d'échec.

- **Diagnostic : données orphelines** : détecte les données rattachées à un album, une série ou un compte qui n'existe plus (progression et notes, temps de lecture, listes intelligentes, séries masquées, albums manquants, métadonnées, cases détectées), une ligne par type, avec un bouton « Nettoyer ». Nettoie ce que les bugs de suppression ont pu laisser dans une base existante.

- **Labo shadcn-vue** (`/labo/shadcn`, non lié dans le menu) : essai des composants shadcn-vue avec les couleurs de l'app sur la vraie bibliothèque — tableau des séries, menu d'actions, dialogue, panneau latéral, recherche ⌘K. Isolé du reste de l'app.

### Corrections

- **Numéros de tome décimaux ou à suffixe tronqués** (« 13.5 » → « 13 », « 7bis » → « 07 ») au renommage, à l'import et au remplissage du champ Numéro depuis un scraper : un tome 13.5 prenait le nom et le numéro du tome 13.

- **Données orphelines à la suppression** : supprimer un album laissait son temps de lecture en base, et supprimer un compte laissait son temps de lecture et ses listes intelligentes. SQLite réutilisant les identifiants, ces données pouvaient réapparaître sur le prochain album ou compte créé (même famille de bug que la progression de lecture corrigée en août).

### Technique

- Build du frontend sous Node 22 (Node 20 n'est plus maintenu).

---

## v1.24.0 — 2026-09-17 — Réglages d'image du lecteur, reprise de lecture repensée, finitions

### Nouveau

- **Panneau de réglages d'image dans le lecteur** (icône "baguette magique") : curseurs Luminosité, Contraste et Saturation en CSS `filter` natif (temps réel, aucun retraitement d'image), plus un vrai réglage de **Netteté** via un filtre SVG (`feConvolveMatrix`, noyau de renforcement de contours) — CSS n'ayant pas de fonction "sharpen" native, contrairement aux trois autres réglages. Un mode nuit (inversion de luminosité) a été ajouté puis retiré du panneau après un premier essai jugé sans intérêt. Tous les réglages repartent à zéro à chaque nouvel album, comme le zoom.
- **Ancrage du zoom généralisé aux modes Page et Double** (trackpad/Ctrl+molette et curseur de zoom) : jusqu'ici seul le mode Défilement gardait le point de contenu sous le curseur lors d'un zoom, les modes Page/Double zoomaient depuis un coin. Le calcul se base sur la position de scroll réelle au moment du geste, donc reste valable même là où le centrage CSS seul ne suffisait pas (mode Double).
- **"Reprendre la lecture" repensé** : la boîte de dialogue bloquante a été remplacée par un bandeau non intrusif. Après un premier essai (reprise automatique et silencieuse, bandeau purement informatif), le comportement a été inversé à la demande de l'utilisateur : la lecture démarre désormais du début par défaut, le bandeau propose "Reprendre à la page X" comme une action explicite (disparaît tout seul après quelques secondes si on l'ignore).
- **Trame de points étendue à la fiche Album** (troisième et dernier des trois bandeaux hero de l'app, après Accueil et fiche Série).
- **Activité de lecture (page Statistiques, onglet "Ma lecture") repensée en rangée de barres façon "moniteur de disponibilité"** (UptimeRobot/Statuspage) — hauteur uniforme, 5 paliers d'intensité de couleur selon le temps de lecture du jour, plutôt qu'un histogramme à hauteur variable.
- **Nouvelle carte "Séries en cours"** dans l'onglet "Ma lecture" (nombre de séries distinctes ayant au moins un album entamé mais pas encore marqué lu), à côté d'"Albums en cours" (renommé pour plus de clarté, ex-"En cours").

### Corrections

- **Flash visuel du fond de la bannière d'accueil** : le fond spécifique à une série (téléchargé sur le réseau) remplaçait brutalement le fond par défaut (image locale, instantanée) le temps du chargement, perçu comme un "saut" au premier affichage. Le fond par défaut reste maintenant affiché en permanence, le fond réel se pose par-dessus en fondu une fois chargé.

### Contexte

Suite directe de la session v1.23.0. Plusieurs allers-retours de précision sur le bandeau de reprise de lecture (l'utilisateur a d'abord validé une reprise automatique, puis a demandé l'inverse une fois vu à l'usage — la fonctionnalité a été livrée deux fois avant de converger). Discussion approfondie sur les fonctionnalités d'amélioration d'image avant implémentation (technologies envisagées, faisabilité d'un vrai filtre de netteté en CSS pur — impossible, d'où le filtre SVG — et pertinence du noir et blanc sur une BD couleur), le mode nuit ayant été retiré après un premier essai. La fonctionnalité "déplacer un album vers une autre série", évoquée comme piste, s'est révélée déjà entièrement implémentée (constatée par lecture directe du code) : mémoire de session corrigée en conséquence.

### Validation

Filtre de netteté et ancrage du zoom vérifiés par lecture de code et déploiement (cohérence des formules), sans mesure de performance réelle sur appareil (signalé explicitement à l'utilisateur comme limite de cette session, faute d'outil de profilage navigateur). Nouveau champ `series_in_progress_count` vérifié en direct via `curl` authentifié sur le conteneur de dev. Reste vérifié par lecture de code et déploiement local, sans outil de navigateur pour confirmation visuelle au-delà des retours directs de l'utilisateur à chaque étape.

---

## v1.23.0 — 2026-09-17 — Lecteur repensé, trame de points sur les bandeaux, "Ma lecture"

### Nouveau

- **Lecteur entièrement repensé**, en plusieurs passes successives :
  - Modèle **ajustement (largeur/hauteur) + zoom continu (1×-2,5×)** séparés, le zoom s'appliquant toujours sur l'axe cadré par l'ajustement en cours, jamais sans effet (contrairement à un référentiel externe étudié en cours de route, qui laissait le zoom inerte en ajustement "hauteur" — jugé comme un bug plutôt qu'un choix par les premiers tests).
  - **Mode Défilement** repensé : suivi de la page courante par seuil de scroll (limité à une fois par frame), chargement des pages natif (`loading="eager"/"lazy"`) plutôt qu'un `IntersectionObserver` maison, qui dérivait à chaque changement de zoom.
  - **Mode Double page** : la couverture (page 1) s'affiche désormais seule, les paires suivantes s'enchaînent normalement (2-3, 4-5, ...) — robuste même en reprenant la lecture à une page arbitraire.
  - **Zoom ancré sous le curseur** (trackpad/Ctrl+molette) ou sous le centre de l'écran (curseur de zoom) plutôt que de toujours revenir au coin haut-gauche — recalcul du défilement pour garder le même point de contenu sous le même point d'écran.
  - **Présentation entièrement restylée** (reprise d'une capture d'écran fournie par l'utilisateur) : barres haut/bas désormais opaques et toujours visibles (fini l'auto-masquage après inactivité), sélecteur de mode en menu déroulant (icône + libellé + chevron), ajustement et zoom fusionnés en un seul bloc (libellé cliquable + curseur + pourcentage), boutons bordés partout (zoom sur les cases, plein écran, précédent/suivant), accent vermillon repris de la charte de l'app.
  - Raccourci **"d"** : fait désormais tourner les 3 modes (Page → Double → Défilement) au lieu de ne basculer qu'entre Page et Double.
  - Conservé tout du lecteur existant : reprise de lecture, proposition du tome suivant façon Netflix, zoom sur les cases (option), raccourcis clavier, `loading="eager"/"lazy"` en mode Défilement.
- **Trame de points façon impression BD** ("halftone") sur les bandeaux hero de la page d'accueil et des fiches Série — point vermillon semi-transparent (`color-mix`) répété en grille de 8px, assombri par-dessus le fond via `mix-blend-mode: multiply`, avec ou sans image de fond fournie.
- **Statistiques — nouvel onglet "Ma lecture"**, distinct de "Bibliothèque" (contenu existant) : albums/pages lus, lectures en cours (cliquables), temps de lecture total et moyen par album, activité de lecture des 30 derniers jours (graphique), genres les plus lus, série de jours de lecture consécutifs ("streak", en cours et meilleure série), notes personnelles (déplacées depuis l'onglet Bibliothèque).
  - Nouveau suivi du **temps de lecture actif** : le lecteur envoie un battement au serveur toutes les ~60s tant que l'onglet est visible et qu'il y a eu une interaction dans les 90 dernières secondes (clic, molette, touche, défilement) — un onglet oublié ouvert n'inflate pas les statistiques. Agrégé par jour et par album (`reading_activity`), envoi fiable même à la fermeture brutale de l'onglet (`sendBeacon`). Aucune donnée rétroactive : les albums déjà lus avant la mise en service n'ont pas de temps associé.
- **Recherche du topbar transformée en simple bouton** : un clic (ou la première touche tapée) ouvre directement la recherche globale existante (Ctrl/Cmd+K), au lieu de filtrer la page courante en direct.

### Corrections

- **Faux positifs "albums manquants" sur certaines séries** (ex. "Achille Talon") : le motif de détection du numéro de tome pouvait confondre une lettre en début de mot du nom de la série elle-même (ex. le "T" de "Talon") avec un marqueur de tome, en l'absence d'un tiret juste avant le vrai numéro. Corrigé en restreignant la branche "code en lettres" du motif aux majuscules strictes (codes type INT/HS1), jamais une continuation de mot en minuscules.
- **Résumé non tronqué sur smartphone** dans la fiche Série (mobile suivait une logique différente du desktop) — uniformisé, même limite de caractères partout.
- **Bordure gauche manquante sur la première carte des rangées défilantes** (accueil et fiche Série) : même cause qu'un bug déjà corrigé sur la bordure du haut (`overflow-x: auto` rogne le bord collé au conteneur) mais côté gauche, visible uniquement sur la toute première carte (aucun "gap" voisin pour le masquer). Corrigé sur `.scroll-row` partout, y compris sur la fiche Série ("Plus dans cette série") qui n'avait jamais reçu le correctif du bord du haut non plus.
- **4 cartes de stats de l'accueil illisibles sur smartphone** (Albums/Séries/Auteurs/Éditeurs) : passent en grille 2×2 en dessous de 900px de large, au lieu de s'empiler sur 4 lignes en dessous de 480px.
- Conversion : le job pouvait indiquer "terminé" malgré des erreurs sur certains tomes — le statut final tient désormais compte des tomes en erreur.
- Sauvegarde/restauration : `is_read`, plusieurs champs de métadonnées et les collisions de noms de page à la conversion n'étaient pas correctement pris en compte ; migration désormais idempotente.
- Réponses obsolètes du lecteur/fiche album/fiche série pouvant écraser l'affichage courant lors d'une navigation rapide (garde "toujours d'actualité" ajoutée).
- Proxy de développement Vite pointait sur le mauvais port en configuration locale.

### Contexte

Session très longue, centrée sur une refonte complète et itérative du lecteur (plusieurs dizaines d'allers-retours sur le zoom, l'ancrage, le centrage CSS et le style visuel), déclenchée par une demande initiale d'amélioration de l'UI/UX puis approfondie via l'étude de deux référentiels externes fournis par l'utilisateur (un guide de réplication détaillé, puis un lecteur HTML autonome testé et revu en détail) avant d'aboutir à un style final repris d'une capture d'écran. En parallèle : reprise et clôture des correctifs R7-R10 laissés en suspens depuis la session précédente, correction d'un bug de faux positifs Bedetheque diagnostiqué par test direct du code, ajout de la trame de points sur les bandeaux hero (à la demande explicite, en reprenant un extrait ciblé d'un document de réplication plus large), et construction d'un système de suivi du temps de lecture (nouvelle table, battements réguliers côté lecteur) pour alimenter le nouvel onglet "Ma lecture" de la page Statistiques.

### Validation

Correctifs CSS/zoom vérifiés par un cycle itératif direct avec l'utilisateur (captures d'écran à chaque round, plusieurs corrections reprises/ajustées en fonction des retours). Bug Bedetheque vérifié par test Python direct contre le fichier réel et les cas déjà documentés (Akira, Blacksad, Code Breaker, INT/HS), non déployé en production (attente explicite de l'utilisateur avant cette session). Nouveaux endpoints (`heartbeat`, `/api/stats/me`) vérifiés en direct via `curl` authentifié sur le conteneur de dev (agrégation par jour, plafond anti-abus, calcul de streak). Reste vérifié par lecture de code et déploiement local, sans outil de navigateur pour confirmation visuelle au-delà des captures fournies par l'utilisateur.

---

## v1.22.0 — 2026-09-12 — Bannière d'accueil "cover à gauche", correctifs de bordures des cartes

### Nouveau

- **Bannière d'accueil restructurée** : la cover 3D et le bloc de texte sont désormais groupés côte à côte (au lieu d'une cover centrée en superposition et d'un texte plaqué à gauche), toute la moitié droite du fond reste visible sans être recouverte ni assombrie. Voile plus prononcé sous le texte (plateau opaque + fondu resserré) pour compenser. Titre et sous-titre d'album légèrement éclaircis pour rester lisibles. Pastilles de pagination du slider déplacées en bas au centre de la bannière (au lieu de sous le bloc texte).
- Barre de progression des cartes "Poursuivre la lecture" affinée (4 → 3px) et recolorée en rouge (`var(--danger)`), plus lisible sur une cover sombre.
- Point de départ : une page de test isolée (`/home-alt`, jamais reliée à la navigation), utilisée pour itérer sur cette disposition sans risque avant de l'appliquer à la vraie page d'accueil, puis supprimée une fois le résultat validé.

### Corrections

- **Anneau de survol manquant sur plusieurs cartes de l'accueil** ("Poursuivre la lecture", "Vos séries", rangées défilantes "Albums ajoutés récemment"/"Sélection"/"Résultats") : elles n'appliquaient qu'un agrandissement d'ombre au survol, sans l'anneau coloré utilisé partout ailleurs dans l'app (Albums, Séries, tomes d'une fiche Série).
- **Bordure/ombre de survol mal rendue (carrée et dentelée) sur "Poursuivre la lecture" et "Albums ajoutés récemment"** : la bordure et l'ombre de survol étaient posées sur le même élément que `overflow: hidden` + `border-radius` + un `transform` au survol — combinaison qui fait mal rendre l'ombre à certains navigateurs (elle ne suit plus les coins arrondis). Corrigé en reprenant le schéma déjà utilisé par les cartes "standard" de l'app (Albums, Séries) : la bordure/l'ombre reste sur un élément en `overflow: visible`, le clipping de l'image est délégué à un enfant dédié sans ombre ni transform.
- **Bordure du haut rognée sur les cartes des rangées défilantes** (déjà rencontré une fois sur les pastilles "Genres") : `overflow-x: auto` force `overflow-y: auto` (règle CSS), qui rogne le pixel du haut de la bordure d'un enfant collé au bord du conteneur. Le correctif (petite marge interne compensée) est désormais porté une fois pour toutes par `.scroll-row`, partagé par toutes les sections de l'accueil, plutôt que dupliqué section par section.

### Contexte

Suite directe de la session v1.21.0. La nouvelle disposition de bannière a été mise au point sur une page de test dédiée avant d'être reportée sur la vraie page d'accueil, à la demande explicite de l'utilisateur ("Fait un test sur une page accueil secondaire"). Le report a ensuite révélé un bug de rendu de bordure sur plusieurs types de cartes (signalé avec capture d'écran), diagnostiqué comme un problème structurel de longue date (overflow + border-radius + box-shadow + transform sur le même élément) plutôt qu'une simple valeur CSS à ajuster, puis un second bug de bordure haute rognée déjà rencontré et documenté lors d'une session précédente sur les pastilles "Genres".

### Validation

Bug de bordure diagnostiqué par comparaison directe avec le pattern "standard" déjà en place et fonctionnel ailleurs dans l'app (`.book-card`), confirmé par capture d'écran avant/après. Reste vérifié par lecture de code et déploiement, sans outil de navigateur pour confirmation visuelle finale au-delà des captures fournies par l'utilisateur.

---

## v1.21.0 — 2026-09-12 — Police mono pour les chiffres, sidebar élargie, cohérence des survols

### Nouveau

- **Police monospace (IBM Plex Mono)** introduite pour tous les affichages numériques de l'app : compteurs de nav (Séries/Albums/Auteurs), badges de nombre de tomes, pourcentages "en cours", note Bedetheque, compteur de tomes sur une fiche Série, sous-titres de section — jamais sur le texte courant. Reprise d'une maquette de comparaison fournie par l'utilisateur.
- **Barre latérale élargie** (220px → 250px), toujours suite à la même maquette.
- **En-têtes de section harmonisés** ("Poursuivre la lecture", "Albums ajoutés récemment", "Sélection", "Vos séries", "Genres" sur l'accueil ; "Séries similaires"/"Du même scénariste"/"Du même dessinateur" sur la fiche Série) : sous-titre en mono indiquant un compte, lien "Tout voir" vers la page correspondante quand elle existe.
- **Barre de statistiques de l'accueil simplifiée** : les icônes sont retirées, ne restent que le nombre et le libellé par segment.
- **Voile du bandeau d'accueil** recoloré en brun chaud plutôt que noir pur, plus cohérent avec le reste de la charte.
- Raccourci **Cmd/Ctrl+K** de la recherche restylé (coins, taille, graisse) pour matcher la maquette ; texte du placeholder de recherche précisé ("Rechercher un album, une série, un auteur…").
- Fiche Série : résumé du hero limité à 181 caractères sur desktop (évite d'étirer la hauteur du bandeau avec un résumé long), largeur de la colonne de texte réduite (640px → 600px), logo réduit de 20% (272×120, contre 340×150).
- Fiche Série : les trois listes "Séries similaires" / "Du même scénariste" / "Du même dessinateur" sont désormais **dédupliquées entre elles** (une série qui partage déjà le genre n'apparaît plus aussi dans "même scénariste") ; largeur des cartes réajustée (100px → 132px, la première valeur étant trop agressive).

### Corrections

- **Survol des cartes de l'accueil incohérent avec le reste de l'app** : "Vos séries" (logos), "Poursuivre la lecture" et les rangées défilantes ("Sélection"/"Résultats") utilisaient un simple agrandissement d'ombre au survol, sans l'anneau coloré (`box-shadow` 1.5px + ombre) utilisé partout ailleurs (Albums, Séries, tomes d'une fiche Série) — uniformisé sur les trois.

### Contexte

Suite directe de la session v1.20.0 : l'utilisateur a fourni l'export d'une maquette de page d'accueil alternative pour comparaison ("CBZ Manager - Accueil.html"), dont 7 idées ont été retenues et intégrées (police mono, sidebar, en-têtes de section, barre de stats, voile brun, style du raccourci clavier, confirmation que la barre de progression sur cover correspondait déjà). Complété par une passe de relecture ("qu'améliorerais-tu sur la fiche Série et l'accueil ?") ayant mené à la déduplication des séries similaires et à l'harmonisation des en-têtes restants, puis par la correction du survol des cartes de l'accueil signalée en dernier.

### Validation

Vérifié par lecture de code (comparaison directe des règles `:hover` entre les cartes de l'accueil et le pattern standard déjà utilisé sur Albums/Séries/fiche Série) et déploiement, sans outil de navigateur pour confirmation visuelle finale.

---

## v1.20.0 — 2026-09-10 — Tome suivant façon Netflix, séries similaires, corrections logo/genres

### Nouveau

- **Lecteur : proposition du tome suivant en fin d'album**, façon Netflix — cover, titre, bouton "Lire la suite →" ou "Rester ici". Se déclenche en tentant d'avancer depuis la dernière page (flèche, espace, tap, bouton ›), chargé en tâche de fond pendant la lecture pour ne rien faire attendre à ce moment-là.
- **Fiche Série : "Séries similaires"**, **"Du même scénariste"**, **"Du même dessinateur"** — trois nouvelles rangées en bas de page, calculées côté client à partir des données déjà chargées (aucun nouvel appel réseau), masquées individuellement si aucune correspondance. Comparaison insensible à la casse/accents pour ne pas rater de correspondances dues à des incohérences de saisie entre fichiers (ex. "Humour" vs "humour").
- Page Séries : **filtre Genre** enfin branché (existait dans le store et était mentionné en commentaire depuis un moment, jamais complété) — champ visible dans le panneau de filtres, comme sur la page Albums.
- Accueil : les pastilles "Genres" renvoient maintenant vers la page **Séries** plutôt qu'Albums (cohérent avec le comptage par nombre de séries), et s'affichent sur une seule ligne défilable au lieu de passer à la ligne.

### Corrections

- **Logo de fiche Série qui s'affichait bien trop grand** pour un logo au contenu carré/vertical (ex. un fond de canevas 1000×400 dont le dessin réel n'occupe qu'une zone proche du carré une fois les marges transparentes rognées) : le bandeau entier gonflait en hauteur. Remplacé par un cadre à hauteur fixe (150px, calé sur le rendu réel d'un logo large déjà validé) : la hauteur du bandeau ne dépend plus jamais de la forme du logo, un logo carré s'affiche simplement plus petit à l'intérieur — plusieurs itérations pour trouver la bonne valeur (140 → 90 → 64 → 150px, les plus basses rétrécissaient aussi des logos larges qui n'avaient jamais posé problème).
- Bordure du haut rognée sur les pastilles "Genres" (effet de bord de `overflow-x:auto`, qui force `overflow-y:auto` et peut rogner 1px sur un enfant collé au bord du conteneur).
- Cartes "Séries similaires" : bordure manquante et texte souligné au survol — utilisaient `<router-link>` (hérite du style de lien global, `a:hover{text-decoration:underline}`), remplacé par le pattern standard div + clic déjà utilisé par les autres cartes de série de l'app.

### Contexte

Suite directe de la session v1.19.0. Le tome suivant façon Netflix et les séries similaires sont des demandes de fonctionnalités nouvelles ; le reste de la session a été consacré à corriger, sur plusieurs allers-retours avec retours visuels précis de l'utilisateur, le dimensionnement du logo de fiche Série (introduit par erreur en voulant corriger un premier bug de logo surdimensionné) et de petits écarts de présentation sur les nouvelles cartes de séries similaires par rapport au reste de l'app.

### Validation

Tome suivant vérifié end-to-end avec de vraies données (tome 92 → tome 93 d'une série réelle, correctement identifié). Dimensionnement du logo recalculé à chaque itération à partir des dimensions réelles des fichiers logo concernés (mesurées directement, pas estimées). Reste vérifié par lecture de code et déploiement, sans outil de navigateur pour confirmation visuelle finale.

---

## v1.19.0 — 2026-09-10 — Bannière d'accueil en slider "livre 3D", statistiques, genres

### Nouveau

- **Bannière d'accueil transformée en slider** : parcourt les derniers albums ajoutés (au lieu d'un seul, tiré au hasard), défilement automatique toutes les 6 secondes, flèches gauche/droite au survol et points de pagination sous les boutons d'action. Fond de la série en plein cadre (recadré, pas déformé) avec un voile noir dégradé pour la lisibilité du texte (blanc désormais).
- **Cover de l'album en montage "livre 3D"** dans la bannière : la cover réelle est plaquée sur un mockup de couverture (cadre + tranche + léger ombrage), calibré pixel par pixel puis reconstruit en 3 calques CSS légers (cadre + dégradé fixes, ~70 Ko au total pour toute la session, chargés une seule fois) plutôt qu'une image composée à la volée côté serveur (ancienne approche abandonnée : 2 à 4 Mo générés et mis en cache par album).
- **4 cartes statistiques** sous la bannière : Albums, Séries, Auteurs, Éditeurs, avec icône et lien vers la page correspondante.
- **Section "Genres"** : les genres les plus représentés de la bibliothèque (comptés par nombre de séries), sous forme de pastilles cliquables filtrant la page Albums.
- Section "Redécouvrir" renommée **"Sélection"** (icône retirée) ; section "Séries récentes" retirée de la navigation (redondante avec "Albums ajoutés récemment"), ne s'affiche plus que comme résultats de recherche.
- Nouvel ordre des sections de l'accueil : Bannière, Statistiques, Poursuivre la lecture, Vos séries, Albums ajoutés récemment, Sélection, Genres.
- **Format d'image de fond de série recalibré** : passage du ratio 2:1 (1200×600) à 4:1 (1600×400), qui réduit fortement la coupure visible sur la fiche Série à la plupart des largeurs d'écran courantes (le dégradé de masquage a été recalculé en conséquence).
- Lecteur : **Échap ferme la popup "Reprendre la lecture ?"** et redémarre l'album depuis le début (au lieu de quitter le lecteur).
- Icône du raccourci Ctrl/Cmd+K légèrement repositionnée dans la barre de recherche.

### Corrections

- **Page d'accueil blanche pour un compte connecté** : un `watch()` référençait une valeur avant sa déclaration plus bas dans le fichier, ce qui faisait planter le composant dès son montage (page de login non affectée, seule la page d'accueil authentifiée était concernée).

### Contexte

Session longue partie d'une simple demande de bannière "nouveautés" avec maquette, qui a mené à explorer un montage 3D de la cover sur un mockup fourni par l'utilisateur (plusieurs itérations de mockups et de calibrage au pixel près), avant de simplifier l'implémentation en calques CSS statiques une fois le mockup final validé (gain : plus de génération serveur, taille divisée par ~40). En cours de route, ajout de statistiques et d'une section Genres suite à des demandes de mise en avant du contenu de la bibliothèque, et découverte + correction d'un bug de démarrage bloquant (JS "temporal dead zone") introduit par un refactor intermédiaire.

### Validation

Rendu du montage 3D vérifié par génération et inspection directe des images (crops de coins, comparaison pixel à pixel avec le mockup de référence). Bug de page blanche reproduit et corrigé par lecture de code (ordre de déclaration), confirmé résolu par l'utilisateur. Recalibrage du dégradé de fond de série (nouveau ratio 4:1) vérifié par le calcul à partir des mesures déjà documentées dans le code, non vérifié visuellement au-delà de la résolution de référence (pas d'outil de navigateur dans cette session).

---

## v1.18.0 — 2026-09-06 — Bannière d'accueil, correction d'une fuite de données entre comptes

### Nouveau

- **Bannière d'accueil repensée** : image de fond piochée aléatoirement parmi celles déjà fournies pour une fiche série, avec le même fondu que les fiches Série (recalculé pour rester correct à toute résolution d'écran, voir Corrections). "Bonjour/Bonsoir Prénom !" en petit au-dessus, "Bonne lecture !" en gros titre, une phrase d'accroche, et les cartes Séries/Albums à l'intérieur de la bannière. Repli sur un dégradé de marque si aucune série n'a encore fourni de fond.
- Page Diagnostic uniformisée sur le modèle de la page Historique : lignes blanches (seule la sévérité reste un badge coloré), ligne de filtres sous les en-têtes de colonnes (Sévérité, Problème, Série, Album, Format, Détail), réinitialisables en un clic.
- Page Albums manquants : barre "Rechercher…/Trier par" (comme Auteurs), une série par ligne avec ses albums manquants en rangée à défilement horizontal, action "Ignorer cette série" en lien discret.
- "Compléter depuis Bedetheque.com" (fiche série) récupère désormais aussi l'ISBN et le lien vers la fiche Bedetheque de chaque album, en plus de Titre/Scénariste/Dessinateur/Éditeur/Année.
- Accès par Public : plus d'option "Illimité" pour un compte non-admin (nouveaux comptes en "Tout public" par défaut, comptes existants migrés) ; "Adultes" renommé "Adultes (illimité)" côté Comptes et rendu vraiment illimité (voit aussi les séries pas encore classifiées, comme un admin).
- Nouvelle classification "Livres illustrés" (proche BD, ex. séries jeunesse comme *Les p'tites poules*).
- Import : le bouton "Créer"/"Créer quand même" de la popup de confirmation de nouvelle série est grisé tant que la recherche Bedetheque.com est en cours.
- Petites retouches Comptes : ordre du menu Rôle corrigé (Aucun, Lecteur, Contributeur, Administrateur), bouton "Historique" en texte plutôt qu'en icône, confirmation de suppression affichant le nom du compte.

### Corrections

- **Fuite de données entre comptes dans le même onglet** : changer de compte (déconnexion puis reconnexion sous un autre utilisateur) ne rechargeait jamais la page — les données mises en cache de la session précédente (smart lists privées, séries visibles selon l'ancien compte...) pouvaient rester affichées jusqu'à ce que chaque partie de l'app pense à se rafraîchir séparément. Connexion et déconnexion déclenchent maintenant un rechargement complet, comme le fait déjà l'app en cas de session expirée.
- Démarcation visible sur le fond des bannières (fiche série et accueil) : le dégradé était calé sur un seul ratio d'image de référence, et se désynchronisait dès qu'une image avait un ratio différent. Comme toutes les images fournies par l'utilisateur ont la même taille (1200×600), le point de départ du dégradé a pu être recalculé précisément par palier de largeur d'écran (résolution de référence inchangée, trois paliers supplémentaires ajoutés pour les écrans plus larges, jusqu'au 4K).
- Ordre du sélecteur de profils (page Comptes) : trié par ordre de création plutôt qu'alphabétique, qui inversait Contributeur/Lecteur.

### Contexte

Suite directe de la session v1.17.0 (accès par Public, uniformisation des pages), poursuivie par une nouvelle bannière d'accueil demandée avec maquette à l'appui, puis plusieurs itérations sur le dégradé de fond suite à des retours visuels précis de l'utilisateur (démarcation visible, mauvaise adaptation 4K). Au passage, un signalement de l'utilisateur ("une smart list privée semble quand même partagée") a mené à l'identification d'un bug plus large et plus important que son symptôme initial : les stores Pinia ne se réinitialisaient jamais entre deux connexions dans le même onglet.

### Validation

Bug de fuite de données reproduit et confirmé par lecture de code (query de visibilité des smart lists testée directement contre une copie de la base, confirmée correcte — le bug était côté cache navigateur, pas dans la requête serveur). Formule du dégradé vérifiée par le calcul (dimensions d'image réelles lues sur le volume de données) mais non vérifiée visuellement au-delà de la résolution de référence déjà validée par l'utilisateur (pas d'outil de navigateur/écran 4K disponible cette session).

---

## v1.17.0 — 2026-09-06 — Accès par Public, Comptes/Profils repensés, uniformisation des popups et des pages

### Nouveau

- **Accès par Public** (Tout public / Ados / Adultes) : nouveau réglage par utilisateur (`age_rating_limit`), combiné à un champ Public par série. Un utilisateur restreint ne voit pas les séries d'un public supérieur ; une série sans Public défini est traitée comme la plus restrictive (masquée par défaut) plutôt que visible par erreur. Appliqué à tous les points d'accès à la bibliothèque (listes Séries/Albums, smart lists, accès direct à un album/une série), pas seulement aux fiches individuelles.
- **Page Comptes** repensée en liste + détail : avatar coloré par utilisateur, mot de passe visible/masqué à la saisie, réinitialisation de mot de passe directement par un admin, rôle/Public/permissions avancées regroupés en interrupteurs. L'onglet **Profils** a reçu le même traitement (liste + détail, mêmes interrupteurs).
- **Popups d'édition Album et Série harmonisées** : passage d'un formulaire à onglets/labels denses à des sections en cartes, auteurs saisis en badges (au lieu de texte libre), même largeur (700px), mêmes libellés allégés des deux côtés. "Éditer en lot" (sélection multiple d'albums) a reçu le même traitement.
- **Échap désélectionne** une sélection multiple d'albums ou de séries (pages Livres, fiche Série, Séries) — sauf si une popup est encore ouverte au-dessus, auquel cas elle se referme d'abord.
- Repère visuel (ligne + point, façon arborescence) pour les Smart lists du menu latéral, signalant qu'elles sont rattachées à "Smart list" plutôt que des entrées de premier niveau.
- Cartes d'info de la fiche série (Classification/Public/Note Bedetheque.com/Fiche externe) et de la fiche album (Ajouté/Modifié/Format/Résolution) réunies en une seule carte à séparateurs discrets, au lieu de 4 cartes séparées.
- Pages **Auteurs** et **Albums manquants** : barre "Rechercher…/Trier par" harmonisée (icône de recherche, tri par nom ou par quantité) ; alignement et largeur de page uniformisés avec Statistiques/Importer. Albums manquants : chaque série affiche désormais ses albums manquants sur une rangée à défilement horizontal (au lieu d'une grille qui s'enroulait sur plusieurs lignes), avec une action "Ignorer cette série" discrète.
- Marges transparentes des logos de fiche série rognées automatiquement à l'upload (utile pour des fichiers logo uniformisés à un même canevas par l'utilisateur) — la carte hero suit désormais la taille réelle du logo plutôt que celle du fichier source.

### Corrections

- Job d'analyse complète (page Diagnostic) resté bloqué "en cours" indéfiniment après un redémarrage du serveur pendant qu'il tournait — nettoyé automatiquement au démarrage.
- Alignement des champs Scénariste/Dessinateur/Éditeur dans la popup album : un badge d'auteur un peu long faisait passer le champ voisin sur deux lignes, désalignant les libellés entre eux.
- "Bonjour/Bonsoir Prénom," : virgule remplacée par un point d'exclamation avec espace ("Bonjour Prénom !").

### Contexte

Session très longue, ouverte par l'ajout du contrôle d'accès par Public puis étendue en une revue systématique des popups d'édition (Album/Série/Éditer en lot) et de plusieurs pages de navigation principale (Auteurs, Albums manquants, Statistiques, Importer, Comptes) pour aligner leurs conventions — couleurs d'onglets, largeur/alignement de page, style de barre de recherche/tri — sur le standard déjà établi ailleurs dans l'app. Nombreux allers-retours pilotés directement par les retours visuels de l'utilisateur (captures d'écran, maquettes fournies) en l'absence d'outil de navigateur côté agent.

### Validation

Contrôle d'accès par Public testé sur une copie isolée de la base réelle (script direct puis `TestClient` FastAPI avec dépendances substituées) avant migration sur la base réelle. Chaque lot de modifications visuelles reconstruit et redéployé localement (health check + vérification des logs) avant de passer au suivant.

---

## v1.16.0 — 2026-09-01 — Fiches Série/Album repensées, statut "Lu"

### Nouveau

- **Statut "Lu"** sur chaque album : coché automatiquement dès que la lecture atteint 95% des pages, ou basculé manuellement (icône dédiée sur la fiche album). Jamais décoché tout seul — une relecture qui repasse le seuil ne fait que confirmer, un décochage manuel n'est jamais écrasé par la suite. Un album Lu n'affiche plus de barre de progression ni de "Reprendre la lecture" (redevient "Lire"), sort de "Poursuivre la lecture" sur l'Accueil, et rouvrir le lecteur repart de la page 1 plutôt que de proposer de reprendre près de la fin. Migration avec pré-remplissage automatique pour les albums déjà terminés avant ce changement (sinon ils seraient tous réapparus d'un coup dans "Poursuivre la lecture").
- **"Vos séries"** sur l'Accueil : rangée défilable des logos de fiche uploadés (voir ci-dessous), cliquables vers leur série — essayée d'abord en bandeau qui défile tout seul, puis à côté des cartes de stats, avant de se fixer en simple rangée de cartes comme les autres sections de la page (plus cohérent avec le reste).
- Boutons d'action des fiches Série et Album simplifiés : un seul bouton principal texte ("Éditer" / "Lire"), le reste en icônes seules (Métadonnées, Télécharger, Lu, Plus d'options...). La bascule "Reprendre TXX" qui prenait la place du bouton principal sur la fiche série a été retirée (jugée incohérente pour une série entière).
- Fiche Album alignée sur la fiche Série : bandeau "hero" avec logo/dégradé de la série parente, ligne méta texte (genre • année • pages), crédits en colonnes, cartes d'info uniformes (Ajouté/Modifié/Format/Résolution), section "Plus dans cette série" passée en grille de vraies cartes (au lieu d'une rangée de miniatures à défiler) et complétée avec les albums manquants du suivi Bedetheque (absents jusqu'ici).
- Upload des images de fiche série (fond/logo) revu dans la modale d'édition : cadres de même taille, cliquables sur toute leur surface pour importer/remplacer, sans bandeau d'action séparé.

### Corrections

- Filet anti-image-cassée sur les logos/fonds de fiche : un fichier disparu du disque (compteur de version désynchronisé) affichait un cadre cassé ou du texte brut au lieu de retomber proprement sur le dégradé/titre de repli.
- Fond de la fiche série : dégradé de fondu revu pour ne plus laisser voir la démarcation entre l'image fournie et le reste du bandeau (pente de transition adoucie), et masqué sur mobile où le recadrage pensé pour desktop rendait mal.
- Bug d'affichage "Tome 01 / 1" au lieu de "Tome 01 / 01" (numéro total non complété à 2 chiffres).
- Menu "Plus d'options" de la fiche album mal positionné (double `overflow:hidden` qui le découpait — un calque en trop en plus de celui déjà prévu pour ce cas).
- Espace manquant dans "Bonsoir Prénom," sur l'Accueil ("BonsoirPrénom,") — cas limite du compilateur Vue qui supprime les nœuds texte ne contenant qu'un espace en tout début de bloc conditionnel.
- Cartes "Albums ajoutés récemment" sur l'Accueil : n'avaient pas le même habillage (fond blanc, bordure, graisse du titre) que les autres grilles d'albums de l'app.
- Idée du personnage détouré sur la fiche album abandonnée après essai (retirée de l'interface).

### Contexte

Session de polissage visuel étendue sur les fiches Série et Album, ouverte par une comparaison directe avec les maquettes explorées lors d'une session précédente (`design-tests/`) et poursuivie par de nombreux allers-retours sur le ressenti (dégradés, tailles d'image, alignement des boutons, gras des libellés) directement pilotés par les retours de l'utilisateur au fil des déploiements. Une tentative de calcul dynamique (mesure réelle des dimensions image/bandeau via `ResizeObserver` pour positionner le fondu du fond automatiquement) a été revertée après avoir produit un résultat pire que le réglage statique qu'elle remplaçait — faute de pouvoir vérifier visuellement le rendu dans cette session (pas d'outil navigateur disponible), le réglage est resté statique, ajusté par itérations successives sur des pourcentages donnés par l'utilisateur.

### Validation

Chaque lot de modifications reconstruit et redéployé localement (health check + vérification des logs après coup) avant de passer à la suivante. Nouveau champ `is_read` testé de bout en bout sur une copie de la base réelle (passage à 95% → bascule auto → exclusion de "Poursuivre la lecture" → décochage manuel → re-vérifié) avant migration sur la base réelle ; migration avec pré-remplissage vérifiée sans erreur au démarrage du conteneur réel. Aucun outil de navigateur disponible cette session : tous les ajustements visuels ont été validés via les retours directs de l'utilisateur après chaque déploiement plutôt qu'une inspection visuelle propre.

---

## v1.15.1 — 2026-08-31 — Zoom sur les cases (lecteur), correction d'une fuite de données utilisateur

### Nouveau

- **Zoom sur les cases** (lecteur, option désactivée par défaut) : détection automatique des cases d'une page (modèle YOLO léger, ONNX + `onnxruntime`, ~85 Mo ajoutés à l'image Docker) et navigation case par case au lieu de page par page — pensé mobile en priorité. Chaque case est cadrée avec une marge (jamais coupée), toujours recentrée à l'écran, le reste de la page assombri pour concentrer l'attention ; passage d'une case à l'autre instantané (sans glissement). Arriver sur une nouvelle page affiche d'abord la page entière avant de zoomer sur la première case. Résultats mis en cache par page (jamais recalculés deux fois).
- **Tri des séries insensible à l'article de tête** : "Le Scrameustache" trie désormais au S, pas au L (idem La/Les/L'/Un/Une) — sans jamais toucher au nom affiché ni stocké. Appliqué partout où les séries sont triées par nom (page Séries, accueil, sélecteurs de série, Albums manquants, vue "regroupé par série").
- **Historique par compte** : icône sur la fiche de chaque utilisateur (page Comptes), ouvre l'Historique déjà filtré sur ce compte.
- **Champ "Année" dans l'assistant d'import** : la table de métadonnées par fichier (étape 2) n'avait pas de colonne pour la date — elle n'était renseignée que via "Rechercher les métadonnées". Ajoutée à côté du numéro, saisissable comme les autres champs.

### Corrections

- **Bug important — fuite de données utilisateur entre albums** : supprimer un album ou une série n'effaçait jamais sa progression de lecture, note ou notes texte (ni les séries masquées individuellement, ni les albums manquants ignorés) — ces lignes restaient orphelines en base et pouvaient se rattacher silencieusement à un nouvel album si l'identifiant interne était réutilisé (signalé par l'utilisateur : réimporter un album juste après l'avoir supprimé faisait réapparaître son ancienne progression de lecture). Corrigé à la source (relations manquantes dans les modèles), valable pour les 4 façons de supprimer un album/une série dans l'app. Vérifié : aucune donnée orpheline dans la base réelle au moment du correctif.
- Largeur des pages de Configuration harmonisée (Bibliothèque/Comptes/Diagnostic/Historique/À propos/Mon compte) — chacune avait sa propre valeur (680 à 900px), désormais 1100px partout, cohérent avec les pages à tableau qui en avaient besoin.
- Page "Gérer le suivi" (Albums manquants) : la liste des séries exclues/albums ignorés était limitée à 420px de large sans rapport avec la largeur réelle de la page.
- Icônes corrigées : `square-plus` (ajout d'un album manquant) et `fullscreen` (plein écran classique, qui contenait en fait le tracé de l'icône "maximize" — bug préexistant, découvert à cette occasion) remplacées par leurs tracés Lucide exacts. Le zoom sur les cases a sa propre icône séparée (`panel-zoom.svg`) pour ne plus partager celle du plein écran classique.

### Contexte

Session ouverte par une question exploratoire de l'utilisateur sur un ancien essai (modèle de détection de cases manga testé par le passé, jamais intégré) — proposition retenue après un test de faisabilité concret (vraie page de la bibliothèque, détection + algorithme de tri en ordre de lecture "xy-cut" vérifiés visuellement) montrant un résultat fiable et un poids raisonnable une fois converti en ONNX. L'intégration dans le lecteur a connu plusieurs itérations directement pilotées par les retours de l'utilisateur : premier calcul de zoom basé sur une hypothèse fausse (l'image affichée suppose à tort remplir tout le cadre) corrigé par un calcul basé sur des mesures réelles du DOM ; puis ajustements successifs sur le ressenti (case trop zoomée → marge ajoutée, glissement visible → transitions supprimées, absence de contexte → page entière affichée avant le zoom). En parallèle, une question de l'utilisateur sur un comportement observé après suppression/réimport d'un album a mené à la découverte d'un bug de fuite de données plus large que le cas signalé (3 tables concernées, 4 points de suppression dans le code).

### Validation

Zoom sur les cases : détection + tri testés sur de vraies pages de la bibliothèque (franco-belge, mise en page irrégulière), build croisé amd64 (cible Synology réelle) testé sous émulation. Calcul de cadrage revérifié algébriquement à la main après le premier correctif (aucun outil de navigateur disponible dans cette session pour une vérification visuelle directe — confirmé fonctionnel par l'utilisateur après déploiement). Fuite de données utilisateur : reproduite puis corrigée pour les 4 endpoints de suppression (album seul, suppression en lot, série seule, séries en lot), vérifiée sur la base réelle (aucune ligne orpheline actuellement). Build frontend + compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.15.0 — 2026-08-30 — Ajout d'albums manquants depuis leur fichier, fiabilité de l'import CBR

### Nouveau

- **Ajout d'un album manquant depuis son fichier** : sur la page "Albums manquants" et sur la fiche d'une série, chaque cover d'album manquant propose désormais un bouton d'upload (au survol, même présentation que les autres pages — cover assombrie, icône lien externe centrale, icône d'ajout en bas à droite). Ouvre une popup simplifiée : sélection du fichier (glisser-déposer), nom proposé automatiquement (éditable), conversion en CBZ si nécessaire (qualité HQ par défaut). Le titre, le numéro, l'année, le scénariste, le dessinateur, l'éditeur et l'URL Bedetheque déjà connus sont écrits directement dans le ComicInfo.xml du fichier importé — plus besoin de les ressaisir.
- **Repli automatique sur le ComicInfo.xml** pour le titre/numéro d'un album quand le nom de fichier n'en fournit pas (ex. "Série - T15.cbz" volontairement sans titre en double avec le numéro) — bénéficie à tous les scans et imports, pas seulement à la nouvelle popup.
- **Effet de tranche cartonnée** sur la cover de la fiche album (dégradé CSS simulant le pli d'une couverture rigide).

### Corrections

- **Bug important — CBR/PDF pouvant devenir illisible après un import avec conversion** : le fichier était renommé en `.cbz` dès l'upload, avant que la conversion n'ait réellement réencodé son contenu ; si la conversion échouait pour une raison quelconque, le fichier restait indéfiniment un CBR (ou PDF) déguisé en CBZ — 0 page, aucune métadonnée, cover cassée, sans qu'aucune erreur ne soit visible. Corrigé à la source (l'upload initial garde désormais l'extension réelle du fichier, seule la conversion réussie renomme en `.cbz`) et en profondeur (scan, conversion, cache de couverture et lecteur détectent maintenant le format réel par les octets magiques du fichier plutôt que par son extension, au cas où un fichier mal étiqueté existerait déjà).
- **Annulation d'un import** : l'endpoint de nettoyage ne supprimait que les fichiers sur disque, jamais les lignes `Tome`/`Série` déjà créées en base au moment de l'upload — un import annulé laissait des albums fantômes visibles jusqu'au scan complet suivant. Réutilise désormais la même suppression complète que "Supprimer l'album" (fichier + cache cover + base + série vide).
- Deux barres de progression affichées en même temps sur la page "Albums manquants" pendant un scan (une globale dans l'en-tête de l'app, une seconde identique sur la page) — la barre de la page a été retirée, celle de l'en-tête suffit et reste visible même en changeant de page.
- Icône "lien externe" au survol d'une cover d'album manquant : mauvais tracé SVG (reconstitué de mémoire), remplacé par le tracé exact de l'icône Lucide.
- Badge de format (CBZ/CBR/PDF) masqué désormais pour les CBZ (99% des fichiers) sur les pages Albums — n'apportait rien pour le cas très majoritaire.
- Badge "année" affiché à la place de la classification de série sur les covers des pages Albums (la classification, ex. "BD franco-belge", débordait et cassait l'affichage) — même traitement en badge sur la page "Albums manquants".
- Galerie d'avatars (page Mon compte) : grille en 5 colonnes × 2 lignes avec plus de marge, bouton "Importer une photo" (au lieu de "Changer la photo"), bouton "Supprimer la photo" plus explicite, indications simplifiées sous Identifiant et Mot de passe. Nombre d'avatars prédéfinis resynchronisé avec les fichiers réellement présents (11 → 10).

### Contexte

Session partie d'un ajustement mineur (nombre d'avatars prédéfinis) puis d'une série de polissages visuels (grille d'avatars, badges de cover, effet de tranche cartonnée). Le sujet principal est venu d'une question sur les fonctionnalités restantes du backlog : l'utilisateur a choisi de corriger l'annulation d'import (bug connu, listé de longue date), ce qui a mené à la question "et si on pouvait uploader un album directement depuis Albums manquants ?" — fonctionnalité construite en réutilisant au maximum l'existant (upload + conversion déjà présents pour l'import classique). Plusieurs tours d'essais réels par l'utilisateur ont révélé des bugs successifs : métadonnées manquantes (Writer/Penciller/Publisher jamais persistés côté scan Bedetheque, Series/Web jamais envoyés, Titre supprimé à tort des métadonnées du fichier), confusion entre l'ID interne d'un tome et son numéro de tome (texte "Tome {id}" affiché tel quel dans la barre de progression de conversion), deux barres de progression dupliquées. Le test d'un vrai fichier CBR par l'utilisateur a ensuite révélé le bug le plus significatif de la session (extension `.cbz` appliquée avant conversion réelle), diagnostiqué par inspection directe de la base de données réelle et du fichier concerné (octets magiques "RAR archive data" sous un nom `.cbz`).

### Validation

Chaque changement vérifié via un serveur de développement isolé (copie temporaire, jamais la base réelle) : annulation d'import (nouvelle série entièrement annulée, tome partiel annulé avec recalcul du compteur de série, sidecar `.meta.json` nettoyé, fichier orphelin, rejet d'un chemin hors bibliothèque) ; upload depuis Albums manquants (métadonnées Titre/Série/Numéro/Année/Auteurs/Éditeur/URL correctement écrites dans le ComicInfo.xml, repli titre/numéro depuis ComicInfo quand absent du nom de fichier sans jamais écraser un titre déjà déduit du nom de fichier, détection de doublon de nom) ; bug CBR reproduit avec le fichier réel de l'utilisateur (octets magiques détectés correctement malgré l'extension trompeuse, conversion aboutissant à un CBZ valide de 91 pages) — `unar` installé localement pour permettre ce test, absent jusqu'ici de l'environnement de développement. Inspection en lecture seule de la base de données réelle à plusieurs reprises pour diagnostiquer des rapports de bugs précis de l'utilisateur (numéros de tome, métadonnées, historique des scans). Build frontend + compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.14.0 — 2026-08-29 — Smart lists, classification des séries, galerie d'avatars

### Nouveau

- **Smart lists ("Listes intelligentes")** : nouveau système de listes dynamiques, recalculées à la demande (jamais de contenu figé à rafraîchir). Générateur de règles en 3 étapes (Informations → Filtres → Vérification) : liste plate de conditions reliées par des connecteurs ET/OU par ligne (ET plus prioritaire, évalué de gauche à droite — même convention que les smart playlists Plex/iTunes), portant sur trois sources (Fichier, Métadonnées, Série) avec des opérateurs adaptés au type de champ (texte/numérique/date/booléen). Suggestions de valeurs déjà utilisées dans la bibliothèque (genre, auteurs, éditeur, étiquettes) et badges de départ rapide (One-shot, Sans genre, Sans classification, Ajouté récemment).
  - **Résultat Albums ou Séries** : une liste peut afficher soit les albums correspondants, soit une tuile par série ayant au moins un album correspondant — mêmes règles dans les deux cas, seule la présentation change (avec rappel explicite dans l'interface de cette sémantique "au moins un album suffit").
  - **Partage** : n'importe quel utilisateur peut créer une liste partagée à tous ; seuls le propriétaire et l'administrateur peuvent la modifier ou la supprimer, mais dupliquer une liste visible (même partagée par quelqu'un d'autre) est ouvert à tous et crée une copie privée éditable.
  - **4 listes par défaut** semées au premier démarrage (BD franco-belge, Comics, Manga, One-shot), partagées et modifiables comme n'importe quelle autre liste.
  - Intégration dans la barre latérale : section dépliable "Smart list" (repliée par défaut) juste après Albums, réordonnable par glisser-déposer, avec popover flottant en mode sidebar réduite (icônes seules).
- **Classification des séries** (BD franco-belge / Comics / Manga / Manhwa / Manhua / Autre) : champ éditable sur la fiche série, hérité automatiquement par ses albums (jamais dupliqué en base), filtrable sur les pages Séries et Albums. Modifier uniquement la classification n'entraîne plus de réécriture des fichiers CBZ de la série (court-circuit dès que c'est le seul champ modifié).
- **Galerie d'avatars** : 11 avatars prédéfinis proposés en plus de l'upload personnalisé, appliqués via le même pipeline que les photos importées (recadrage carré centré, redimensionnement 256×256).
- **OPDS-PSE** (Page Streaming Extension) : les catalogues OPDS exposent désormais un flux page par page par album, pour les apps de lecture compatibles (Chunky/Ubooquity). Extraction de page mutualisée entre le lecteur web et OPDS (nouveau service partagé, plus de code dupliqué entre les deux).
- **Connexion insensible à la casse** : l'identifiant ("Admin" / "admin" / "ADMIN") n'est plus distingué à la connexion ni à la création de compte — seul le mot de passe reste strictement sensible à la casse. Évite les échecs de connexion déroutants dus à l'autocapitalisation mobile ou à Verr. Maj, et empêche de créer par erreur deux comptes distincts qui ne diffèrent que par la casse.

### Corrections

- **Diagnostic** : les fichiers CBZ/CBR/PDF corrompus (déjà détectés par le scan de doublons via hachage de contenu) remontent désormais comme une alerte dédiée sur la page Diagnostic, au lieu de n'apparaître nulle part.
- **Notifications persistantes** : le menu "Nouveautés" garde les 10 derniers éléments même après consultation (la pastille de compteur seule repasse à zéro), au lieu de se vider entièrement au premier clic.
- **Extension affichée lors d'une conversion à l'import** : la colonne "Fichier" et l'aperçu "Convertir en CBZ" affichaient l'extension du fichier source (ex. `.pdf`) même quand la conversion vers `.cbz` était cochée.

### Contexte

Session longue partie de deux questions ponctuelles (compatibilité OPDS 1.2 vs 2.0, déjà traitée avant ce rituel — voir suite ci-dessous) puis d'une discussion sur une classification de bibliothèque (BD/Comics/Manga), qui a naturellement mené à la question du chantier suivant : des listes/collections intelligentes. Contrairement à une v1 minimaliste, l'utilisateur a demandé d'emblée un vrai générateur de règles (groupes ET/OU, plusieurs sources de champs, partage) plutôt que des raccourcis de filtre codés en dur. La présentation de la liste des smart lists dans l'interface a connu de nombreuses itérations directement pilotées par les retours de l'utilisateur au fil de la session : page dédiée avec grille de tuiles abandonnée au profit d'une intégration directe dans la barre latérale (comme une app de lecteur type Kavita), structure "groupes de conditions" simplifiée en liste plate avec connecteur ET/OU par ligne, badges de comptage ajoutés puis partiellement retirés après un bug de superposition avec le bouton d'options qui le rendait impossible à cliquer, bouton "+" déplacé puis ramené à sa position initiale, ordre des entrées du menu ajusté deux fois.

### Validation

Moteur de règles testé unitairement pour chaque opérateur (contient/est/vide/supérieur à/entre...) et chaque source (Fichier/Métadonnées/Série), y compris la conversion aller-retour entre la liste plate éditée côté interface et le format groupes ET/OU du backend (aucune perte d'information vérifiée par test). Endpoints testés de bout en bout sur base isolée : création/édition/duplication/suppression/réordonnancement, droits (propriétaire vs partagé vs autre utilisateur), résultat Albums vs Séries sur les mêmes règles, rejet d'une règle malformée (400) et d'un type de résultat invalide. Connexion insensible à la casse vérifiée (connexion croisée avec casses différentes, création de compte en double bloquée). Build frontend + compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.13.0 — 2026-08-27 — Permissions personnalisées, navigation OPDS étendue, OPDS 2.0

### Nouveau

- **Personnalisation des droits par utilisateur** : à la création ou l'édition d'un compte, un rôle de base (profil existant ou Administrateur) précoche un panneau "Permissions avancées" repliable — décocher/cocher une case personnalise ce compte précis (badge "{Rôle} (Modifié)"), sans avoir besoin de créer un profil nommé juste pour une exception. La personnalisation est un instantané figé : modifier le profil de base plus tard ne change plus rien pour un compte déjà personnalisé. Édition et création partagent désormais le même formulaire (comme l'onglet Profils juste à côté) — modifier les droits d'un compte se fait là où ils ont été saisis la première fois, plus de popup séparée.
- **Accès à Configuration ouvert par permission** : nouveau droit `library.settings` (Bibliothèque > Général, Diagnostic, Historique, À propos) assignable via un profil, sans passer par le statut administrateur. Comptes (création d'utilisateurs) et Sauvegarde & BDD restent volontairement toujours réservés à l'admin — déléguer la création de comptes ouvrirait une auto-élévation de privilèges possible, et la BDD n'a pas de filet de rattrapage.
- **Navigation OPDS étendue** : le catalogue (`/opds`) propose désormais 5 nouveaux axes à côté de "Toutes les séries" — Par genre, Par année, Par scénariste, Par dessinateur, Par éditeur.
- **Catalogue OPDS 2.0** (`/opds2`, JSON `application/opds+json`) ajouté en plus du 1.2 existant (Atom/XML, inchangé) — pour les apps de lecture qui ne parlent que la 2.0. Même arborescence de navigation que le 1.2, réutilise la même authentification et les mêmes endpoints de téléchargement/couverture.

### Corrections

- **Menu "Configuration" affiché à tort pour les non-admins** : le bouton apparaissait pour tout le monde et s'ouvrait au clic sur un sous-menu systématiquement vide (chaque lien étant filtré sur le statut admin) — visuellement indiscernable d'un menu cassé. Masqué désormais pour qui n'a ni le statut admin ni `library.settings`.
- **Changement de mot de passe forcé acceptait le mot de passe identique** : ni le formulaire ni le serveur ne vérifiaient que le nouveau mot de passe différait de l'actuel — on pouvait donc "changer" son mot de passe temporaire en resaisissant exactement le même. Rejeté aux deux niveaux désormais.

### Contexte

Suite du rituel v1.12.0 (albums one-shot) : questions successives de l'utilisateur sur la gestion des droits (pourquoi un profil "tous droits sauf suppression" n'a pas accès à Configuration, faut-il ouvrir la création de comptes à des non-admins — refusé, risque d'auto-élévation) ont mené à trois itérations de prototype avant de retenir un menu déroulant de rôle + panneau de permissions avancées repliable, testées sur des pages dédiées avec données fictives avant intégration réelle. Le sujet OPDS est venu d'un retour d'app de lecture (Chunky) : d'abord la question de la navigation par facettes (déjà supportée par le standard, juste jamais câblée), puis le signalement que le catalogue n'était qu'en version 1.2.

### Validation

Personnalisation des droits testée de bout en bout : création avec droits personnalisés, application réelle vérifiée (permission retirée du profil de base bien bloquée à l'usage, permission conservée passe), retour à un profil standard, promotion admin qui nettoie la personnalisation, rejet d'une clé de permission invalide. `library.settings` vérifié sur un profil sans `library.delete` : accès accordé/refusé exactement comme attendu sur chaque endpoint (réglages, diagnostic, historique) tout en gardant Comptes et Sauvegarde & BDD strictement admin. OPDS 2.0 vérifié : structure des flux, filtrage par genre, téléchargement réel d'un fichier via le lien référencé, flux 1.2 confirmé inchangé en parallèle. Build frontend + compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.12.0 — 2026-08-27 — Albums "one-shot"

### Nouveau

- **Flag "one-shot" par album** (`Tome.is_oneshot`) pour les albums indépendants, sans rapport avec les autres tomes de leur dossier (typiquement un dossier "One Shot" regroupant plusieurs one-shots comme une pseudo-série). Bascule immédiate depuis la fiche d'édition d'un album, ou dès l'import (case par ligne + "Tout marquer one-shot" en lot à l'étape 2 de l'assistant).
- Conséquences câblées partout où c'est pertinent : badge "One-shot" à la place de "T{numéro}" (page album, page série, page Albums, popup d'édition), requête de recherche en ligne par défaut sur le titre propre plutôt que série+numéro, exclusion du classement "Top séries" des statistiques, renommage forcé sur le motif `{Titre}` seul quel que soit le modèle configuré.
- **Filtre "One-shot uniquement"** ajouté au menu de filtres de la page Albums.
- Popup d'édition d'un album : champ Numéro grisé et vidé automatiquement dès que "One-shot" est coché (un one-shot n'a pas de numéro de tome) ; case positionnée sur la même ligne que Numéro, avec une icône ⓘ pour le texte explicatif plutôt qu'une ligne dédiée.
- Étape 2 de l'import : champ Série ignoré/vidé pour une ligne one-shot, y compris lors d'une recherche en ligne (Bedetheque crée une page "série" du même nom que l'album pour chaque one-shot, ce qui polluait sinon ce champ) ; l'aperçu de nom final (colonne Fichier + section Convertir/Recompresser) applique désormais la même règle que le renommage réel côté serveur.

### Corrections

- **Popup d'édition d'un album ouverte depuis une fiche série** : la case "One-shot" apparaissait toujours décochée même quand l'album était correctement flaggé en base — `GET /api/series/{id}` construisait ses `TomeOut` à la main sans jamais inclure `is_oneshot`, contrairement aux autres endpoints qui passent tous par le même constructeur commun.
- **Notifications (icône cloche)** : ouvrir le menu déroulant vidait immédiatement la liste avant même de l'afficher (« Rien de nouveau pour l'instant » alors qu'un badge venait de signaler du contenu) — `markSeen()` remettait `items` à vide en même temps que le compteur, au lieu de laisser la liste visible et de la laisser se vider naturellement au prochain rafraîchissement.
- **Barre de sélection multiple (page Série)** : "Annuler la sélection" s'intercalait entre les boutons d'action (Éditer, Télécharger) et le menu "..." (Déplacer/Supprimer), rendant l'ensemble peu lisible. Actions regroupées ensemble, "Annuler la sélection" repoussée en toute fin de barre.

### Contexte

Suite du brainstorm sur la gestion des one-shots mené juste avant le rituel v1.11.0 (l'utilisateur stocke tous ses one-shots dans un unique dossier "One Shot", traité par l'app comme une pseudo-série) — implémentation complète de la case à cocher évoquée à l'époque, en plusieurs itérations de placement/comportement affinées au fil des retours de l'utilisateur (position de la case à l'import, alignement dans la popup, nettoyage du champ Série, numéro grisé), plus quelques bugs annexes remontés en testant la fonctionnalité en conditions réelles.

### Validation

Testé de bout en bout sur un environnement isolé (DB fraîche, fichier réel, upload avec le flag coché) : persistance de `is_oneshot` dès l'import, badge/recherche/statistiques/renommage vérifiés individuellement, renommage confirmé forcé sur `{Titre}` malgré un modèle contenant Série/Numéro. Bug `GET /api/series/{id}` confirmé en base réelle (`is_oneshot=1` en DB, absent de la réponse API) puis corrigé et revérifié. Build frontend + compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.11.0 — 2026-08-27 — Revue de sécurité, espace « Mon compte », doublons, catalogue OPDS, réorganisation des réglages

### Sécurité

- **SSRF corrigée** sur 3 endpoints de scraping Bedetheque (`/api/scrape/bedetheque-bulk`, `/api/scrape/bedetheque-album-summary`, `/api/missing-albums/series/{id}/bedetheque-url`) : l'URL fournie par le client n'était vérifiée que par `startswith("http")`, permettant de faire requêter au serveur n'importe quelle adresse du réseau local du NAS. Validation stricte du domaine (`bedetheque.com`/`www.bedetheque.com`) ajoutée aux trois.
- **Contournement du masquage de séries par utilisateur** corrigé sur 6 endpoints qui avaient oublié la vérification (`assert_series_visible`/`assert_tomes_visible`) présente partout ailleurs : masquer/afficher une série, changer sa cover, éditer ses métadonnées, complétion Bedetheque (aperçu + application), conversion. Un utilisateur non-admin pouvait agir sur une série qui lui était censée être invisible, en devinant son identifiant.
- **Brute-force et déni de service sur la connexion** : `/api/auth/login` n'avait aucune limite de tentatives, et la vérification du mot de passe (bcrypt, ~100-300 ms) tournait en synchrone dans l'unique worker de l'app, bloquant toutes les requêtes de tous les utilisateurs pendant chaque tentative. Rate-limiting par IP ajouté, vérification déplacée hors de la boucle d'événements.
- **Identifiants par défaut** : le compte admin créé au tout premier démarrage (`admin`/`admin`) n'était jamais réellement forcé à changer de mot de passe malgré l'existence du champ prévu à cet effet — seulement un badge ⚠ informatif dans le tableau Utilisateurs. Désormais réellement appliqué : redirection bloquante vers Mon compte tant que le mot de passe par défaut ou temporaire n'a pas été changé.
- **Traversal de chemin** sur le réglage `LIBRARY_SUBDIR` (admin) : aucune vérification que le sous-dossier saisi restait dans `MEDIA_ROOT` après résolution, contrairement au sélecteur de dossier qui lui l'avait déjà. Corrigé.
- **Jobs de conversion** rattachés à leur propriétaire (nouvelle colonne `user_id`) : consultation/annulation désormais limitées au créateur du job ou à un admin.

### Nouveau

- **Espace « Mon compte »** : page dédiée (photo de profil avec recadrage carré automatique, changement d'identifiant, modale de changement de mot de passe partagée) et menu déroulant dans la topbar (Mon compte / Changer le mot de passe / Se déconnecter). Remplace l'ancienne page « Sécurité » et le bouton Déconnexion isolé de la sidebar.
- **Détection de doublons par contenu** (hash SHA-256, pas seulement nom/taille) intégrée à la page Diagnostic : un seul bouton « Lancer une analyse complète » déclenche à la fois les vérifications habituelles et le hashing des fichiers pas encore traités, avec suppression directe des doublons trouvés depuis le tableau de résultats.
- **Catalogue OPDS** (`/opds`) pour parcourir et télécharger la bibliothèque depuis une app de lecture dédiée (Chunky, Panels, Yacreader...) — authentification HTTP Basic dédiée et isolée du système de cookies, avec cache court des identifiants vérifiés et rate-limiting par IP. URL affichée dans Mon compte.
- **Réorganisation des pages de réglages**, à la demande de l'utilisateur après remarque sur la navigation : Utilisateurs + Profils fusionnés en « Comptes » (2 onglets), Bibliothèque + Sauvegarde & BDD fusionnés en « Bibliothèque » (2 onglets, Général / Sauvegarde & BDD). Diagnostic conservé séparé (outil d'action, pas de configuration). Onglets restylés en soulignement plutôt qu'en boutons segmentés, moins ambigus visuellement.
- **Topbar** : mode sombre et menu Mon compte déplacés en haut à droite, en icônes seules avec infobulle au survol, à côté du bouton Actualiser.
- **Photo de l'auteur** (page À propos) : vraie image du compte GitHub plutôt qu'un simple médaillon lettré.

### Contexte

Suite directe de la revue de sécurité demandée par l'utilisateur après le rituel v1.10.0 — corrections appliquées et vérifiées avant d'enchaîner sur un brainstorm de nouvelles fonctionnalités (PWA, OPDS, détection de doublons...), dont deux ont été retenues et implémentées. La réorganisation des pages de réglages est venue de remarques successives de l'utilisateur sur la lisibilité de la navigation au fil des ajouts de la session (onglets peu visibles, pages Diagnostic/Doublons redondantes, Bibliothèque/Sauvegarde & BDD scindées sans raison forte).

### Validation

Chaque correctif de sécurité et chaque fonctionnalité testés de bout en bout sur une copie de la vraie base de données via un serveur de dev jetable : tentatives de contournement SSRF (domaines pièges type `evil-bedetheque.com`), 404 confirmés sur séries masquées avant/après correctif, comptage du rate-limiter, mesure de latence du cache d'identifiants OPDS (~180 ms sans cache vs ~2 ms avec), scénario complet de doublon réel (détection, suppression, ré-hashing après modification d'un fichier), navigation OPDS complète (catalogue → série → couverture → téléchargement, avec échec d'authentification et changement de permission appliqué immédiatement). Build frontend et compilation Python systématiques après chaque lot de modifications, conteneur Docker local reconstruit et vérifié (health check) après chaque étape.

---

## v1.10.0 — 2026-08-26 — Nouvelle identité visuelle "Affiche", corrections mobile, revue de code

### Nouveau

- **Nouvelle identité visuelle "Affiche"**, appliquée à l'ensemble du site : typographie Bebas Neue pour les titres (gras unique, toujours en majuscules) associée à Work Sans pour le texte courant, fond papier clair, palette à double rôle — bleu marine pour les éléments structurels (graphiques, sélection, focus, barres de progression) et vermillon réservé aux éléments interactifs (boutons d'action, badges/étiquettes, liens, navigation active, notation). Direction validée via une proposition de palette avant application, puis déployée fichier par fichier (~30 fichiers, une centaine d'usages de couleur reclassés individuellement).
- **Mobile — grilles de couvertures** (pages Séries, Albums, Série, Accueil, Albums manquants) : passées de 2 à 3 colonnes par ligne.
- **Page Statistiques (mobile)** : nouvelle carte "Top éditeurs" ; les 4 tops (séries/éditeurs/dessinateurs/scénaristes) s'affichent en 2 colonnes au lieu d'une pile verticale.
- **Bouton "Actualiser"** (scanner, barre du haut) : libellé textuel ajouté à côté de l'icône (masqué sur mobile pour garder la barre compacte).
- **Lecteur (mobile)** : zoom par tap sur l'image ou flèches haut/bas désactivé (déplaçait l'image sans vraiment zoomer) — le pincer-zoomer à 2 doigts reste disponible. Icônes plein écran et double page masquées, non pertinentes sur petit écran.
- **Filtre de tri** : libellé "Nom (A-Z)"/"Nom (Z-A)" raccourci en "A-Z"/"Z-A" sous 480px ; largeur du select plafonnée pour ne plus pousser le bouton filtre hors champ.

### Corrections

- **Bug de build critique (Vite 8 / Lightning CSS)** : le minifieur CSS de production réécrivait silencieusement toutes les media queries `max-width`/`min-width` de l'application en syntaxe moderne (`width <= …`), non supportée avant Safari 16.4 — sur un iPhone plus ancien, les blocs concernés étaient donc intégralement ignorés sans erreur visible, ce qui a rendu inopérants une bonne partie des ajustements responsive de cette période sans que le code source ne laisse rien paraître. Corrigé en ciblant explicitement `build.cssTarget` (la seule option réellement lue par l'étape de minification, découverte après lecture du code source de Vite).
- **Conflit de cascade CSS** empêchant la grille 2 colonnes des "tops" de la page Statistiques de s'appliquer sur mobile malgré une media query correcte : une règle non conditionnelle de même spécificité, définie plus loin dans le fichier, l'emportait systématiquement. Corrigé par un sélecteur composé plus spécifique.
- **Étoiles de la note Bedetheque.com** affichées en jaune → alignées en rouge sur celles de "Ma note".
- **Texte secondaire (`--muted`) en dark mode** peu lisible avec la nouvelle palette → ancienne teinte restaurée.
- **10 bugs remontés par une revue de code complète**, tous corrigés :
  - Session SQLAlchemy partagée entre coroutines concurrentes lors de l'application en lot de métadonnées Bedetheque (risque de plantage sur plusieurs albums à la fois).
  - Collision d'identité de série entre deux dossiers portant le même nom (auparavant fusionnés en une seule série, avec risque de suppression du mauvais dossier) — identifiée par chemin de dossier, avec désambiguïsation automatique du nom en cas de conflit.
  - Déplacement d'albums vers une autre série : requêtes N+1 remplacées par une requête groupée.
  - Cache mémoire de la clé de session non invalidé au changement de mot de passe (nouveau cache introduit pour réduire la charge DB) — invalidation explicite ajoutée, testée en conditions réelles.
  - Vérification de chemin du convertisseur acceptant des dossiers que la conversion rejetait ensuite silencieusement.
  - Popup de complétion Bedetheque : un champ vidé par l'utilisateur restait compté/surligné comme "à appliquer" alors qu'il est ignoré côté serveur.
  - Page album blanche sans message en cas d'échec de chargement (lien obsolète, album supprimé ailleurs).
  - Section "Albums récents" de l'accueil non rafraîchie après un scan.
  - Virgule littérale cassant le champ de recherche de série dans la popup "Déplacer les albums".
  - Tri des tomes dupliqué et divergent (cas "HS" et numéros décimaux) dans le sélecteur de cover de série.

### Contexte

Suite directe de la refonte visuelle v1.9.1 : itération sur l'équilibre des couleurs (plusieurs allers-retours navy/vermillon avant validation du système à double rôle), puis remontées mobiles ponctuelles (grilles, statistiques, lecteur, tri) ayant mené à la découverte du bug Vite/Lightning CSS sous-jacent. Complété par une revue de code demandée explicitement avant publication.

### Validation

Chaque étape vérifiée par build frontend + inspection du bundle CSS compilé (syntaxe des media queries, règles scopées) + rebuild/redéploiement Docker. Correctifs de la revue de code testés en conditions réelles : flux d'authentification complet (login, changement de mot de passe, invalidation de l'ancienne session confirmée via requête directe) contre un conteneur de dev jetable ; compilation Python et build frontend passants sur l'ensemble des fichiers modifiés.

---

## v1.9.1 — 2026-08-24 — Refonte des pages Album et Série, correctif fuseau horaire, menu Scanner unifié

### Nouveau

- **Menu "Scanner" unifié** : bouton unique (icône refresh) dans la barre du haut, accessible depuis n'importe quelle page, avec un menu déroulant "Scanner les fichiers de la bibliothèque" et "Actualiser toutes les métadonnées" — remplace les boutons jusque-là dispersés entre la page Bibliothèque et la page Albums manquants. La progression du scan de métadonnées (Bedetheque) est désormais partagée dans un store global au lieu d'un état local à la page Albums manquants, donc visible et suivie où qu'on navigue pendant le scan.
- **Actualisation des métadonnées étendue à toute la bibliothèque** : le scan Bedetheque rafraîchit désormais le statut/résumé/genre de toutes les séries ayant une correspondance, et pas seulement celles suivies pour la détection d'albums manquants — le suivi ("séries suivies") ne fait plus que déterminer si les entrées d'albums manquants sont calculées, il ne bloque plus la mise à jour des infos générales.
- **Reprise de lecture** : sur la page album, le bouton "Lire" affiche "Reprendre la lecture (xx%)" quand l'album a une progression de lecture enregistrée et non terminée, au lieu de toujours afficher "Lire".
- **Confirmation avant téléchargement d'une série** : le bouton "Télécharger" de la page série (téléchargement en lot de tous les albums) est déplacé du groupe de boutons principal vers le menu "...", et ouvre désormais une popup de confirmation avant de lancer le téléchargement.

### Corrections

- **Bug de fuseau horaire généralisé** : toutes les dates de l'application (dernier scan, date d'ajout/modification d'un album, etc.) étaient stockées en UTC mais sérialisées sans indicateur de fuseau (`2026-08-24T17:12:03` au lieu de `...+00:00`), que le navigateur interprétait alors comme une heure locale plutôt qu'UTC — d'où un décalage systématique de 2h en France l'été. Corrigé à la racine via un type SQLAlchemy dédié (`UTCDateTime`) appliqué à toutes les colonnes de date de la base, sans migration nécessaire.
- **Barre de progression du scan de fichiers qui restait bloquée** après un redémarrage du conteneur (perte de l'état de progression en mémoire, sans repli sur la base de données) — même correctif que celui déjà en place pour le scan des albums manquants, désormais appliqué aux deux.
- **Cover de série à l'affichage démesuré ou déformée**, et débordant de l'écran en mobile.
- **Liens de filtre (auteur/dessinateur/éditeur/étiquette)** poussés depuis la page série vers la page Séries n'étaient jamais lus par cette dernière — les liens ne filtraient donc rien.
- **Étiquettes de série agrégées depuis un champ mort** (`Metadata.Tags`, jamais exposé ni écrit ailleurs dans l'app) au lieu des vraies étiquettes utilisateur (`user_tags`).
- **Étoiles de la note Bedetheque.com plus grosses que celles de la note personnelle** sur la page album (tailles de police désynchronisées entre les deux composants).

### Refonte des pages Album et Série

Nombreux ajustements visuels itératifs sur les pages de détail, pour harmoniser les deux héros et mieux exploiter l'espace disponible :
- Boutons d'action calés en bas de la cover même en l'absence de résumé (au lieu de rester collés sous le bloc titre/auteurs), et réduits en taille (padding, police, graisse) pour un rendu plus discret — identique sur les deux pages.
- Résumé limité à 3 lignes en desktop (troncature à 450 caractères, résumé entier conservé en mobile), avec le lien "Lire la suite" toujours visible à la suite du texte.
- Alignement responsive harmonisé : en dessous de 620px, tout le bloc texte (titre, identité, auteurs, étiquettes, résumé, boutons) est aligné à gauche de façon cohérente, au lieu d'un mélange centré/gauche selon les éléments.
- Page album : notes personnelle et Bedetheque.com remontées en haut à droite du hero, à côté du titre, avec leurs étoiles désormais alignées verticalement ; genre et étiquettes remontés dans le hero (comme sur la page série) ; encart technique passé d'une liste à une colonne à une grille à 3 colonnes ; année de publication et nombre de pages fusionnés dans la ligne "Tome" ; bande Ajouté/Modifié/Format/Taille dédiée, sans redondance avec le badge de statut déjà affiché dans le hero.

### Contexte

Session de polish continue sur les pages Album et Série, partie d'une simple question sur l'héritage des étiquettes entre série et albums, ayant mené à un audit plus large (dette visuelle, liens morts, champ de données mort) puis à une clarification demandée par l'utilisateur sur l'articulation entre "scan de bibliothèque" et "suivi des albums manquants" — deux vrais bugs (fuseau horaire, SSE de scan) ont été découverts en cours de route, sans lien avec la demande initiale.

### Validation

Chaque étape vérifiée par build frontend + rebuild/redéploiement Docker + inspection des bundles compilés. Correctifs backend testés en conditions réelles via curl authentifié contre les données du conteneur de dev : scan déclenché avec suivi désactivé sur une série (infos rafraîchies, aucun album manquant calculé), fuseau horaire confirmé sur plusieurs endpoints avant/après correctif, calcul de progression de lecture confronté à la valeur déjà renvoyée par `/api/tomes/in-progress`.

---

## v1.9.0 — 2026-08-23 — URL Bedetheque à l'import, préremplissage global des métadonnées

### Nouveau

- **Import — URL Bedetheque dès la création d'une série** : la popup "Créer une nouvelle série ?" propose désormais un champ optionnel pour renseigner directement l'URL Bedetheque de la série. Dès la saisie du nom, jusqu'à 5 séries candidates sont recherchées automatiquement dans l'index local (nom, nombre d'albums, statut, années — de quoi choisir sans quitter l'application) avec un lien direct vers chaque fiche Bedetheque.com pour vérifier avant de sélectionner ; en secours (série absente des suggestions), un champ de saisie manuelle reste disponible.
- **Préremplissage automatique des métadonnées à l'import** : dès l'arrivée à l'étape "Métadonnées", si une URL Bedetheque est connue (nouvelle série tout juste renseignée, ou série existante déjà liée), tous les albums importés sont automatiquement associés à leur fiche par numéro de tome et prérempli (titre, scénariste, dessinateur, éditeur) — sans action manuelle. L'icône de recherche individuelle sur chaque ligne reste disponible en repli pour un album non trouvé dans la page (ex. hors-série, édition spéciale).
- Valider la popup de création de série passe désormais directement à l'étape suivante (si des fichiers sont déjà sélectionnés), sans clic "Suivant →" supplémentaire.

### Corrections

- **Le menu latéral replié se rouvrait à chaque changement de page** (ex. fermé sur la page Séries, il réapparaissait en allant sur Albums) : l'état n'était jamais mémorisé, la vue étant recréée à chaque navigation. Persisté désormais comme le thème clair/sombre.

### Contexte
Suite d'une discussion partie d'une simple question ("peut-on saisir l'URL Bedetheque à l'import ?") ayant abouti, itération par itération, à un flux complet de découverte + préremplissage global — pensé pour éviter la recherche fichier par fichier lors de l'ajout d'une série entière, cas jusque-là uniquement couvert pour une série déjà existante et déjà liée.

### Validation
Endpoints testés en conditions réelles dans le conteneur de dev : recherche par nom ("Gaston" → bon candidat en tête sur les 46 séries correspondantes de l'index), récupération complète d'une page série par URL directe, et par `series_id` pour une série existante déjà liée (46 albums récupérés). Cas d'erreur (URL invalide, série sans URL confirmée) vérifiés en retour 400/502 propres. Build frontend et bundles compilés vérifiés (présence du code et des styles attendus).

---

## v1.8.0 — 2026-08-22 — Recherche Bedetheque précise pour une série déjà identifiée, statistiques, responsive

### Nouveau

- **Recherche Bedetheque précise pour une série déjà liée** : rechercher les métadonnées d'un album existant, ou importer un nouvel album dans une série existante ayant déjà une URL Bedetheque confirmée, utilise désormais directement cette URL au lieu de deviner la bonne série par son nom. Pour une franchise avec de nombreuses déclinaisons sur Bedetheque (éditions, langues, spin-offs — ex. une vingtaine de séries "Garfield…"), la recherche par nom pouvait passer complètement à côté de la bonne série (limitée à 3 candidates, classées par ordre alphabétique) ; avec l'URL déjà connue, la liste complète et exacte des albums est récupérée, dans l'ordre naturel de Bedetheque, avec l'album recherché toujours en tête. La recherche par nom reste utilisée telle quelle pour une série pas encore liée à Bedetheque.
- **Page Statistiques** : camembert "Séries en cours / terminées" (avec une part "Statut inconnu" pour les séries sans statut Bedetheque renseigné), graphique en barres de la répartition des notes personnelles (1 à 5 étoiles), et carte "Séries complètes" (% des séries suivies et résolues sur Bedetheque sans aucun album manquant). Graphique "Formats" retiré (redondant). "Éditeurs" et "Séries en cours / terminées" affichés côte à côte.
- **Page Albums manquants** : croix "ignorer cette série" déplacée à côté du titre (au lieu de tout à droite, loin de la série concernée).

### Corrections

- **Pages Séries et Albums débordant horizontalement sur mobile** : la barre d'outils (titre, compteur, bascule Séries/Albums, tri, filtre) dépasse largement la largeur d'un écran étroit, et rien ne contenait cet excédent — il se répercutait sur toute la page. La barre défile désormais dans ses propres limites (comme la barre alphabet juste en dessous), avec un filet de sécurité pour empêcher toute page de reproduire ce problème à l'avenir.
- **Lecteur, mode double page sur écran étroit** : deux pages pleine hauteur côte à côte ne pouvaient pas rétrécir en dessous de leur largeur naturelle (bug flexbox classique), débordant et se retrouvant rognées au lieu d'être réduites proportionnellement — donnant une impression de "zoom" involontaire.
- **Lecteur sur mobile (iOS Safari) : un tap près du haut/bas de l'écran faisait "bouger" la page** au lieu d'agir sur le zoom — comportement natif de rebond élastique (overscroll) du navigateur qui s'infiltrait à travers le lecteur malgré sa position fixe. Corrigé par verrouillage du défilement de la page pendant la lecture et confinement de l'overscroll.
- **Bouton plein écran du lecteur inopérant sur iPhone** : Safari sur iPhone ne supporte pas l'API Fullscreen (restriction d'Apple, iPad la supporte). Le bouton se masque désormais automatiquement sur les appareils qui ne la supportent pas, plutôt que de rester affiché sans effet.

### Contexte
Suite de la session v1.7.1 : retour d'usage sur la page Statistiques (nouvelles données utiles), un audit de l'affichage responsive (pages Séries/Albums et lecteur) suite à des tests sur téléphone, et un vrai bug de recherche découvert en essayant d'importer un tome de Garfield — la série ayant le plus de déclinaisons testée jusqu'ici, elle a révélé une limite de la recherche floue jamais remarquée avec des séries moins ambiguës.

### Validation
Fix de recherche Bedetheque vérifié en conditions réelles dans le conteneur de dev : une série de test pointée vers la vraie page "Garfield (Dargaud)" (98 albums) confirme la récupération complète et le bon tri, recherche floue classique (sans série identifiée) reconfirmée fonctionnelle en parallèle. Nouvelles statistiques vérifiées via l'API sur les données réelles du conteneur de dev. Correctifs responsive et lecteur vérifiés par inspection du CSS/JS compilé (présence des propriétés attendues) ; comportement tactile/iOS non testable directement dans cet environnement, à confirmer par l'utilisateur sur appareil réel.

---

## v1.7.1 — 2026-08-21 — Renommage de fichiers : motif par défaut et numéro/titre non mis à jour

### Corrections

- **"Renommer les fichiers" utilisait un motif par défaut différent de celui configuré dans Paramètres** (sans le "T" devant le numéro), ignorant totalement le réglage réel — contrairement au renommage à l'import qui, lui, le respectait déjà. Charge désormais le motif effectivement configuré au lieu d'une valeur codée en dur.
- **Renommer un fichier ne recalculait jamais son numéro/titre à partir du nouveau nom** : le fichier était bien renommé sur le disque, mais `number`/`title` restaient figés sur l'ancien parsing — un titre pollué par un numéro mal reconnu avant renommage (voir le point précédent) restait donc affiché tel quel indéfiniment, même après correction du nom de fichier, et même après un nouveau scan (la taille/date du fichier ne changeant pas lors d'un simple renommage, rien ne déclenchait de nouvelle analyse). Les deux endpoints de renommage (individuel et en lot) recalculent désormais number/title depuis le nouveau nom, immédiatement.
- Correction complémentaire côté scan : la récupération automatique d'un numéro non reconnu (introduite en v1.6.3/v1.7.0) ne corrigeait le titre associé que s'il était vide — un ancien titre erroné (numéro resté collé dedans) restait donc lui aussi figé. Corrigé pour toujours resynchroniser les deux ensemble, y compris pour un fichier renommé directement sur le NAS hors de l'application.

### Contexte
Repéré en corrigeant une série Tintin nommée sans "T" devant les numéros (T01, T02…) : le renommage via l'app semblait fonctionner (nom de fichier correct sur le disque) mais le titre affiché sous chaque cover restait incorrect malgré un nouveau scan.

### Validation
Scénario reproduit à l'identique dans le conteneur de dev : fichier mal nommé scanné (titre pollué par le numéro, comme chez l'utilisateur), puis renommé via l'endpoint réel de l'application — `number`/`title` corrects immédiatement après le renommage, sans scan supplémentaire. Données de test nettoyées ensuite.

---

## v1.7.0 — 2026-08-21 — Menu complet sur la cover série, navigation lecteur, correctif "sans métadonnées"

### Nouveau

- **Cover de la page série, actions complètes** : crayon en bas à gauche (édition directe), "…" vertical en bas à droite ouvrant le même menu complet et dans le même ordre que sur la page Séries (Éditer, Compléter, Renommer les fichiers, Convertir, Modifier la miniature, Masquer/Afficher, Supprimer la série) ; le reste de la cover ouvre toujours le sélecteur de miniature au clic. Les boutons directs existants (Éditer/Compléter/Convertir/Masquer) sont conservés à la demande.
- **Lecteur — barre de progression cliquable et glissable** : clic ou glisser (souris et tactile) sur la barre du bas pour sauter directement à une page, au lieu de la navigation page par page uniquement. Zone cliquable/glissable élargie verticalement (invisible) pour plus de confort, sans épaissir visuellement la barre.
- **Lecteur — plein écran** : nouveau bouton dédié dans la barre du haut (déjà possible via le raccourci clavier `f`, mais jamais mis en avant). Un premier `Échap` en plein écran quitte désormais seulement le plein écran (comme un lecteur vidéo classique) au lieu de fermer directement le lecteur.
- **Page Albums manquants** : nom de série cliquable (renvoie vers sa fiche) et croix pour retirer une série du suivi directement depuis la liste, sans passer par "Gérer le suivi".

### Corrections

- **Filtre "Sans métadonnées uniquement" incluait des albums pourtant bien renseignés** (ex. après une complétion depuis Bedetheque ou une édition en lot) : les deux endpoints concernés (application des suggestions Bedetheque, édition en lot) écrivaient bien les champs dans le fichier et en base, mais oubliaient de mettre à jour l'indicateur `has_metadata` utilisé par ce filtre. Corrigé aux deux endroits, avec une réconciliation automatique au prochain scan pour les albums déjà concernés (reconstruite depuis les métadonnées déjà en base, sans relecture du fichier) — aucune action manuelle nécessaire.
- **Couverture d'un album manquant parfois remplacée par une icône décorative** du site Bedetheque au lieu de la vraie couverture, pour certains albums seulement.
- **Numéro de tome jamais reconnu pour la convention "Tome 01"** (seul "T01" l'était), empêchant toute correspondance avec Bedetheque pour les fichiers nommés ainsi — reconnu désormais, avec récupération rétroactive automatique au prochain scan.
- **Renommage d'une série avec un caractère comme « : » pouvait corrompre silencieusement le nom du dossier sur le disque** (certains partages réseau y substituent un nom court à la DOS 8.3, ex. "Code : Breaker" → "CRUHFO~C", sans remonter d'erreur) — caractères réservés Windows/SMB désormais rejetés explicitement avant tout renommage.
- **Connexion impossible en HTTP direct** (sans reverse proxy HTTPS devant l'application) : le cookie de session était marqué `Secure` par défaut en production, donc rejeté par le navigateur.
- **Enregistrement de l'URL Bedetheque d'une série lent et nécessitant un rafraîchissement manuel** : réécriture inutile de tous les CBZ de la série à chaque sauvegarde (même sans changement de métadonnées) et re-scan associé en tâche de fond terminant après le rechargement de la page — les deux corrigés, l'enregistrement passe de 5-10s à ~0,3s avec état à jour immédiat.
- **Note communautaire jamais récupérée en complétant les métadonnées d'un seul album** (recherche multi-sources, onglet Bedetheque.com) : perdue en route entre le scraper et le formulaire.

### Contexte
Suite de la session v1.6.3, sur la même journée : authentification, statut/notes Bedetheque et actions rapides par menu (v1.6.0-v1.6.2) déployées puis affinées suite aux retours d'usage réel ; page Albums manquants, "Tome N" et noms de série protégés (v1.6.3) ; puis cette session, en continu : refonte des icônes de la cover série, amélioration du lecteur (navigation par page, plein écran), et un dernier correctif de fond sur le filtre "sans métadonnées" repéré en naviguant dans la bibliothèque.

### Validation
Chaque correctif backend vérifié en direct via `curl` contre les données réelles du conteneur de dev (session authentifiée). Changements frontend vérifiés par reconstruction du conteneur Docker et inspection des bundles compilés après chaque lot de modifications. La correction rétroactive de `has_metadata` vérifiée sur un album réel (« Faut pas Poussy », `has_metadata` passé de `False` à `True` après un simple scan, disparu du filtre concerné).

---

## v1.6.3 — 2026-08-21 — Albums manquants (lien série, ignorer), couverture, numérotation "Tome N", noms de série protégés

### Nouveau

- **Page Albums manquants** : le nom de chaque série est désormais cliquable (renvoie vers sa fiche), et une croix discrète à côté permet de la retirer du suivi directement (même effet que l'exclusion depuis "Gérer le suivi", sans avoir à l'y rechercher).

### Corrections

- **Couverture d'un album manquant parfois remplacée par une icône décorative** (coin `corner.top.left.png` du site) au lieu de la vraie couverture : certains albums Bedetheque affichent une icône de mise en avant avant l'image de couverture dans le même bloc HTML — le sélecteur prenait par erreur la première image trouvée. Exclut désormais explicitement cette icône.
- **Numéro de tome jamais reconnu pour la convention "Tome 01"** (seul "T01" l'était) : empêchait toute correspondance avec Bedetheque pour les fichiers nommés ainsi ("Aucun album possédé ne correspond…"), le numéro local restant `null`. Format "Tome N"/"tome N" (avec ou sans espace, insensible à la casse) désormais reconnu au même titre que "TN". Un fichier déjà scanné mais dont le numéro n'avait jamais pu être extrait est automatiquement corrigé au prochain scan, même sans modification du fichier lui-même — aucune resynchronisation manuelle nécessaire.
- **Renommage d'une série avec un caractère comme « : » pouvait corrompre silencieusement le nom du dossier sur le disque** : certains partages réseau/systèmes de fichiers compatibles Windows substituent un nom court à la DOS 8.3 (ex. "Code : Breaker" → "CRUHFO~C") sans que l'opération de renommage ne remonte d'erreur, désynchronisant le nom affiché dans l'app du nom réel sur le disque. Les caractères réservés Windows/SMB (`/ \ : * ? " < > |`) sont désormais rejetés explicitement avant toute tentative de renommage, avec un message clair.

### Contexte
Trois remontées successives en testant l'app au quotidien : ergonomie de la page Albums manquants, une couverture visiblement fausse sur un album précis, et une série (manga "Code:Breaker", titre officiel avec un ":") qui refusait obstinément toute complétion Bedetheque malgré une URL valide et des fichiers a priori bien nommés.

### Validation
Sélecteur de couverture vérifié par récupération réelle de la page Bedetheque de l'album concerné (Anatole Latuile T20). Détection "Tome N" testée sur une dizaine de formats de noms réels et régressifs (aucun format existant cassé), et la récupération rétroactive vérifiée en conditions quasi réelles dans le conteneur de dev (fichier scanné, numéro effacé en base pour simuler l'état "jamais reconnu", confirmé corrigé après un simple nouveau scan sans toucher au fichier). Validation des caractères réservés testée en direct par tentative de renommage avec « : », rejetée avec le message attendu, série non modifiée.

---

## v1.6.2 — 2026-08-20 — Correction : enregistrement URL série lent, note absente par album

### Corrections

- **Enregistrement de l'URL Bedetheque d'une série encore lent (plusieurs secondes) malgré le correctif v1.5.15** : la modale d'édition d'une série réécrivait systématiquement le `ComicInfo.xml` de tous les tomes CBZ à chaque sauvegarde, même quand seul le champ URL (ou Statut) avait changé — c'était le vrai goulot d'étranglement, pas le re-scan associé (déjà en tâche de fond). Cette réécriture est désormais sautée si aucun des champs Série/Dessinateur/Scénariste/Éditeur/Langue n'a réellement changé.
- **Page série non à jour après modification de l'URL sans rafraîchissement manuel** : le re-scan associé tournait en tâche de fond, terminant après le rechargement de la page déclenché par la sauvegarde — d'où un statut affiché périmé jusqu'au rafraîchissement suivant. Redevenu synchrone (délai de courtoisie de 1,5s, prévu pour l'enchaînement de plusieurs séries lors d'un scan complet, retiré pour une ré-analyse ponctuelle d'une seule série) : la réponse contient directement l'état à jour, ~0,3s au lieu de 5-10s.
- **Note communautaire jamais récupérée en complétant les métadonnées d'un seul album** (recherche multi-sources, onglet Bedetheque.com) : l'API de recherche extrayait bien la note et le nombre de votes en interne, mais le schéma de réponse ne les exposait pas, et le frontend ne les reportait pas sur la sélection d'un résultat. Les deux corrigés.

### Contexte
Signalé immédiatement après déploiement de v1.6.1.

### Validation
Les trois correctifs vérifiés en direct via `curl` contre les données réelles du conteneur de dev (session authentifiée) : enregistrement d'URL chronométré (0,3s), statut à jour dans la réponse immédiate, note/votes présents dans une recherche Bedetheque réelle et correctement persistés sur un album test (valeur d'origine restaurée après coup).

---

## v1.6.1 — 2026-08-20 — Correction critique : connexion impossible en HTTP direct

### Corrections

- **Impossible de se connecter (identifiants corrects) dès que l'application est accédée en HTTP direct (sans reverse proxy HTTPS devant)** : le cookie de session était marqué `Secure` dès que `DEV_MODE` n'était pas activé, ce qui est le cas par défaut en production. Un cookie `Secure` n'est jamais stocké par le navigateur sur une connexion non-HTTPS — la connexion semblait aboutir un court instant puis toutes les requêtes suivantes retombaient en 401, comme si rien ne s'était passé. Le cookie reflète désormais la connexion réelle (header `X-Forwarded-Proto` posé par un reverse proxy s'il est présent, sinon le schéma de la requête reçue par l'app) au lieu de dépendre de `DEV_MODE`.

### Contexte
Signalé immédiatement après déploiement de v1.6.0 : connexion impossible avec les identifiants par défaut sur une instance accédée directement en HTTP (sans passer par un reverse proxy HTTPS).

### Validation
Testé en direct via `curl` : cookie posé sans `Secure` sur une requête HTTP simple, avec `Secure` dès qu'un header `X-Forwarded-Proto: https` est présent (cas d'un reverse proxy en HTTPS devant l'app).

---

## v1.6.0 — 2026-08-20 — Authentification, statut/notes Bedetheque, actions rapides par menu

### Nouveau

- **Authentification** : un unique compte (login/mot de passe, `admin`/`admin` par défaut) protège désormais l'application derrière une session par cookie signé (pas de stockage de session côté serveur). Page "Sécurité" dans les paramètres pour changer l'identifiant et le mot de passe ; toute modification invalide les autres sessions ouvertes. Redirection automatique vers `/login` si non connecté, bouton de déconnexion dans le menu.
- **Statut, genre et notes de la communauté depuis Bedetheque.com** : en plus des champs déjà récupérés, la fiche série affiche désormais le statut ("Série en cours" / "Série finie", modifiable manuellement) et chaque album affiche sa note communautaire (note sur 5 + nombre de votes), à côté de la note personnelle. Tout est stocké en base uniquement — jamais écrit dans le `ComicInfo.xml` des fichiers.
- **Popup "Compléter depuis Bedetheque.com" entièrement révisée** : toutes les cellules du tableau sont éditables (plus seulement les champs vides), avec une suggestion visible quand la fiche Bedetheque propose une valeur différente de celle déjà renseignée ; colonne "Titre" ajoutée ; bouton "Accepter toutes les modifications" pour tout valider en un clic.
- **Actions rapides via les menus "…"** : sur un album, "Rechercher les métadonnées" est accessible directement depuis le menu "…" (sans passer par "Éditer" d'abord). Sur une série, le menu "…" (pages Séries et Accueil) gagne une entrée "Compléter les métadonnées" qui ouvre directement le tableau de complétion.
- Sur la page d'une série, le bouton "Renommer" — largement redondant puisque le renommage se fait déjà à l'import — est remplacé par un bouton "Compléter" plus utile au quotidien ; le renommage manuel reste accessible via le menu "…" des pages Séries/Accueil.

### Corrections

- **Enregistrement de l'URL Bedetheque d'une série lent (5 à 10s)** : le re-scan associé bloquait la réponse HTTP. Déplacé en tâche de fond ; la page se met à jour immédiatement sans nécessiter de rafraîchissement manuel.
- **Suggestions de complétion jamais affichées pour un champ déjà renseigné** : la comparaison avec la valeur Bedetheque n'était calculée que pour les champs vides, empêchant toute correction assistée d'un champ déjà rempli mais erroné.
- **URL `__10000.html` pouvait être doublement suffixée** (`...__10000__10000.html`) si l'URL enregistrée était déjà au format "liste complète" — la génération de cette URL est maintenant idempotente.
- **Auteurs/éditeurs incomplets sur la fiche série et le pré-remplissage à l'import** : l'agrégation ne portait que sur le premier tome de la série au lieu de tous les tomes, masquant les scénaristes/dessinateurs supplémentaires d'une série à plusieurs mains.

### Interface

- Badge de statut de série déplacé après le nombre de tomes (plus logique qu'après le titre), style neutre.
- Barre "Compléter les métadonnées" repositionnée juste sous le titre de la série, au même endroit que "Rechercher" sur un album, pour uniformiser les deux popups.
- Champ Statut en menu déroulant plutôt qu'en boutons, plus discret. Lien "Consulter" à côté du champ URL Bedetheque.com.
- Suppression des champs inutilisés : URL Bedetheque par album (seule l'URL de la série sert de référence), champ libre "Commentaire" par album (et purge de la colonne associée, vide, en base).
- Note personnelle renommée en clair, note Bedetheque.com affichée sur la même ligne ; survol des étoiles corrigé pour remplir toutes les étoiles précédentes.
- Popup "Compléter depuis Bedetheque.com" : titre précisé, icône d'aide superflue retirée.

### Contexte
Suite de la session v1.5.16, sur plusieurs jours : mise en place de l'authentification (demandée suite à l'exposition de l'app via reverse proxy), puis extension du scraping Bedetheque (statut de série, notes communautaires) déjà utilisé pour les auteurs/éditeur, et enfin une longue passe d'ergonomie sur les popups de métadonnées et les menus d'action rapide, au fil des retours d'usage réel de l'application.

### Validation
Fonctionnalités backend vérifiées par tests `curl` directs contre les données réelles du conteneur de dev (sessions authentifiées via cookie jar, scraping Bedetheque testé sur plusieurs séries réelles). Changements frontend vérifiés par reconstruction du conteneur Docker et inspection des bundles compilés (présence des textes/classes attendus) après chaque lot de modifications ; rendu visuel à l'écran non vérifié directement (pas d'accès navigateur cette session).

---

## v1.5.16 — 2026-08-20 — Correction critique : réaffectation de série au scan

### Corrections

- **Régression v1.5.15 — sous-dossiers imbriqués créés vides** : le scan ne réaffectait `series_id` qu'à la création d'un tome, jamais pour un fichier déjà connu (chemin inchangé). Un fichier déjà scanné avant le changement de logique de nommage des séries (v1.5.15) restait donc rattaché à son ancienne série (celle nommée d'après le dossier de catégorie), pendant que la nouvelle série correctement nommée était créée vide à côté. Le scan réaligne désormais `series_id` à chaque passage, y compris pour un fichier inchangé.
- Une série de catégorie devenue vide après cette réaffectation (ex. l'ancien "manga" qui contenait tout) n'est nettoyée qu'au scan suivant (le nettoyage des séries vides évalue l'état en début de scan, avant la réaffectation) — comportement normal, identique à celui d'une série vidée par une suppression manuelle.

### Contexte
Signalé immédiatement après déploiement de v1.5.15 : les nouvelles séries issues des sous-dossiers imbriqués apparaissaient bien mais restaient vides (0 albums) malgré des fichiers présents sur le disque.

### Validation
Bug reproduit à l'identique dans le conteneur de dev (tome inséré directement en base avec l'ancien rattachement "catégorie", comme l'aurait laissé un scan v1.5.15) : après correctif, un premier scan réaffecte bien le tome à la série "sous-dossier", un second scan supprime l'ancienne série de catégorie devenue vide — données de test nettoyées ensuite.

---

## v1.5.15 — 2026-08-20 — Bedetheque auto-complétion, sélection multiple, actions par album, sous-dossiers

### Nouveau

- **Complétion automatique des métadonnées depuis Bedetheque** : sur une série liée à une fiche Bedetheque, un nouveau bouton "Compléter les métadonnées depuis Bedetheque…" (déplacé dans la popup d'édition, sous le champ URL, toujours visible) récupère en un seul appel la page de la série et propose de remplir les champs Dessinateur/Scénariste/Éditeur/Année manquants de chaque tome — jamais les champs déjà renseignés. Tableau récapitulatif (une ligne par album, une colonne par champ), autocomplétion sur les champs éditables, correction manuelle possible avant validation.
- **Champ "URL Bedetheque" éditable manuellement** sur la fiche série, avec re-scan immédiat si la case "suivre les nouveautés" est active. Le scan automatique ne retente plus de deviner l'URL une fois une correspondance confirmée ("found"), mais retente à chaque scan si elle est restée "introuvable" — une URL cassée par un changement côté Bedetheque peut donc s'auto-corriger, alors qu'une URL manuellement validée n'est plus jamais écrasée.
- **Sélection multiple** (cercle sur chaque cover, au survol) sur les pages Séries, Albums et désormais aussi sur la page d'une série : Déplacer vers une série / Éditer en lot / Supprimer, avec confirmation avant toute suppression.
- **Menu "…" par album** (survol de la cover, coin bas-droit) sur les pages Albums et page-série : Éditer les métadonnées / Déplacer vers une série / Supprimer, pour agir sur un seul album sans passer par la sélection multiple ni ouvrir la fiche complète.
- **Sous-dossiers imbriqués** : le scanner regroupait les albums par le premier niveau de dossier sous la racine de la bibliothèque — un dossier "manga" contenant un sous-dossier par série aurait fusionné toutes ces séries en une seule nommée "manga". Il utilise désormais le dossier immédiatement parent des fichiers, quelle que soit la profondeur : un dossier de catégorie (`manga/OnePiece/…`, `manga/Naruto/…`) fonctionne maintenant sans fusion, en gardant chaque sous-dossier comme série distincte.

### Corrections

- **Déplacer un album ne mettait pas à jour le compteur de la série** (`tome_count` figé jusqu'au scan suivant) **ni le nom de série dans ses métadonnées** (champ `Series` du `ComicInfo.xml` et de la base, toujours celui de l'ancienne série). Même bug de fond retrouvé et corrigé dans la suppression (unitaire et en lot) : le compteur de la série restante n'était jamais recalculé après le retrait d'un album.
- **Liste déroulante de l'autocomplétion impossible à faire défiler** (champ "Série de destination" de la popup Déplacer, entre autres) : un écouteur de scroll en phase de capture fermait la liste dès qu'on tentait de la parcourir, avant même que le scroll n'atteigne son propre contenu. Un clic sur le champ affiche maintenant la liste complète des séries, triée A→Z, et reste ouverte pendant qu'on la parcourt.
- **Menu "…" par album** : se refermait si la souris quittait la carte (même en cliquant dessus juste avant), et s'ouvrait vers le haut au lieu du bas comme sur la page Séries. Les deux corrigés — le menu reste ouvert jusqu'à un clic ailleurs ou une sélection, et s'ouvre systématiquement vers le bas.
- **Badges illisibles en mode sombre** (numéro de tome sur les covers Séries/Albums/page-série, badge "Albums manquants") : fond blanc fixe avec une couleur de texte qui suivait le thème (`var(--text)`), devenant gris clair sur fond blanc en mode sombre. Couleur de texte fixée.

### Interface

- **Icônes flottantes sur les covers** (Modifier, "…") : passées d'un rond de fond plein à une icône seule (blanche + ombre portée légère pour rester lisible sur toute image), légèrement agrandies, cohérentes sur les 4 pages qui les utilisent (Séries, Albums, page-série, Accueil). Icône "…" désormais verticale.
- **Cercle de sélection multiple** : anneau fin (façon Plex) quand non sélectionné au lieu d'un rond plein, remplissage bleu + coche blanche une fois sélectionné (inchangé).
- **Bordure au survol** des covers (Séries, Albums, page-série) : fin liseré bleu, de la même épaisseur que celui de la sélection (1.5px), pour un retour visuel cohérent entre survol et sélection.
- **Assombrissement au survol des covers** : augmenté de 32% à 45% d'opacité.
- **Barre de sélection multiple** : remplace la barre alphabet (au lieu de s'ajouter par-dessus) le temps qu'une sélection est active, pour ne pas décaler la grille vers le bas.
- Icône "Lire" de la page Albums : agrandie et centrée sur la cover au survol, comme sur la page d'une série (au lieu d'une petite icône en coin).

### Contexte
Suite directe de la session v1.5.14. Un très gros lot cette fois : la fonctionnalité de complétion automatique depuis Bedetheque (plusieurs itérations de présentation avant la version retenue), puis la sélection multiple/actions en lot sur les trois pages d'albums, avec son lot de bugs de bord trouvés en testant en conditions réelles (compteurs de série, métadonnées non mises à jour, menu contextuel capricieux), et enfin une passe de polish visuel sur les covers demandée au fil de l'eau.

### Validation
Chaque correctif et chaque nouvelle fonctionnalité touchant le backend a été vérifié contre les données réelles du conteneur de dev (déplacement d'album, suppression en lot, scan de sous-dossiers imbriqués — données de test toujours nettoyées après coup), avec inspection directe des fichiers CBZ modifiés (ComicInfo.xml) quand pertinent. Le rendu visuel des changements CSS/JS a été vérifié par build + reconstruction du conteneur Docker + inspection du bundle compilé et servi ; aucun accès navigateur direct cette session, le rendu final à l'écran reste à confirmer côté utilisateur.

---

## v1.5.14 — 2026-08-18 — Corrections mobile Stats, fin d'import, titre Import

### Corrections critiques

- **Scroll bloqué sur mobile** : `AppLayout.vue` verrouille `document.body.style.overflow = "hidden"` pendant que le tiroir de menu mobile est ouvert. Comme ce composant est recréé à chaque navigation (chaque page l'inclut dans son propre template), changer de page pendant que le tiroir était encore ouvert pouvait laisser ce verrou bloqué indéfiniment, empêchant le défilement de la page suivante (et de toutes les suivantes) sans lien apparent avec la cause. Reset explicite et inconditionnel au démontage du composant.

### Corrections — page Statistiques (mobile)

- Le graphique "Albums par année d'édition" débordait de la largeur de l'écran (largeur minimale forcée à 400px) ; il se réduit désormais proportionnellement sous 480px au lieu de forcer un défilement horizontal.
- Les cards après le graphique (Éditeurs/Formats, Top séries/dessinateurs/scénaristes) s'affichaient avec une largeur incohérente (plus étroites que le reste de la page) sous 640px — conflit CSS où `min-width: 280px` dépassait `max-width: 50%` du conteneur sur petit écran, forçant une largeur fixe au lieu de remplir la ligne. Empilées en pleine largeur sous ce seuil.
- Les unités Go/Mo des cards "Taille totale" / "Taille moyenne" sont désormais affichées plus petites et grisées, pour mettre en valeur le chiffre.

### Corrections — import

- **Fin d'import bloquée sur "en cours"** : après l'upload et la conversion de tous les fichiers, l'app relance une réindexation de la bibliothèque avant d'afficher l'état "terminé" — pendant ce temps, le bouton "Annuler" restait affiché sans plus rien de significatif à annuler, et le décompte + les boutons de fin (Importer d'autres albums / Voir la série) n'apparaissaient pas. Nouvel état intermédiaire "Mise à jour de la bibliothèque…", bouton Annuler masqué durant cette phase.
- Le décompte "X fichier(s) importé(s)" était collé aux boutons de fin sur la même ligne ; affiché maintenant sur sa propre ligne, boutons regroupés en dessous.
- Titre de la page renommé "Importer une série" → "Importer des albums" (plus fidèle à l'usage — import d'albums individuels, pas uniquement de séries complètes).

### Contexte
Suite directe de la session v1.5.13. Une nouvelle série de remontées ergonomiques ciblées sur mobile (page Statistiques) et sur le flux de fin d'import, avec un vrai bug de fond découvert au passage (verrou de défilement) plutôt qu'un simple problème visuel.

### Validation
Chaque correctif vérifié via build réel + reconstruction du conteneur Docker + inspection directe du CSS/JS compilé et servi (recherche de règles/chaînes distinctives dans les bundles) — le rendu visuel/tactile final reste à confirmer côté utilisateur, aucun accès navigateur cette session.

---

## v1.5.13 — 2026-08-17 — UI/UX : tri, doublons, lecteur tactile, cohérence clavier

### Corrections

- **Détection de doublons auteurs/éditeurs (niveau 3)** : la comparaison se faisait sur des sous-chaînes brutes sans respecter les limites de mots — "Sti" matchait à tort "Chri**sti**an", "Hero" matchait "Ma**chero**t", créant des groupes de doublons absurdes reliés par transitivité (ex. "Godard", "Sti", "Jean Bastide", "Bast", "Christian Godard" dans une seule alerte). La comparaison ne se fait plus que sur des mots entiers.
- **Formulaire d'édition de série** : n'avait ni autocomplétion ni champ Langue, et un ordre de champs différent de l'édition d'album. Aligné (Série, Dessinateur, Scénariste, Éditeur, Langue), avec la même autocomplétion partout.
- **Albums d'un auteur/éditeur mélangés** : cliquer sur un auteur ou un éditeur depuis la page Auteurs affichait ses albums dans un ordre non pertinent. Triés désormais par série (A→Z) puis par numéro de tome (tri numérique : T2 avant T10).
- **Page Statistiques sur mobile** : le graphique "Albums par année d'édition" débordait de la largeur de l'écran (largeur minimale forcée) ; les cards restaient sur 1 colonne sur les petits écrans (ex. iPhone 12 mini) faute de place pour 2 colonnes de 160px. Corrigés.
- **Page Albums manquants** : le titre "Albums manquants" était répété deux fois (bandeau du haut + à l'intérieur de la card), avec le badge du nombre uniquement sur le second. Le second titre est supprimé, le badge est déplacé sur le titre principal.
- **Couleur des badges de notification** (menu "Albums manquants" + titre de la page) : rouge, trop associé à une alerte critique pour un simple compteur. Passés au bleu de l'identité visuelle de l'app (`--primary`).

### Nouveau

- **Menu latéral responsive** (voir v1.5.12) et **lecteur tactile** : swipe horizontal pour tourner les pages sur mobile/tablette (geste horizontal dominant uniquement, sans interférer avec le tap existant ni le défilement vertical en mode zoom-largeur).
- **Bouton "Ignorer" sur les doublons auteurs/éditeurs** : un groupe détecté à tort peut être masqué (mémorisé localement par le navigateur), avec un lien "réafficher" pour ne jamais le perdre définitivement.
- **Cohérence clavier des popups d'édition** (série, album) : Entrée valide désormais le formulaire (sauf pendant une sauvegarde en cours, une confirmation de suppression ouverte, ou dans un champ de commentaire multi-lignes). Bug corrigé au passage : Échap fermait toute la popup même quand une confirmation de suppression était ouverte par-dessus, perdant les modifications en cours sans prévenir — Échap referme maintenant la couche visible la plus haute en premier.
- **Navigation clavier dans l'autocomplétion** (auteurs/dessinateurs/éditeurs) : jusqu'ici sélection à la souris uniquement. Flèches pour parcourir les suggestions, Entrée pour confirmer, Échap pour refermer juste la liste sans fermer toute la popup.

### Contexte
Suite directe de la session v1.5.12 (menu responsive) : une série de remontées ergonomiques ciblées, chacune vérifiée sur le conteneur Docker réel (build + inspection du CSS/JS compilé et servi) faute d'accès navigateur direct cette session — le rendu visuel/tactile final reste à confirmer côté utilisateur.

---

## v1.5.12 — 2026-08-17 — Menu responsive (mobile/tablette)

### Nouveau

- **Menu latéral responsive** : sous 768px de large, le menu de navigation (`AppLayout.vue`) n'est plus affiché en permanence — il devient un tiroir flottant, masqué par défaut, ouvert via le bouton hamburger de la barre du haut (déjà présent, sert désormais aussi de bouton d'ouverture sur mobile). Un fond semi-transparent apparaît derrière le tiroir ouvert et le referme au clic ; le tiroir se referme aussi automatiquement à chaque navigation.
- Le menu conserve son comportement desktop existant (repli en mode icônes seules) sans changement au-dessus de 768px.

### Contexte
Investigation préalable ayant confirmé que la mise en page globale (menu + barre du haut) n'avait en réalité aucune règle responsive existante — seules les grilles de couvertures (Séries, Albums, Accueil…) s'adaptaient déjà à la largeur d'écran. Cette étape traite le menu, la partie la plus rentable (un seul fichier partagé par toute l'app) ; la mise en page fine du contenu de chaque page (tableaux, modales) reste à traiter plus tard, page par page.

### Validation
Build frontend réel + reconstruction et redémarrage du conteneur Docker de dev, CSS compilé inspecté directement dans le conteneur en cours d'exécution pour confirmer que la règle `@media (max-width: 768px)` et les classes `.sidebar-mobile-open` / `.sidebar-backdrop` sont bien présentes et correctement empilées (z-index). Le rendu visuel/tactile réel (redimensionnement de fenêtre, usage tactile) n'a pas pu être vérifié dans cette session (pas d'accès navigateur) — à confirmer côté utilisateur.

---

## v1.5.11 — 2026-08-17 — Performance scan/édition, réconciliation auteurs, corrections diverses

### Performance

- **Édition de métadonnées** (album seul ou lot sur une série) : chaque écriture recompressait inutilement toutes les images du CBZ en DEFLATE pour ne changer qu'un petit XML. Les images (déjà compressées) sont désormais stockées telles quelles (`ZIP_STORED`), seul `ComicInfo.xml` reste compressé. L'édition en lot est en plus parallélisée (4 fichiers en simultané) au lieu d'un traitement strictement séquentiel — une édition sur 60 albums qui prenait plusieurs minutes se fait maintenant en quelques secondes.
- **Scan de bibliothèque** : chaque fichier était entièrement rouvert et relu à chaque scan, même sans aucun changement. Une nouvelle colonne (date de modification du fichier) permet de sauter entièrement l'ouverture de l'archive pour tout fichier inchangé depuis le dernier scan — vérifié : sur un fichier "touché" parmi 59, seul celui-là est retraité. Accélère fortement les scans répétés sur une grosse bibliothèque, y compris celui déclenché automatiquement en fin d'import.

### Nouveau — Réconciliation auteurs/éditeurs

- La page Auteurs reflète fidèlement les orthographes exactes présentes dans les fichiers (pas de fusion automatique/silencieuse).
- Détection de doublons probables à 3 niveaux de fiabilité : casse/accents ("Le Lombard" / "Le lombard"), mots dans un ordre différent ("Franquin André" / "André Franquin"), une chaîne contenue dans l'autre ("Bamboo" / "Bamboo Éditions", signalé "à vérifier" car moins fiable).
- Fusion explicite : l'utilisateur choisit l'orthographe à garder parmi les variantes détectées : réécrit réellement le champ dans le `ComicInfo.xml` de tous les albums concernés (et la base), sans jamais rien appliquer automatiquement.

### Corrections

- **Import PDF→CBZ** : après conversion, l'ancien tome PDF restait en base (pointant vers un fichier supprimé par `delete_source`) pendant qu'un second tome était créé pour le CBZ — doublon visible, pages illisibles sur l'ancien. Le tome existant est maintenant repointé vers le fichier converti (même `tome_id`, progression de lecture/notes/notation préservées) au lieu de laisser une ligne orpheline.
- **Renommer une série** ne renommait que la base de données, jamais le dossier sur le disque — le scan suivant recréait une série en double sous l'ancien nom (déduit du dossier). Renommer une série renomme maintenant aussi le dossier et les chemins de tous ses fichiers ; collision de nom détectée et rejetée proprement.
- **Édition en lot d'une série** écrasait silencieusement les champs non concernés (résumé, genre, ISBN…) des albums qui en avaient, en ne réécrivant que Série/Éditeur/Scénariste/Dessinateur. Repart maintenant des métadonnées existantes de chaque album.
- **Filtres auteur/scénariste/dessinateur/éditeur** (clic depuis la page Auteurs) utilisaient une correspondance par sous-chaîne — "Bamboo" remontait aussi "Bamboo Éditions" (entité différente). Corrigé en correspondance exacte (insensible casse/accents, gère les champs multi-valeurs).
- **"Albums ajoutés récemment"** sur l'accueil : la section existait déjà dans le code mais restait silencieusement vide (mauvaise source de données) — nouvel endpoint dédié, fonctionne réellement désormais.
- **Autocomplétion auteurs/éditeurs** : le pool de suggestions n'était chargé qu'une fois par session, jamais rafraîchi après une édition — un auteur tout juste ajouté n'apparaissait pas dans les suggestions ailleurs sans recharger la page. Rafraîchi automatiquement après chaque sauvegarde de métadonnées.
- **Recherche persistante entre pages** : chercher "Tintin" depuis Séries puis aller sur Auteurs laissait le filtre actif, vidant la page Auteurs à tort. La recherche se réinitialise maintenant à chaque changement de page.
- Bouton "Importer d'autres albums" ajouté à l'étape 3 de l'import.

### Contexte
Session issue d'un signalement de bug ("les métadonnées ne s'affichent plus" en production) qui a mené, après investigation approfondie (voir v1.5.10), à corriger le vrai problème de fond (`docker-compose.yml`). Le reste de cette session a traité une série de remontées ergonomiques et de bugs de fond découverts en marge (édition lente, doublons de casse, filtres trop larges, données écrasées silencieusement).

### Validation
Chaque correctif testé en conteneur Docker réel avec des cas concrets reproduits (fichiers de test dédiés, avant/après comparé), pas seulement une relecture de code.

---

## v1.5.10 — 2026-08-16 — Correctifs permissions NAS & robustesse lecteur

### Corrections critiques

- **`docker-compose.yml`** : `PUID`/`PGID` étaient codés en dur (`PUID=1000`) au lieu d'une substitution de variable (`PUID=${PUID:-1000}`) — toute valeur personnalisée dans `.env` était silencieusement ignorée, l'app tournait toujours avec l'identité par défaut quoi que l'utilisateur configure. C'est la cause racine d'un bug de lecture généralisé sur NAS (ACL Synology n'autorisant pas l'UID/GID réellement utilisé). Corrigé.
- **Crash en cascade sur permission refusée** : plusieurs endpoints (`/api/tomes/{id}/file-info`, `/api/reader/{id}/info`, la page "Vérification") plantaient (erreur 500 non gérée) dès qu'un seul fichier de la bibliothèque était illisible par le process — et dans le cas du panneau de métadonnées, un seul appel en échec empêchait l'affichage de métadonnées pourtant correctement récupérées par ailleurs (`Promise.all` qui échoue en bloc). Tous corrigés pour dégrader proprement plutôt que planter.
- **`filename_parser.py`** (trouvé lors de l'investigation Albums manquants, corrigé cette session-ci également en pratique) : nouveau pattern pour les fichiers numérotés sans titre distinct.

### Nouveau — Diagnostic de permissions média

- Log clair au démarrage du conteneur si l'identité de l'application (UID/GID) ne correspond pas au propriétaire réel du dossier média, avec les valeurs exactes à renseigner dans `.env`.
- Bandeau discret dans l'application (visible seulement si un problème est détecté) reprenant la même information, pour les utilisateurs qui ne consultent pas les logs.
- Nouveau type de problème "Fichier illisible (permission refusée)" dans la page Vérification (Configuration), distinct de "Fichier introuvable".
- Aucune détection/adoption automatique d'identité : uniquement informatif, pas de changement de comportement silencieux — le réglage `PUID`/`PGID` reste entièrement à la charge de l'utilisateur, dans son propre `.env`.

### Contexte
Investigation partie d'un rapport « les métadonnées ne s'affichent plus » sur NAS Synology en production, ayant révélé successivement : des endpoints non protégés contre les erreurs de permission, un vrai problème d'ACL Synology (accès nommé à des comptes précis + groupe `administrators`), puis — après une session de diagnostic approfondie (ACL Synology, `/proc/1/status`, comparaison avec deux autres assistants IA consultés en parallèle par l'utilisateur) — la cause racine réelle : `PUID`/`PGID` jamais appliqués à cause du bug `docker-compose.yml`. Plusieurs pistes de correctif (auto-détection d'UID, groupes supplémentaires, groupe NAS dédié) ont été examinées puis écartées au profit d'une solution strictement informative, jugée plus sûre et plus conforme aux conventions de l'écosystème self-hosted (PUID/PGID explicite, à la charge de l'utilisateur).

### Validation
Chaque correctif reproduit et vérifié en conditions réelles : erreur de permission simulée localement (fichier rendu inaccessible), requêtes directes vers le serveur de production du NAS pendant l'investigation, logique de détection UID/GID vérifiée par tests unitaires (limitation connue : Docker Desktop pour Mac virtualise l'appartenance des bind mounts, rendant un vrai désaccord UID impossible à reproduire localement).

---

## v1.5.9 — 2026-08-16 — Albums manquants

### Nouvelle fonctionnalité — Détection d'albums manquants

- Nouvelle page "Albums manquants" (nav principale) : compare, pour chaque série suivie, les numéros de tome publiés sur Bedetheque à ceux présents dans la bibliothèque. Détecte aussi bien un nouveau tome au-dessus du dernier connu qu'un trou dans la collection (diff d'ensemble, pas juste "plus grand que le dernier").
- Ne considère que les albums à numérotation purement numérique (hors-séries "HS", intégrales "INT", best-of… ignorés, non comparables à une suite de tomes classique).
- Scan déclenché manuellement ("Rechercher les albums manquants"), en tâche de fond avec barre de progression, résultat du dernier scan mémorisé (pas besoin de relancer pour consulter la page). Requêtes espacées de 1,5s vers Bedetheque (même politesse que l'index de recherche existant) : ~2 minutes pour 79 séries, quel que soit le nombre d'albums manquants trouvés.
- Résultats présentés en grille de vignettes (même style que la page Albums), groupés et clairement séparés par série, avec filtre de recherche par nom de série.
- Section "Séries non trouvées" pour les séries dont le nom n'a pas pu être rapproché d'une fiche Bedetheque (lien direct vers la fiche série de l'app).
- Gestion des exceptions unifiée dans "Gérer le suivi" : exclusion d'une série entière (recherche + réactivation, avec revérification immédiate de la série à la réactivation) et ignorance d'un album précis (croix au survol d'une vignette, persiste à travers les scans suivants, réversible).
- Badge de comptage sur l'icône de navigation (état partagé, mis à jour après chaque action sans recharger la page).

### Corrections

- **`filename_parser.py`** : les fichiers numérotés sans titre distinct par tome (convention courante pour les mangas, ex. `Série - T01.cbz`) ne matchaient aucun pattern de parsing et voyaient leur numéro de tome silencieusement perdu (interprété à tort comme un titre). Nouveau pattern dédié — corrige ce champ dans toute l'app, pas seulement cette fonctionnalité. Un re-scan de la bibliothèque est nécessaire pour corriger les tomes déjà en base.
- **Résolution série → fiche Bedetheque** : le rapprochement approximatif acceptait par erreur des entrées d'index très courtes ("D", "Al"…) comme correspondance dès qu'elles étaient une sous-chaîne du nom recherché. Restreint au sens utile (nom local ⊂ nom complet Bedetheque), condition plus stricte pour éviter les faux rattachements.

### Validation
Chaque itération testée en conteneur Docker réel sur une bibliothèque de test (scan complet, ignorer/réafficher, exclure/réactiver, vérification des logs) avant passage à l'étape suivante.

---

## v1.5.8 — 2026-08-15 — Scraper Bedetheque & refonte de l'import

### Nouvelle fonctionnalité — Scraper Bedetheque.com

- Troisième source de métadonnées (aux côtés de Google Books et ComicVine) : récupère série, tome, titre, auteurs, éditeur, année et couverture depuis bedetheque.com.
- Scraping **poli** : User-Agent honnête et identifié, aucun contournement de la protection anti-bot du site, aucune imitation de navigateur, aucun identifiant de connexion utilisé.
- Le moteur de recherche en ligne du site étant protégé (dégradation silencieuse des résultats pour tout client non-navigateur), la recherche s'appuie sur un **index local pré-construit** (~76 500 séries, embarqué dans l'image, ~7 Mo), rafraîchissable manuellement depuis Configuration → Bibliothèque. Limiteur de débit dédié (6 requêtes/min) sur l'endpoint de recherche.
- Gestion des articles ("Le", "La", "Les"…) réordonnés en fin de nom, format d'auteur harmonisé ("Prénom Nom"), doublons d'éditions en langue étrangère conservés (non filtrés — choix délibéré), tri des résultats par numéro de tome recherché.

### Refonte de l'import (étape 2)

- Un seul modèle de renommage, configuré une fois dans Configuration → Bibliothèque, appliqué automatiquement à tous les imports (au lieu d'un bloc de renommage personnalisable à chaque import) ; modèle vide = pas de renommage. Bouton "Réinitialiser" ajouté à côté de "Sauvegarder le modèle".
- Détection des doublons/conflits déplacée à l'étape 1 (liste de fichiers), avec avertissements en direct dès la sélection.
- Étape 2 simplifiée à 2 tableaux (Métadonnées, Convertir), toujours visibles, sans accordéon à déplier.
- Tableau Métadonnées : le nom de fichier affiché reflète maintenant en direct le renommage (mis à jour à la saisie des métadonnées et après une recherche en ligne) au lieu du nom d'origine figé, sans l'extension d'origine trompeuse (ne correspondait ni à l'ancien fichier ni au futur, notamment lors d'une conversion PDF→CBZ). Info-bulle au survol cohérente avec le nom affiché. Icône de recherche en ligne agrandie.

### Corrections

- **`renamePattern.js`** : un "T" orphelin apparaissait dans le nom final quand aucun numéro de tome n'était détecté (ex. `"Série - T - Titre"`), produisant un nom confus — perçu à tort comme deux fichiers distincts sur les noms d'origine longs/mal encodés. Le "T" est désormais retiré avec le token `{Numéro}` quand celui-ci est vide.
- **`ScraperResultCard.vue`** : le badge de numéro de tome pouvait être masqué par la troncature du titre trop long.
- **`scraper.py`** : la priorité entre la requête tapée dans la modale et la série pré-remplie était inversée — une nouvelle recherche était ignorée tant que la série d'origine restait non vide.

### Validation
Build backend + frontend, puis conteneur Docker réel à chaque itération (health check, `/api/settings`, `/api/import/parse`) pour valider les corrections de rendu et de format de nom.

---

## v1.5.7 — 2026-08-13 — Performance scan/import & nettoyage dette technique

Suite directe de la session v1.5.6 : traitement des items identifiés lors de l'audit mais volontairement laissés de côté (non critiques).

### Corrections — Performance

- **Scan (`scanner.py`)** : le lookup de série par nom faisait une requête DB séparée pour chaque fichier. Un cache `{nom: series_id}` partagé pendant tout le scan élimine cette requête pour tout fichier dont la série a déjà été vue plus tôt dans le même scan.
- **Scan (`scanner.py`)** : la génération des covers (extraction + resize) tournait en série, un fichier à la fois, à l'intérieur de la boucle bloquante d'indexation DB. Sortie de la boucle et exécutée après coup, 4 en parallèle (`asyncio.gather` + semaphore).
- **Import (`ImportView.vue`)** : les requêtes `parseFilename`/`checkFile` étaient tirées en `Promise.all` sans limite — un dossier de 150+ fichiers envoyait autant de requêtes simultanées. Limitées à 6 en concurrence (nouveau `utils/concurrency.js`). Le suivi des résolutions d'image (`imageSizes`) recopiait tout l'objet à chaque résolution (coût O(n²) sur un gros import) ; mutation directe de la clé désormais.

### Corrections — Bugs

- **Conversion (`converter_service.py`)** : un fichier `.cbz` existant pouvait être silencieusement écrasé si un fichier homonyme d'un autre format (ex. `Album.pdf`) était converti à côté. Erreur explicite désormais, sauf pour la recompression légitime en place.
- **Lecteur (`ReaderView.vue`)** : pas de rechargement si l'URL change sans démontage du composant (contrairement à `SeriesDetailView`/`TomeDetailView`). Ajout du `watch(route.params.id)` correspondant, avec état d'erreur visible en cas d'échec de chargement.
- **Gestion d'erreur silencieuse** : `StatsView.vue`, `MetadataDrawer.vue`, `CoverPickerModal.vue` et `stores/reader.js:loadTome` n'avaient aucun `try/catch` — spinner infini ou action sans feedback en cas d'échec réseau. Erreurs désormais catchées et remontées à l'utilisateur (notification ou état dédié).

### Nettoyage

- **`backend/core`** (lien symbolique cassé vers une ancienne machine) et **`core_compat.py`** (devenu inutile) supprimés.
- **`/api/health`** lit désormais la version depuis le fichier `VERSION` au lieu d'une valeur codée en dur (`"1.0.0"`).
- **`schemas.py:LoginIn`** (vestige d'une auth jamais implémentée) et **`api/library.js:deleteSeries`** (défini deux fois à l'identique) supprimés.
- **Logique de pattern de renommage** unifiée dans `frontend/src/utils/renamePattern.js`, utilisée par `ImportView.vue` et `RenameModal.vue` — élimine la duplication signalée lors de l'audit. `RenameModal.vue` bénéficie au passage du nettoyage des séparateurs orphelins (`" - - "` → `" - "`) qui n'existait jusque-là que côté import.
- **`.env` local** : `MEDIA_ROOT` pointait vers le chemin d'une ancienne machine (`/Users/macbookair/...`), corrigé vers le chemin réel.

### Validation
Build backend + frontend, puis conteneur Docker réel : scan (8 séries/59 fichiers), lecture, et re-vérification qu'une des failles corrigées en v1.5.6 reste bloquée.

---

## v1.5.6 — 2026-08-13 — Audit sécurité & robustesse

### Corrections

**Sécurité — path traversal**
- **Import (`/api/import/file`)** : le `filename` reçu en form-data n'était pas validé — un chemin absolu ou `../` pouvait écrire hors de MEDIA_ROOT (Pathlib remplace tout le chemin quand on joint un chemin absolu). Filename désormais validé (rejet des séparateurs et de `..`).
- **Import (`cancel-cleanup`)** : les chemins fournis par le client étaient supprimés sans vérifier qu'ils appartiennent à la bibliothèque. Chemins désormais confinés à `LIBRARY_PATH`.
- **Import (`new_series_name`)** : seuls les `/` en début/fin de nom étaient nettoyés ; `../../` passait tel quel et pouvait créer un dossier hors MEDIA_ROOT. Nom de série désormais validé comme un simple nom de dossier, destination revérifiée après résolution.
- **Fallback SPA (`main.py`)** : le chemin d'URL servait de fichier statique sans normalisation, permettant de lire des fichiers arbitraires hors de `backend/static/`. Chemin désormais résolu et confiné via `is_relative_to`.
- **Conversion (`dest_path`)** : la destination personnalisée d'une conversion n'était jamais validée contre la bibliothèque. Désormais rejetée si hors de `LIBRARY_PATH`.
- **Configuration (`browse_folders`)** : le contrôle anti-évasion utilisait `str.startswith()` sans séparateur de fin, contournable par un dossier voisin (`/media/comics-evil` passe le test pour `/media/comics`). Remplacé par `Path.is_relative_to()`.

**Docker — persistance des réglages**
- **Bug** : les réglages modifiés depuis la page Configuration (sous-dossier bibliothèque, clés API) étaient écrits dans un `.env` relatif au dossier de travail du conteneur (`/app/.env`), qui n'est pas dans le volume `/data`. Résultat : les changements étaient perdus à chaque recréation du conteneur (mise à jour d'image), pas seulement à un simple restart.
- **Correction** : écriture désormais dans `/data/.env` (volume persistant) quand disponible. Le chargement au démarrage applique explicitement ces valeurs par-dessus les variables d'environnement du conteneur, car Docker Compose (`env_file: .env`) injecte le `.env` de l'hôte comme variables d'environnement réelles, normalement prioritaires sur tout fichier `.env` lu par l'application — sans ce correctif, les valeurs persistées restaient masquées par le `.env` hôte au redémarrage. Vérifié par un test réel : build + conteneur + réglage via l'API + recréation complète du conteneur → réglage toujours présent.

**Frontend — races conditions & robustesse**
- **Scan (`stores/library.js`)** : `triggerScan()` pouvait ouvrir plusieurs `EventSource` concurrents (ex. scan manuel + fin d'import), chacun écrivant dans le même state de progression → barre de progression incohérente. Un scan déjà suivi n'ouvre plus de second flux ; `onerror` repasse maintenant le statut à `error` au lieu de laisser l'UI bloquée sur "running" indéfiniment.
- **Lecteur (`stores/reader.js`)** : la sauvegarde différée de la progression de lecture (`_scheduleSave`, 800ms) n'était jamais annulée lors d'un changement de tome — un changement rapide de lecture pouvait écraser la progression du nouveau tome avec la page de l'ancien. Le timer est désormais annulé dans `loadTome()`.
- **Import (`ImportView.vue`)** : quitter la page `/import` pendant un upload/conversion en cours laissait la boucle d'import continuer en tâche de fond sans plus aucune UI pour la suivre, avec un risque de collision avec un scan déclenché ailleurs. Un `onUnmounted` déclenche désormais la même annulation propre que le bouton "Annuler".

### Audit (sans changement de code)
Revue complète backend + frontend (performance scan, N+1 requêtes import, gestion d'erreurs silencieuses sur plusieurs vues, dette technique `core_compat.py`/`LoginIn` vestiges d'un ancien projet) — items non critiques laissés pour une session ultérieure.

---

## v1.5.5 — 2026-04-14 — Qualité conversion PDF, import & UI

### Nouveau
- **Tri des colonnes page Auteurs** : clic sur les en-têtes Nom / Séries / Albums pour trier (asc/desc), indicateur visuel actif
- **Lien GitHub auteur** : page À propos → onglet Auteur → lien cliquable `github.com/sirdj3y`

### Corrections
- **Qualité conversion PDF drastiquement améliorée** : les pages PDF sont désormais extraites à leur résolution native (via `page.get_images()`) au lieu d'être re-rendues à 108 DPI. Élimine la double compression JPEG (MuPDF → Pillow) qui dégradait la qualité même en preset "Original". Pour les pages composites, fallback rendu à 216 DPI en PNG (lossless).
- **Import — extension protégée** : le champ de renommage à l'étape 2 affiche uniquement le nom sans extension ; l'extension (`.pdf`, `.cbz`, etc.) est affichée séparément en lecture seule, évitant les suppressions accidentelles.
- **Import — fallback extension manquante** : si le champ `filename` reçu par le backend n'a pas d'extension, fallback automatique sur le nom du fichier multipart.
- **Cover picker — couvertures complètes** : `object-fit: contain` au lieu de `cover` — toutes les couvertures s'affichent entièrement quel que soit leur ratio.
- **Crash `s.authors.writers is undefined`** : `LibraryView` et `MetadataForm` accédaient à `library.authors.writers` (inexistant) au lieu de `library.authorNames.writers`.
- **Suppression série — dossier nettoyé** : avant de tenter `rmdir`, les fichiers résiduels connus (`.meta.json`, `.converting.cbz`, `.DS_Store`, `._*`, `Thumbs.db`) sont supprimés automatiquement.

---

## v1.5.4 — 2026-04-13 — Corrections import

### Corrections
- **Timeout scan post-import** — `waitForScan` attendait max 30s avant de rediriger ; porté à 150s pour les bibliothèques de 2000+ fichiers sur NAS Synology.
- **Requêtes image-size sur fichiers non sélectionnés** — à l'étape 2 de l'import, les requêtes `getImageSize` étaient envoyées pour tous les fichiers (y compris ceux décochés à l'étape 1) ; seuls les fichiers sélectionnés sont désormais interrogés.

---

## v1.5.3 — 2026-04-13 — Performance import & robustesse

### Nouveau
- **Import sans scan intermédiaire** : le fichier uploadé est désormais enregistré en DB immédiatement et retourne son `tome_id` directement. La conversion démarre sans attendre un scan complet de la bibliothèque. Sur 2000+ fichiers (NAS Synology), cela élimine N scans complets par import (un seul scan final subsiste).

### Corrections
- **Bug #25 : sidecar `.meta.json` orphelin** — si la conversion échoue, le fichier `.meta.json` est maintenant supprimé proprement.
- **Bug #26 : double écriture des métadonnées** — le frontend écrivait les métadonnées après conversion alors que le sidecar backend le faisait déjà. Le write frontend redondant a été supprimé.
- **Fuite mémoire `_progress`** — les entrées de jobs de conversion terminés sont purgées de la mémoire après 5 minutes (important pour les NAS qui tournent en continu).
- **CBZ non coché automatiquement à l'import** — sélectionner un preset de qualité ne coche plus les fichiers CBZ/ZIP (déjà dans le bon format). Seuls les CBR/PDF sont cochés automatiquement.
- **ComicInfo.xml préservé à la recompression** — recompresser un CBZ conserve maintenant son XML existant dans le fichier de sortie.
- **FILE ERROR scanner** — un fichier inaccessible lors du scan met maintenant le tome en `status=error` en DB au lieu de simplement loguer l'erreur.
- **Fallback `lookup-tomes`** — si un fichier n'est pas encore en DB (scan en retard), le endpoint le scanne à la volée au lieu d'attendre.
- **`backend/static/` exclu du contexte Docker** — les fichiers frontend précompilés ne sont plus copiés dans l'image Docker, garantissant que le frontend est toujours recompilé depuis les sources.

---

## v1.5.2 — 2026-04-13 — Corrections compatibilité Synology & conversion

### Corrections
- **Bug #23 : CBR/RAR5 non extractibles sur Synology** — `unrar-free` ne supporte pas le format RAR5 (archives CBR modernes). Remplacé par `unrar` (non-free) dans le Dockerfile via le dépôt `bookworm non-free`.
- **Bug #24 : corruption potentielle lors de la recompression CBZ** — le convertisseur écrivait directement sur le fichier source (src == dest) sans fichier temporaire. Si le scanner tournait en parallèle, il pouvait lire un CBZ tronqué en cours d'écriture. Corrigé : écriture vers `fichier.converting.cbz` puis déplacement atomique vers la destination finale.

---

## v1.5.1 — 2026-04-13 — Correction métadonnées après conversion

### Corrections
- **Bug #22 : métadonnées non écrites dans le CBZ après import+conversion** — lors de l'import d'un CBR/PDF avec métadonnées et conversion activée, le `ComicInfo.xml` n'était pas écrit dans le fichier converti. Corrigé via un fichier sidecar `.meta.json` créé à l'upload, lu par le convertisseur après la conversion réussie, puis supprimé automatiquement.
- Les CBZ/ZIP importés sans conversion continuaient de recevoir les métadonnées directement à l'upload (comportement inchangé).

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
