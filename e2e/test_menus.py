"""Menus, panneaux et infobulles (shadcn-vue) : ils s'ouvrent, à l'écran, près de leur bouton."""
import pytest
from helpers import dialog, gone, goto, in_viewport, menu, open_first_series, popover


@pytest.mark.parametrize("label", ["Scanner", "Nouveautés", "Mon compte"])
def test_menus_du_haut(page, label):
    goto(page, "/")
    page.locator(f'button[aria-label="{label}"]').click()
    assert in_viewport(menu(page)), f"menu {label} hors écran"
    page.keyboard.press("Escape")
    assert gone(menu(page))


def test_menu_carte_serie(page):
    goto(page, "/series")
    card = page.locator(".series-card").first
    card.hover()
    card.locator('button[aria-label="Plus d\'options"]').click()
    assert in_viewport(menu(page))
    assert menu(page).get_by_text("Supprimer la série").count() == 1


def test_menus_fiche_serie(page):
    open_first_series(page)
    page.locator('.hero-btn[aria-label="Plus d\'options"]').click()
    assert in_viewport(menu(page))
    page.keyboard.press("Escape")
    gone(menu(page))
    tome = page.locator(".tome-card").first
    tome.hover()
    tome.locator('button[aria-label="Plus d\'options"]').click()
    assert in_viewport(menu(page))
    assert menu(page).get_by_text("Déplacer vers une série").count() == 1


def test_menu_fiche_album(page):
    open_first_series(page)
    page.locator(".tome-info").first.click()
    page.wait_for_url("**/tomes/*")
    page.locator('button[aria-label="Plus d\'options"]').first.click()
    assert in_viewport(menu(page))


def test_tri_et_filtres(page):
    goto(page, "/series")
    page.locator('button[aria-label="Trier"]').click()
    assert in_viewport(popover(page))
    page.keyboard.press("Escape")
    gone(popover(page))
    page.locator('button[aria-label="Filtrer"]').click()
    assert in_viewport(popover(page))


def test_lecteur_echap_ferme_le_menu_sans_quitter(page):
    open_first_series(page)
    page.locator(".tome-info").first.click()
    page.wait_for_url("**/tomes/*")
    tome_id = page.url.rstrip("/").split("/")[-1]
    goto(page, f"/read/{tome_id}")
    page.locator(".reader-dropdown-btn").click()
    assert in_viewport(menu(page))
    page.keyboard.press("Escape")
    assert gone(menu(page))
    assert "/read/" in page.url


def test_infobulle(page):
    goto(page, "/")
    btn = page.locator('button[aria-label="Mode sombre"], button[aria-label="Mode clair"]').first
    btn.hover()
    tip = page.locator("[data-slot=tooltip-content]").first
    tip.wait_for()
    assert in_viewport(tip)
    assert "Mode" in tip.inner_text()


def test_palette_de_recherche(page):
    goto(page, "/")
    page.keyboard.press("Control+k")
    dialog(page).wait_for()
    page.keyboard.type("hori")
    page.locator("[data-slot=command-item]").first.wait_for()
    page.keyboard.press("Enter")
    page.wait_for_url("**/series/*")
    assert gone(dialog(page))


def test_controles_natifs_suivent_le_theme(page):
    """Listes <select>, barres de défilement… natives : color-scheme suit le thème de l'app."""
    goto(page, "/series")
    scheme = lambda: page.evaluate("getComputedStyle(document.documentElement).colorScheme")
    dark_now = page.evaluate("document.documentElement.getAttribute('data-theme') === 'dark'")
    assert scheme() == ("dark" if dark_now else "light")
    page.locator('button[aria-label="Mode sombre"], button[aria-label="Mode clair"]').first.click()
    page.wait_for_timeout(200)
    assert scheme() == ("light" if dark_now else "dark")
