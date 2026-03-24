"""
Google Books API client.
"""
import httpx
from fastapi import HTTPException


GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


async def search_google_books(
    query: str,
    api_key: str = "",
    max_results: int = 15,
) -> list[dict]:
    params: dict = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
    }
    if api_key:
        params["key"] = api_key

    headers = {"User-Agent": "CBZManager/1.0"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_URL, params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(
                    status_code=503,
                    detail="Google Books: quota dépassé. Configurez une clé API dans les paramètres.",
                )
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Impossible de contacter Google Books.")

    results = []
    for item in data.get("items", [])[:max_results]:
        info = item.get("volumeInfo", {})
        isbn = None
        for ident in info.get("industryIdentifiers", []):
            if ident.get("type") == "ISBN_13":
                isbn = ident.get("identifier")
                break
        cover_url = None
        img_links = info.get("imageLinks", {})
        for size in ("thumbnail", "smallThumbnail"):
            url = img_links.get(size)
            if url:
                cover_url = url.replace("zoom=1", "zoom=2").replace("http://", "https://")
                break

        pub_date = info.get("publishedDate", "")
        year = pub_date[:4] if pub_date else None

        results.append({
            "title": info.get("title", ""),
            "authors": info.get("authors", []),
            "publisher": info.get("publisher"),
            "year": year,
            "cover_url": cover_url,
            "isbn": isbn,
            "pages": info.get("pageCount"),
            "source": "google_books",
        })

    return results
