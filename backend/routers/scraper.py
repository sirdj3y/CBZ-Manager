from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import auth_required
from ..models.schemas import ScraperQueryIn, ScraperResultOut
from ..services.scraper_google import search_google_books
from ..services.scraper_comicvine import search_comicvine
from ..config import settings

router = APIRouter(prefix="/api/scrape", tags=["scraper"], dependencies=[Depends(auth_required)])


@router.post("/googlebooks", response_model=list[ScraperResultOut])
async def scrape_google(body: ScraperQueryIn):
    query = body.query
    if not query:
        # Build query from fields
        parts = []
        if body.series:
            parts.append(body.series)
        if body.number:
            import re
            num = re.sub(r"\D", "", body.number)
            if num:
                parts.append(num)
        if body.author:
            parts.append(body.author)
        query = " ".join(parts)

    if not query:
        raise HTTPException(status_code=400, detail="Requête vide")

    results = await search_google_books(query, api_key=settings.GOOGLE_BOOKS_API_KEY)
    return [ScraperResultOut(**r) for r in results]


@router.post("/comicvine", response_model=list[ScraperResultOut])
async def scrape_comicvine(body: ScraperQueryIn):
    if not settings.COMICVINE_API_KEY:
        raise HTTPException(status_code=400, detail="Clé API ComicVine non configurée")

    query = body.query or body.series or ""
    if not query:
        raise HTTPException(status_code=400, detail="Requête vide")

    results = await search_comicvine(query, api_key=settings.COMICVINE_API_KEY)
    return [ScraperResultOut(**r) for r in results]
