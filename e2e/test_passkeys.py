"""Passkeys dans l'interface, avec l'authentificateur virtuel de Chromium (équivalent de
Touch ID / Face ID, piloté par le protocole de débogage du navigateur)."""
from helpers import dialog, gone, goto


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
    page.get_by_role("button", name="Ajouter une passkey").click()
    box = dialog(page)
    box.first.wait_for()
    box.locator("input").fill("Test e2e")
    box.get_by_role("button", name="Continuer").click()
    assert gone(box, timeout=10)
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
