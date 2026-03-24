"""
ComicVine API client.
Endpoint: https://comicvine.gamespot.com/api/
"""
import httpx
from typing import Optional


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
    headers = {
        "User-Agent": "CBZManager/1.0",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{COMICVINE_URL}/search/", params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return []

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
