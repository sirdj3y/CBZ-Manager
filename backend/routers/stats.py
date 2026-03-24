from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..dependencies import auth_required
from ..models.db_models import Series, Tome, Metadata

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(auth_required)])


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    # ── Compteurs de base ──────────────────────────────────────────────────
    series_count = (await db.execute(select(func.count()).select_from(Series))).scalar() or 0
    tome_count   = (await db.execute(select(func.count()).select_from(Tome))).scalar() or 0
    total_size   = (await db.execute(select(func.sum(Tome.file_size)))).scalar() or 0
    total_pages  = (await db.execute(select(func.sum(Tome.page_count)))).scalar() or 0

    # ── Plus grande série ─────────────────────────────────────────────────
    top_series_row = (await db.execute(
        select(Series.name, Series.tome_count)
        .order_by(Series.tome_count.desc())
        .limit(1)
    )).first()
    top_series = {"name": top_series_row.name, "count": top_series_row.tome_count} if top_series_row else None

    # ── Top 10 séries par nombre de tomes ─────────────────────────────────
    top10_rows = (await db.execute(
        select(Series.name, Series.tome_count)
        .order_by(Series.tome_count.desc())
        .limit(10)
    )).all()
    top10_series = [{"name": r.name, "count": r.tome_count} for r in top10_rows]

    # ── Albums par année (metadata.Year) ──────────────────────────────────
    year_rows = (await db.execute(
        select(Metadata.Year, func.count().label("n"))
        .where(Metadata.Year.isnot(None))
        .where(Metadata.Year != "")
        .group_by(Metadata.Year)
        .order_by(Metadata.Year)
    )).all()
    # Filtrer les années plausibles (1900-2030)
    by_year = [
        {"year": r.Year, "count": r.n}
        for r in year_rows
        if r.Year and r.Year.isdigit() and 1900 <= int(r.Year) <= 2030
    ]

    # ── Éditeurs (top 10) ─────────────────────────────────────────────────
    pub_rows = (await db.execute(
        select(Metadata.Publisher, func.count().label("n"))
        .where(Metadata.Publisher.isnot(None))
        .where(Metadata.Publisher != "")
        .group_by(Metadata.Publisher)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    publishers = [{"name": r.Publisher, "count": r.n} for r in pub_rows]

    # ── Scénaristes (top 10) ──────────────────────────────────────────────
    writer_rows = (await db.execute(
        select(Metadata.Writer, func.count().label("n"))
        .where(Metadata.Writer.isnot(None))
        .where(Metadata.Writer != "")
        .group_by(Metadata.Writer)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    writers = [{"name": r.Writer, "count": r.n} for r in writer_rows]

    # ── Dessinateurs (top 10) ─────────────────────────────────────────────
    penciller_rows = (await db.execute(
        select(Metadata.Penciller, func.count().label("n"))
        .where(Metadata.Penciller.isnot(None))
        .where(Metadata.Penciller != "")
        .group_by(Metadata.Penciller)
        .order_by(func.count().desc())
        .limit(10)
    )).all()
    pencillers = [{"name": r.Penciller, "count": r.n} for r in penciller_rows]

    # ── Album le plus lourd ───────────────────────────────────────────────
    heaviest_row = (await db.execute(
        select(Tome.title, Tome.filename, Tome.file_size)
        .where(Tome.file_size.isnot(None))
        .order_by(Tome.file_size.desc())
        .limit(1)
    )).first()
    heaviest = {
        "name": heaviest_row.title or heaviest_row.filename,
        "size": heaviest_row.file_size,
    } if heaviest_row else None

    # ── Langues ───────────────────────────────────────────────────────────
    lang_rows = (await db.execute(
        select(Metadata.LanguageISO, func.count().label("n"))
        .where(Metadata.LanguageISO.isnot(None))
        .where(Metadata.LanguageISO != "")
        .group_by(Metadata.LanguageISO)
        .order_by(func.count().desc())
    )).all()
    languages = [{"lang": r.LanguageISO, "count": r.n} for r in lang_rows]

    # ── Formats ───────────────────────────────────────────────────────────
    format_rows = (await db.execute(
        select(Tome.file_format, func.count().label("n"))
        .where(Tome.file_format.isnot(None))
        .group_by(Tome.file_format)
        .order_by(func.count().desc())
    )).all()
    formats = [{"name": r.file_format.upper(), "count": r.n} for r in format_rows]

    # ── Couverture métadonnées ─────────────────────────────────────────────
    with_meta = (await db.execute(
        select(func.count()).select_from(Tome).where(Tome.has_metadata == True)
    )).scalar() or 0

    avg_size  = round(total_size / tome_count) if tome_count else 0
    avg_pages = round((total_pages or 0) / tome_count) if tome_count else 0

    return {
        "series_count": series_count,
        "tome_count": tome_count,
        "total_size": total_size,
        "avg_size": avg_size,
        "total_pages": total_pages,
        "avg_pages": avg_pages,
        "top_series": top_series,
        "top10_series": top10_series,
        "heaviest": heaviest,
        "by_year": by_year,
        "publishers": publishers,
        "writers": writers,
        "pencillers": pencillers,
        "formats": formats,
        "languages": languages,
        "tomes_without_meta": tome_count - with_meta,
    }
