"""Catalogue fermé des classifications de série — liste fixe plutôt qu'un champ libre, pour
garder le filtrage propre (pas de variantes orthographiques "Manga"/"manga"/"mangas")."""

CLASSIFICATIONS: list[str] = [
    "BD franco-belge",
    "Comics",
    "Manga",
    "Manhwa",
    "Manhua",
    "Livres illustrés",
    "Autre",
]
