"""Import, étape 1 : dépôt de fichiers dans la zone."""
from helpers import goto


def test_deposer_des_fichiers(page):
    goto(page, "/import")
    zone = page.locator(".file-drop-zone")
    zone.wait_for()
    # DataTransfer construit dans la page : un dépôt simulé (le vrai dépôt d'un dossier depuis
    # le Finder n'est pas reproductible ici ; son parcours est testé dans
    # frontend/tests/droppedFiles.test.js).
    handle = page.evaluate_handle("""() => {
        const dt = new DataTransfer()
        for (const name of ['Akira - T03.cbz', 'Akira - T04.cbz', 'notes.txt'])
            dt.items.add(new File(['x'], name))
        return dt
    }""")
    zone.dispatch_event("drop", {"dataTransfer": handle})
    preview = page.locator(".files-preview")
    preview.wait_for()
    text = preview.inner_text()
    assert "Akira - T03.cbz" in text and "Akira - T04.cbz" in text
    assert "notes.txt" not in text, "les formats non acceptés sont écartés"
