"""Affichage sur smartphone (iPhone, 390 × 844)."""
import pytest


@pytest.fixture
def phone(browser, server, auth_state):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, storage_state=auth_state, base_url=server)
    page = ctx.new_page()
    yield page
    ctx.close()


def test_barre_du_haut_tient_dans_l_ecran(phone):
    phone.goto("/")
    phone.locator(".topbar").wait_for()
    for label in ["Mon compte", "Scanner", "Nouveautés"]:
        box = phone.locator(f'button[aria-label="{label}"]').bounding_box()
        assert box and box["x"] + box["width"] <= 390, f"{label} sort de l'écran"
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "défilement horizontal"
    assert phone.locator(".topbar-search").inner_text().strip() == "Rechercher"


def test_bandeau_d_accueil_avec_fond(phone):
    phone.goto("/")
    clip = phone.locator(".home-hero-bg-clip")
    clip.wait_for()
    assert clip.is_visible(), "le fond du bandeau doit rester affiché sur smartphone"
    color = phone.locator(".home-hero-title").first.evaluate("e => getComputedStyle(e).color")
    assert color == "rgb(255, 255, 255)", "titre en blanc sur le voile sombre"


def test_avatars_predefinis_dans_la_carte(phone):
    phone.goto("/account")
    grid = phone.locator(".preset-grid")
    grid.wait_for()
    card = phone.locator(".settings-section").first.bounding_box()
    for btn in grid.locator(".preset-btn").all():
        b = btn.bounding_box()
        assert b["x"] + b["width"] <= card["x"] + card["width"], "un avatar dépasse de la carte"
