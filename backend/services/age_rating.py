"""Catalogue fermé du public conseillé d'une série — même principe que classification.py
(liste fixe plutôt qu'un champ libre), et volontairement pas un passage du champ ComicInfo.xml
AgeRating : ce dernier est rarement renseigné en pratique et dans des valeurs en anglais
("Everyone"/"Teen"/…) pas présentables telles quelles dans l'interface."""

AGE_RATINGS: list[str] = [
    "Tout public",
    "Ados",
    "Adultes",
]
