"""Catalogue fixe des permissions paramétrables via un Profile (voir models.db_models.Profile
et dependencies.require_permission). Les actions les plus sensibles (gestion des comptes,
suppression/restauration de la base) restent volontairement hors de ce catalogue — toujours
réservées à l'administrateur, jamais paramétrables via un profil : déléguer la création de
comptes ouvrirait une auto-élévation de privilèges (créer un compte avec un profil plus
permissif que le sien), et la BDD n'a pas de filet de rattrapage en cas d'erreur."""

PERMISSIONS: dict[str, str] = {
    "library.read": "Parcourir la bibliothèque et lire dans le lecteur",
    "library.import": "Importer des fichiers",
    "library.scan": "Déclencher un scan / actualiser les métadonnées",
    "library.metadata_edit": "Éditer les métadonnées",
    "library.convert": "Convertir CBR/PDF en CBZ",
    "library.rename": "Renommer des fichiers",
    "library.move": "Déplacer des albums entre séries",
    "library.delete": "Supprimer ou masquer un album ou une série",
    "library.download": "Télécharger le fichier original",
    "library.missing_albums": "Albums manquants / suivi Bedetheque",
    "library.settings": "Réglages de bibliothèque, Diagnostic et Historique (hors Comptes et Sauvegarde & BDD)",
}
