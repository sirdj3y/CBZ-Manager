from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    password: str

class AuthStatus(BaseModel):
    authenticated: bool


# ── Series ────────────────────────────────────────────────────────────────────

class SeriesOut(BaseModel):
    id: int
    name: str
    tome_count: int
    cover_url: Optional[str] = None
    hidden: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Métadonnées agrégées pour filtrage
    writers: list[str] = []
    pencillers: list[str] = []
    publishers: list[str] = []
    tags: list[str] = []
    has_tomes_without_meta: bool = False

    model_config = {"from_attributes": True}


class SeriesDetailOut(BaseModel):
    id: int
    name: str
    tome_count: int
    cover_url: Optional[str] = None
    cover_tome_id: Optional[int] = None
    hidden: bool = False
    tomes: list["TomeOut"] = []

    model_config = {"from_attributes": True}


# ── Tomes ─────────────────────────────────────────────────────────────────────

class TomeOut(BaseModel):
    id: int
    series_id: int
    filename: str
    filepath: Optional[str] = None
    number: Optional[str] = None
    title: Optional[str] = None
    file_format: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    has_metadata: bool
    cover_cached: bool
    cover_url: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    hidden: bool = False
    series_hidden: bool = False
    # Annotations utilisateur
    user_rating: Optional[int] = None
    user_notes: Optional[str] = None
    user_tags: list[str] = []
    # Métadonnées enrichies (pour filtrage)
    writer: Optional[str] = None
    penciller: Optional[str] = None
    publisher: Optional[str] = None

    model_config = {"from_attributes": True}


class UserDataIn(BaseModel):
    user_rating: Optional[int] = None
    user_notes: Optional[str] = None
    user_tags: Optional[list[str]] = None


class ReadingProgressOut(BaseModel):
    tome_id: int
    last_page: int
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReadingProgressIn(BaseModel):
    last_page: int


# ── Metadata ──────────────────────────────────────────────────────────────────

class MetadataOut(BaseModel):
    Title: Optional[str] = None
    Series: Optional[str] = None
    Number: Optional[str] = None
    Volume: Optional[str] = None
    AlternateSeries: Optional[str] = None
    AlternateNumber: Optional[str] = None
    StoryArc: Optional[str] = None
    SeriesGroup: Optional[str] = None
    Publisher: Optional[str] = None
    Year: Optional[str] = None
    Month: Optional[str] = None
    Day: Optional[str] = None
    LanguageISO: Optional[str] = None
    Format: Optional[str] = None
    Web: Optional[str] = None
    Writer: Optional[str] = None
    Penciller: Optional[str] = None
    Inker: Optional[str] = None
    Colorist: Optional[str] = None
    Letterer: Optional[str] = None
    CoverArtist: Optional[str] = None
    Editor: Optional[str] = None
    Translator: Optional[str] = None
    Genre: Optional[str] = None
    Tags: Optional[str] = None
    AgeRating: Optional[str] = None
    Characters: Optional[str] = None
    Teams: Optional[str] = None
    Locations: Optional[str] = None
    Summary: Optional[str] = None
    Notes: Optional[str] = None
    PageCount: Optional[str] = None
    BlackAndWhite: Optional[str] = None
    Manga: Optional[str] = None
    ScanInformation: Optional[str] = None
    GTIN: Optional[str] = None
    ISBN: Optional[str] = None

    model_config = {"from_attributes": True}


class MetadataIn(MetadataOut):
    pass


# ── Scan ──────────────────────────────────────────────────────────────────────

class ScanStartOut(BaseModel):
    job_id: int

class ScanStatusOut(BaseModel):
    job_id: int
    status: str
    processed: int
    total: int
    error_msg: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Conversion ────────────────────────────────────────────────────────────────

class ConvertIn(BaseModel):
    tome_ids: list[int]
    preset: str
    dest_path: Optional[str] = None
    delete_source: bool = False

class ConvertStartOut(BaseModel):
    job_id: int

class ConvertStatusOut(BaseModel):
    job_id: int
    status: str
    progress: int
    total: int
    error_msg: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Scraper ───────────────────────────────────────────────────────────────────

class ScraperQueryIn(BaseModel):
    query: str
    series: Optional[str] = None
    number: Optional[str] = None
    author: Optional[str] = None

class ScraperResultOut(BaseModel):
    title: str
    authors: list[str] = []
    publisher: Optional[str] = None
    year: Optional[str] = None
    cover_url: Optional[str] = None
    isbn: Optional[str] = None
    pages: Optional[int] = None
    source: str = "google_books"


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    library_subdir: str
    media_root_name: str = ""
    google_books_configured: bool
    comicvine_configured: bool

class SettingsIn(BaseModel):
    library_subdir: Optional[str] = None
    google_books_api_key: Optional[str] = None
    comicvine_api_key: Optional[str] = None


# ── Rename ────────────────────────────────────────────────────────────────────

class RenameIn(BaseModel):
    pattern: str

class RenameBulkIn(BaseModel):
    ids: list[int]
    pattern: str


class RenameToIn(BaseModel):
    new_filename: str


class RenameItemIn(BaseModel):
    id: int
    new_filename: str


class RenameBulkToIn(BaseModel):
    renames: list[RenameItemIn]


# ── Filename parse ────────────────────────────────────────────────────────────

class ParseFilenameOut(BaseModel):
    series: Optional[str] = None
    number: Optional[str] = None
    title: Optional[str] = None
