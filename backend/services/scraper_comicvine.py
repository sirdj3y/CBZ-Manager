"""
ComicVine API client.
Endpoint: https://comicvine.gamespot.com/api/
"""
from typing import Optional

from .http_client import COMICVINE


COMICVINE_URL = "https://comicvine.gamespot.com/api"


async def search_comicvine(
    query: str,
    api_key: str,
    max_results: int = 15,
) -> list[dict]:
    if not api_key:
        return []

    params = {
        "api_key": api_key,
        "format": "json",
        "query": query,
        "resources": "volume",
        "field_list": "id,name,publisher,start_year,image,count_of_issues,description",
        "limit": max_results,
    }
    # Erreurs (clé refusée, quota, service indisponible) : ServiceError, remontée telle quelle
    # jusqu'au routeur (message clair) — plus avalée en « aucun résultat ».
    resp = await COMICVINE.get(f"{COMICVINE_URL}/search/", params=params)
    data = resp.json()

    results = []
    for item in data.get("results", [])[:max_results]:
        publisher = None
        pub_data = item.get("publisher")
        if pub_data:
            publisher = pub_data.get("name")

        cover_url = None
        img_data = item.get("image", {})
        cover_url = img_data.get("medium_url") or img_data.get("small_url")

        results.append({
            "title": item.get("name", ""),
            "authors": [],
            "publisher": publisher,
            "year": str(item.get("start_year")) if item.get("start_year") else None,
            "cover_url": cover_url,
            "isbn": None,
            "pages": item.get("count_of_issues"),
            "source": "comicvine",
        })

    return results
