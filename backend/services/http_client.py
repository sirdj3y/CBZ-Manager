"""
Client HTTP commun des services tiers (Bedetheque.com, ComicVine, Google Books).

Un point unique pour ce que chaque scraper gérait à sa façon (ou pas du tout) :
- **rythme** : les requêtes vers un même service sont sérialisées et espacées d'un
  intervalle minimum, quel que soit l'appelant (recherche, import, scan des albums
  manquants, construction de l'index…) — un seul processus uvicorn (voir Dockerfile), donc un
  verrou en mémoire suffit ;
- **reprises** : 429 / 5xx / erreur réseau → nouvelle tentative avec attente croissante
  (Retry-After respecté s'il est fourni) ;
- **erreurs claires** : `ServiceError.kind` distingue « introuvable » (404 — la ressource
  n'existe pas) de « indisponible » (panne passagère, à réessayer plus tard), « quota » et
  « refusé » (clé API invalide). Sans cette distinction, une panne de Bedetheque pendant le
  scan des albums manquants marquait l'URL confirmée d'une série comme introuvable ;
- **User-Agent** explicite, avec la version de l'app.
"""
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "dev"
# ASCII uniquement : un en-tête HTTP n'accepte pas les accents (UnicodeEncodeError à l'envoi).
USER_AGENT = f"CBZManager/{APP_VERSION} (gestionnaire de bibliotheque BD personnel, usage non-commercial)"


class ServiceError(Exception):
    """kind : "not_found" | "unavailable" | "quota" | "unauthorized"."""

    def __init__(self, service: str, kind: str, status: int | None = None, detail: str = ""):
        self.service, self.kind, self.status = service, kind, status
        super().__init__(detail or f"{service} : {kind} ({status})")

    @property
    def message(self) -> str:
        """Message affichable à l'utilisateur."""
        return {
            "not_found": f"{self.service} : page ou ressource introuvable.",
            "quota": f"{self.service} : limite de requêtes atteinte — réessayez plus tard.",
            "unauthorized": f"{self.service} : clé API refusée — vérifiez-la dans les paramètres.",
        }.get(self.kind, f"{self.service} ne répond pas pour le moment — réessayez dans quelques minutes.")


@dataclass
class ThrottledClient:
    service: str
    min_interval: float          # secondes minimum entre deux requêtes vers ce service
    timeout: float = 20.0
    max_attempts: int = 3        # tentative initiale comprise
    backoff: float = 2.0         # attente avant la 2e tentative (doublée ensuite)
    extra_headers: dict | None = None
    transport: httpx.AsyncBaseTransport | None = None  # tests : httpx.MockTransport

    def __post_init__(self):
        self._last = 0.0
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self) -> asyncio.Lock:
        # Un verrou par boucle d'événements : l'app n'en a qu'une, les tests en créent plusieurs.
        loop = id(asyncio.get_running_loop())
        return self._locks.setdefault(loop, asyncio.Lock())

    async def _wait_turn(self):
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    async def get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET avec rythme et reprises. Renvoie la réponse (2xx/3xx suivis) ou lève ServiceError."""
        headers = {"User-Agent": USER_AGENT, **(self.extra_headers or {})}
        last_status = None
        async with self._lock():
            async with httpx.AsyncClient(headers=headers, timeout=self.timeout, follow_redirects=True,
                                         transport=self.transport) as client:
                for attempt in range(self.max_attempts):
                    await self._wait_turn()
                    try:
                        resp = await client.get(url, params=params)
                    except httpx.HTTPError:
                        resp = None
                    if resp is not None:
                        last_status = resp.status_code
                        if resp.status_code < 400:
                            return resp
                        if resp.status_code == 404:
                            raise ServiceError(self.service, "not_found", 404)
                        if resp.status_code in (401, 403):
                            raise ServiceError(self.service, "unauthorized", resp.status_code)
                        if resp.status_code != 429 and resp.status_code < 500:
                            raise ServiceError(self.service, "unavailable", resp.status_code)
                    if attempt == self.max_attempts - 1:
                        break
                    delay = self.backoff * (2 ** attempt)
                    retry_after = resp.headers.get("Retry-After") if resp is not None else None
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, min(float(retry_after), 60.0))
                    await asyncio.sleep(delay)
        raise ServiceError(self.service, "quota" if last_status == 429 else "unavailable", last_status)


# Instances partagées — intervalle choisi par service :
# Bedetheque.com est un site (pas une API) lu page par page : 1,5 s, comme le délai de
# courtoisie qui existait déjà pour le scan des albums manquants et l'index.
BEDETHEQUE = ThrottledClient("Bedetheque.com", min_interval=1.5, extra_headers={"Accept-Language": "fr-FR,fr;q=0.9"})
# ComicVine : limite documentée par ressource et par heure, plus une détection des rafales.
COMICVINE = ThrottledClient("ComicVine", min_interval=1.0, timeout=15.0, extra_headers={"Accept": "application/json"})
GOOGLE_BOOKS = ThrottledClient("Google Books", min_interval=0.2, timeout=15.0)
