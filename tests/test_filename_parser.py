import pytest

from backend.services.filename_parser import natural_sort_key, parse_filename


@pytest.mark.parametrize(
    "stem, series, number, title",
    [
        ("Akira - T01 - Akira", "Akira", "1", "Akira"),
        ("Blacksad - T03 - Âme rouge", "Blacksad", "3", "Âme rouge"),
        ("Le retour à la terre T01 - La vraie vie", "Le retour à la terre", "1", "La vraie vie"),
        ("Code Breaker Tome 01 - Titre", "Code Breaker", "1", "Titre"),
        ("Série - T 05 - Titre", "Série", "5", "Titre"),
        ("Série - TOME 7 - Titre", "Série", "7", "Titre"),
        ("Série - T13.5 - Titre", "Série", "13.5", "Titre"),
        ("Série - T7bis - Titre", "Série", "7bis", "Titre"),
        ("Série - TINT - Intégrale", "Série", "INT", "Intégrale"),
        ("Série - THS1 - Hors-série", "Série", "HS1", "Hors-série"),
        ("Série - T00 - Prologue", "Série", "0", "Prologue"),
        # Numéro sans titre (mangas)
        ("Horimiya - T01", "Horimiya", "1", None),
        ("Code Breaker Tome 01", "Code Breaker", "1", None),
        # Sans numéro
        ("Akira - Akira", "Akira", None, "Akira"),
        # Nom "plat" = titre seul (one-shot), pas une série
        ("Leave them alone", None, None, "Leave them alone"),
        # Régression : le "T" de "Talon" ne doit pas être pris pour un marqueur de tome
        ("Achille Talon T01 - Achille Talon", "Achille Talon", "1", "Achille Talon"),
        ("Achille Talon - T02 - Les Mains", "Achille Talon", "2", "Les Mains"),
    ],
)
def test_parse_filename(stem, series, number, title):
    assert parse_filename(stem) == {"series": series, "number": number, "title": title}


def test_parse_filename_vide():
    assert parse_filename("   ") == {"series": None, "number": None, "title": None}


def test_natural_sort_key_ordre_numerique():
    numbers = ["10", "2", None, "1", "HS1"]
    assert sorted(numbers, key=natural_sort_key) == ["1", "2", "10", None, "HS1"]
