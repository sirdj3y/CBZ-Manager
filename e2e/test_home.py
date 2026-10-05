"""Page d'accueil : rangées de cartes jusqu'au bord droit de l'écran (issue #16)."""
from helpers import goto


def _check_bleed(page):
    row = page.locator(".scroll-row").first
    row.wait_for()
    content = page.locator(".home-content").bounding_box()
    r = row.bounding_box()
    header = page.locator(".section-header").first.bounding_box()
    # À droite : la rangée va jusqu'au bord de la zone de contenu, marge comprise.
    assert abs((r["x"] + r["width"]) - (content["x"] + content["width"])) <= 1, "la rangée doit aller jusqu'au bord droit"
    # À gauche : inchangé, aligné sur le titre (4 px de compensation du rognage de bordure).
    assert abs(r["x"] - (header["x"] - 4)) <= 1, "la rangée doit rester alignée sur le titre"
    # Le titre et « Tout voir » restent dans la marge normale.
    assert header["x"] + header["width"] < content["x"] + content["width"] - 10
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "défilement horizontal de la page"


def test_rangees_jusqu_au_bord_droit(page):
    goto(page, "/")
    _check_bleed(page)


def test_rangees_jusqu_au_bord_droit_smartphone(browser, server, auth_state):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, storage_state=auth_state, base_url=server)
    try:
        page = ctx.new_page()
        goto(page, "/")
        _check_bleed(page)
        r = page.locator(".scroll-row").first.bounding_box()
        assert abs((r["x"] + r["width"]) - 390) <= 1, "sur smartphone, la rangée touche le bord de l'écran"
    finally:
        ctx.close()
