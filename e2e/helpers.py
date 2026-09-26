import time

from conftest import HEIGHT, WIDTH


def in_viewport(locator, timeout=3.0) -> bool:
    """Visible en entier à l'écran — un menu mal ancré reste hors champ (translate -200 %).
    Attend que l'élément apparaisse et que Reka UI ait fini de le positionner (asynchrone)."""
    locator.first.wait_for(timeout=timeout * 1000)
    deadline = time.monotonic() + timeout
    while True:
        bb = locator.first.bounding_box()
        ok = bool(bb) and bb["x"] >= 0 and bb["y"] >= 0 and bb["x"] + bb["width"] <= WIDTH + 1 and bb["y"] + bb["height"] <= HEIGHT + 1
        if ok or time.monotonic() > deadline:
            return ok
        time.sleep(0.05)


def gone(locator, timeout=3.0) -> bool:
    locator.first.wait_for(state="detached", timeout=timeout * 1000)
    return True


def menu(page):
    return page.locator("[data-slot=dropdown-menu-content]")


def popover(page):
    return page.locator("[data-slot=popover-content]")


def dialog(page):
    return page.locator("[data-slot=dialog-content]")


def goto(page, path):
    """Navigue et attend que l'app (barre du haut) soit montée."""
    page.goto(path)
    page.locator(".topbar, .reader-toolbar").first.wait_for()


def open_first_series(page):
    goto(page, "/series")
    page.locator(".series-card").first.click()
    page.wait_for_url("**/series/*")
    page.locator(".tome-card").first.wait_for()
