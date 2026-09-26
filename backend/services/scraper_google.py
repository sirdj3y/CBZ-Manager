"""
Google Books API client.
"""
from .http_client import GOOGLE_BOOKS


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

    # 429 → ServiceError("quota") après reprises ; message côté routeur (sans clé API, le quota
    # anonyme de Google est vite atteint — le message invite à en configurer une).
    resp = await GOOGLE_BOOKS.get(GOOGLE_BOOKS_URL, params=params)
    data = resp.json()

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
