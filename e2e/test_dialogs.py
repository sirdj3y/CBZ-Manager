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
    page.wait_for_timeout(300)  # fin de l'animation d'ouverture (un humain ne clique pas plus vite)
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


def _series_action(page, item):
    open_first_series(page)
    page.locator('.hero-btn[aria-label="Plus d\'options"]').click()
    menu(page).get_by_text(item).click()
    dialog(page).first.wait_for()


def test_renommer(page):
    _series_action(page, "Renommer les fichiers")
    assert in_viewport(dialog(page).locator(".modal-box"))
    page.keyboard.press("Escape")
    assert gone(dialog(page))


def test_convertir_et_carte_de_comparaison(page):
    _series_action(page, "Convertir les fichiers")
    page.locator(".quality-info-icon").hover()
    card = page.locator("[data-slot=hover-card-content]")
    assert in_viewport(card), "la carte de comparaison doit s'afficher à l'écran, au-dessus de la modale"
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(10, 450)
    assert gone(dialog(page))


def test_nouvelle_smart_list(page):
    goto(page, "/")
    page.locator('button[aria-label="Nouvelle liste"]').first.click()
    dialog(page).first.wait_for()
    assert dialog(page).get_by_text("Nouvelle Smart list").count() == 1
    page.keyboard.press("Escape")
    assert gone(dialog(page))


def test_metadonnees_serie_confirmation_imbriquee(page):
    open_first_series(page)
    page.get_by_role("button", name="Éditer").first.click()
    dialog(page).first.wait_for()
    page.locator('button[aria-label="Plus d\'actions"]').click()
    menu(page).get_by_text("Supprimer la série").click()
    confirm = page.locator(".confirm-title", has_text="Supprimer la série ?")
    confirm.wait_for()
    assert dialog(page).count() == 2
    # Échap ferme la couche du dessus seulement, puis la modale.
    page.keyboard.press("Escape")
    confirm.wait_for(state="detached")
    assert dialog(page).count() == 1
    page.wait_for_timeout(300)  # fin de l'animation de fermeture de la confirmation
    # Le focus revient dans la modale (le « Supprimer » du menu qui avait ouvert la
    # confirmation n'existe plus) : Échap y répond encore.
    assert page.evaluate("document.activeElement.closest('[data-slot=dialog-content]') !== null")
    page.keyboard.press("Escape")
    assert gone(dialog(page))


def test_scraper_depuis_le_tiroir_echap_ne_ferme_que_le_scraper(page):
    open_first_series(page)
    tome = page.locator(".tome-card").first
    tome.hover()
    tome.locator('button[aria-label="Plus d\'options"]').click()
    menu(page).get_by_text("Rechercher les métadonnées").click()
    scraper = dialog(page)
    scraper.first.wait_for()
    assert scraper.locator(".modal-title").inner_text() == "Rechercher en ligne"
    page.keyboard.press("Escape")
    assert gone(scraper)
    # Le tiroir de métadonnées (toujours ouvert) reste là.
    assert page.locator(".modal-backdrop").count() == 1


def test_confirmation_suppression_album_annulable(page):
    goto(page, "/books")
    card = page.locator(".book-card").first
    card.hover()
    card.locator('button[aria-label="Plus d\'options"]').click()
    menu(page).get_by_text("Supprimer l'album").click()
    box = dialog(page)
    box.first.wait_for()
    assert box.locator(".confirm-title").inner_text() == "Supprimer l'album ?"
    n_before = page.locator(".book-card").count()
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    assert gone(box)
    assert page.locator(".book-card").count() == n_before, "annuler ne doit rien supprimer"


def test_confirmation_effacer_historique(page):
    goto(page, "/logs")
    page.get_by_role("button", name="Effacer l'historique").click()
    dialog(page).first.wait_for()
    page.wait_for_timeout(300)
    page.mouse.click(10, 450)
    assert gone(dialog(page))


def test_lecteur_tome_suivant(page):
    open_first_series(page)
    page.locator(".tome-info").first.click()
    page.wait_for_url("**/tomes/*")
    tome_id = page.url.rstrip("/").split("/")[-1]
    goto(page, f"/read/{tome_id}")
    page.locator(".reader-toolbar-top").wait_for()
    for _ in range(6):  # 3 pages : aller au-delà de la dernière
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(150)
    box = dialog(page)
    box.first.wait_for()
    assert box.locator(".resume-title").inner_text() == "Tome suivant"
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    assert gone(box)
    assert "/read/" in page.url, "Échap ferme la fenêtre sans quitter le lecteur"
