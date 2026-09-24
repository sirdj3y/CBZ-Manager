"""
Small in-memory rate limiter, no external dependency.

Used both for endpoints that proxy an outbound call to a third-party service (scraper
routes — any authenticated user could otherwise hammer that third party using this app's
IP) and for /api/auth/login (brute-force protection, keyed by IP via PerKeyRateLimiter). A
single-process, single-worker deployment (see Dockerfile CMD) makes a plain in-memory
counter enough — no need for Redis or a shared store.
"""
import time
from collections import deque
from fastapi import HTTPException


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._calls: deque[float] = deque()

    def __call__(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.period_seconds:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            raise HTTPException(
                status_code=429,
                detail="Trop de requêtes de scraping — réessayez dans quelques instants",
            )
        self._calls.append(now)


class PerKeyRateLimiter:
    """Même principe que RateLimiter, mais un compteur par clé (ex. IP) plutôt qu'un seul
    compteur global — pour /api/auth/login, un seul compteur global ferait qu'un attaquant
    seul peut bloquer les tentatives de connexion légitimes de tout le monde. Nettoyage
    paresseux des clés inactives (au moment de l'appel) : pas de tâche de fond, adapté au
    faible nombre de clients concurrents attendu ici (usage NAS personnel)."""

    def __init__(self, max_calls: int, period_seconds: float, max_keys: int = 10_000):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.max_keys = max_keys
        self._buckets: dict[str, deque[float]] = {}
        # Dernière activité par clé — purger seulement les compartiments VIDÉS (comme avant)
        # ne bornait rien pour de vrai : le passage ci-dessous ne rafraîchit que la clé en
        # cours d'appel, une clé qui ne revient jamais garde indéfiniment au moins une entrée
        # et n'apparaît donc jamais "vide". L'éviction se fait maintenant par ancienneté
        # réelle de dernière activité, quelle que soit l'état du compartiment.
        self._last_seen: dict[str, float] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        while bucket and now - bucket[0] > self.period_seconds:
            bucket.popleft()
        self._last_seen[key] = now
        if len(bucket) >= self.max_calls:
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives — réessayez dans quelques instants",
            )
        bucket.append(now)

        # Filet de sécurité contre une fuite mémoire si énormément de clés distinctes se
        # présentent (scan/attaque distribuée) : évince les clés les plus anciennes par
        # dernière activité plutôt que de laisser le dict croître indéfiniment.
        if len(self._buckets) > self.max_keys:
            n_to_remove = len(self._buckets) - self.max_keys
            oldest = sorted(self._last_seen.items(), key=lambda kv: kv[1])[:n_to_remove]
            for k, _ in oldest:
                self._buckets.pop(k, None)
                self._last_seen.pop(k, None)
