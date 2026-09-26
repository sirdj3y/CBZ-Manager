"""Modales (AppDialog) : ouverture, focus, autocomplétion, fermeture."""
from helpers import dialog, gone, goto, in_viewport, menu, open_first_series


def _open_move(page):
    open_first_series(page)
    tome = page.locator(".tome-card").first
    tome.hover()
    tome.locator('button[aria-label="Plus d\'options"]').click()
    menu(page).get_by_text("Déplacer vers une série").click()
    dialog(page).wait_for()


def test_deplacer_autocompletion_dans_la_modale(page):
    _open_move(page)
    field = dialog(page).locator("input").first
    field.fill("Aki")
    suggestion = page.locator(".autocomplete-list li").first
    suggestion.wait_for()
    suggestion.click()
    assert dialog(page).count() == 1, "un clic sur une suggestion ne doit pas fermer la modale"
    assert field.input_value() == "Akira"


def test_echap_ferme_la_modale(page):
    _open_move(page)
    page.keyboard.press("Escape")
    assert gone(dialog(page))


def test_clic_a_cote_ferme_la_modale(page):
    open_first_series(page)
    page.locator('.hero-btn[aria-label="Plus d\'options"]').click()
    menu(page).get_by_text("Modifier la miniature").click()
    dialog(page).wait_for()
    page.mouse.click(10, 450)
    dialog(page).first.wait_for(state="detached")


def test_changer_mot_de_passe_focus_et_tab(page):
    goto(page, "/")
    page.locator('button[aria-label="Mon compte"]').click()
    menu(page).get_by_text("Changer le mot de passe").click()
    box = dialog(page)
    box.wait_for()
    # Le focus est dans la modale et y reste après plusieurs Tab.
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.closest('[data-slot=dialog-content]') !== null")
    page.keyboard.press("Escape")
    assert gone(dialog(page))


def test_modale_edition_groupee_ne_se_ferme_pas_au_clic_a_cote(page):
    open_first_series(page)
    page.locator(".tome-card").first.hover()
    page.locator(".tome-select").first.click()
    page.get_by_role("button", name="Éditer…").click()
    dialog(page).wait_for()
    assert in_viewport(dialog(page).locator(".modal-box"))
    page.mouse.click(10, 450)
    page.wait_for_timeout(300)
    assert dialog(page).count() == 1
