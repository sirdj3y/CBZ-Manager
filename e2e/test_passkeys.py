"""Passkeys dans l'interface, avec l'authentificateur virtuel de Chromium (équivalent de
Touch ID / Face ID, piloté par le protocole de débogage du navigateur)."""
from helpers import dialog, goto


def _virtual_authenticator(page):
    cdp = page.context.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal",
        "hasResidentKey": True, "hasUserVerification": True, "isUserVerified": True,
    }})
    return cdp


def test_ajouter_une_passkey_puis_se_connecter_avec(page, server):
    _virtual_authenticator(page)
    goto(page, "/account")
    # Depuis l'adresse publique, pas de renvoi vers elle.
    assert page.get_by_text("ouvrez l'application depuis").count() == 0
    page.get_by_role("button", name="Ajouter une passkey").click()
    # Nom saisi dans la section, sans Dialog : rien de modal par-dessus l'éventuelle fenêtre
    # d'un gestionnaire de mots de passe en extension.
    form = page.locator(".pk-form")
    form.locator("input").fill("Test e2e")
    assert dialog(page).count() == 0
    assert page.locator("[data-slot=dialog-overlay]").count() == 0
    form.get_by_role("button", name="Continuer").click()
    form.wait_for(state="detached")
    item = page.locator(".pk-item", has_text="Test e2e")
    item.wait_for()
    assert "jamais utilisée" in item.inner_text()

    # Déconnexion, puis connexion par passkey sans rien saisir.
    page.context.clear_cookies()
    page.goto("/login")
    page.get_by_role("button", name="Se connecter avec une passkey").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=10000)
    me = page.evaluate("fetch('/api/auth/me').then(r => r.json())")
    assert me["authenticated"] is True and me["username"] == "admin"

    # Nettoyage : suppression depuis Mon compte.
    goto(page, "/account")
    item = page.locator(".pk-item", has_text="Test e2e")
    assert "utilisée le" in item.inner_text()
    item.locator("button").click()
    confirm = dialog(page)
    confirm.first.wait_for()
    confirm.get_by_role("button", name="Supprimer").click()
    item.wait_for(state="detached")


def test_passkey_proposee_seulement_depuis_l_adresse_publique(page, server):
    # Même serveur ouvert par 127.0.0.1 au lieu de localhost : le bouton n'est pas proposé,
    # un lien vers l'adresse publique le remplace.
    page.context.clear_cookies()
    page.goto(server.replace("localhost", "127.0.0.1") + "/login")
    page.locator(".login-card").wait_for()
    page.get_by_text("Connexion par passkey disponible sur").wait_for()
    assert page.get_by_role("button", name="Se connecter avec une passkey").count() == 0


def test_deuxieme_passkey_sur_le_meme_appareil_message_clair(page, server):
    """Cas de l'iPhone qui a déjà la passkey du Mac (trousseau iCloud) : l'appareil refuse
    d'en créer une seconde pour le même compte ; message explicite, pas une erreur obscure."""
    _virtual_authenticator(page)
    goto(page, "/account")

    def add(name):
        page.get_by_role("button", name="Ajouter une passkey").click()
        form = page.locator(".pk-form")
        form.locator("input").fill(name)
        form.get_by_role("button", name="Continuer").click()

    add("Premier")
    page.locator(".pk-item", has_text="Premier").wait_for()
    add("Second")
    page.locator(".pk-error", has_text="Cet appareil a déjà une passkey pour ce compte").wait_for(timeout=10000)
    assert page.locator(".pk-item").count() == 1

    # Nettoyage
    page.locator(".pk-item", has_text="Premier").locator("button").click()
    confirm = dialog(page)
    confirm.first.wait_for()
    confirm.get_by_role("button", name="Supprimer").click()
    page.locator(".pk-item").first.wait_for(state="detached")
