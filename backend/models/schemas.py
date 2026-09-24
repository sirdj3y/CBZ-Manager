from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class AuthStatus(BaseModel):
    authenticated: bool
    username: Optional[str] = None
    is_admin: bool = False
    must_change_password: bool = False
    permissions: list[str] = []
    avatar_version: int = 0


class LoginIn(BaseModel):
    username: str
    password: str


class CredentialsIn(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = None


# ── Series ────────────────────────────────────────────────────────────────────

class SeriesOut(BaseModel):
    id: int
    name: str
    tome_count: int
    cover_url: Optional[str] = None
    hidden: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    classification: Optional[str] = None
    # Métadonnées agrégées pour filtrage
    writers: list[str] = []
    pencillers: list[str] = []
    publishers: list[str] = []
    tags: list[str] = []
    genres: list[str] = []
    has_tomes_without_meta: bool = False
    # Utilisé à l'import (destination série existante) pour savoir si le préremplissage
    # global depuis Bedetheque est possible sans re-deviner l'URL.
    bedetheque_url: Optional[str] = None
    bedetheque_match_status: Optional[str] = None
    # Utilisé par le bandeau de logos et la bannière de l'Accueil (HomeView.vue) — évite un
    # appel dédié par série, la liste des séries est déjà chargée au démarrage de l'app.
    hero_logo_version: int = 0
    hero_background_version: int = 0

    model_config = {"from_attributes": True}


class SeriesDetailOut(BaseModel):
    id: int
    name: str
    tome_count: int
    cover_url: Optional[str] = None
    cover_tome_id: Optional[int] = None
    hidden: bool = False
    bedetheque_url: Optional[str] = None
    bedetheque_match_status: Optional[str] = None
    bedetheque_status: Optional[str] = None
    bedetheque_resume: Optional[str] = None
    classification: Optional[str] = None
    age_rating: Optional[str] = None
    # Compteurs de version des images "hero" (fond/logo/personnage) — 0 = aucune image,
    # le frontend retombe alors sur le dégradé/titre texte. Pas de chemin ici, voir
    # services/series_hero.py.
    hero_background_version: int = 0
    hero_logo_version: int = 0
    hero_character_version: int = 0
    # Moyenne des notes Bedetheque.com des tomes de la série qui en ont une (pas de note
    # "série" telle quelle sur Bedetheque.com, contrairement à l'album) — None si aucun tome
    # n'a de note connue.
    community_rating: Optional[float] = None
    # Pas de champ "années de publication" dédié à la série — min/max des Metadata.Year des
    # tomes qui en ont une (voir get_series). None si aucun tome n'a d'année connue.
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    # Auteurs/éditeurs distincts sur l'ensemble des tomes de la série (pas seulement le
    # premier) — un album peut avoir plusieurs scénaristes/dessinateurs.
    writers: list[str] = []
    pencillers: list[str] = []
    publishers: list[str] = []
    genres: list[str] = []
    tomes: list["TomeOut"] = []

    model_config = {"from_attributes": True}


# ── Tomes ─────────────────────────────────────────────────────────────────────

class TomeOut(BaseModel):
    id: int
    series_id: int
    series_name: Optional[str] = None
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
    # Dimensions de la couverture mise en cache — peuplées paresseusement (voir
    # routers/covers.py::get_cover), None tant que la couverture n'a jamais été consultée.
    cover_width: Optional[int] = None
    cover_height: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    hidden: bool = False
    series_hidden: bool = False
    is_oneshot: bool = False
    # Annotations utilisateur
    user_rating: Optional[int] = None
    user_notes: Optional[str] = None
    user_tags: list[str] = []
    user_is_read: bool = False
    # Métadonnées enrichies (pour filtrage)
    writer: Optional[str] = None
    penciller: Optional[str] = None
    publisher: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    community_rating: Optional[float] = None
    # Hérité de la série (jamais stocké sur le tome, voir Series.classification) — exposé ici
    # uniquement pour permettre le filtrage sur la page Albums.
    classification: Optional[str] = None

    model_config = {"from_attributes": True}


class UserDataIn(BaseModel):
    user_rating: Optional[int] = None
    user_notes: Optional[str] = None
    user_tags: Optional[list[str]] = None
    is_read: Optional[bool] = None


class ReadingProgressOut(BaseModel):
    tome_id: int
    last_page: int
    updated_at: Optional[datetime] = None
    # Le lecteur (ReaderView.vue) s'en sert pour ne jamais proposer de reprendre à la page
    # sauvegardée sur un album déjà marqué lu — une relecture repart de zéro (voir
    # save_progress, qui ne redescend jamais is_read à False de lui-même).
    is_read: bool = False

    model_config = {"from_attributes": True}


class ReadingProgressIn(BaseModel):
    last_page: int


class HeartbeatIn(BaseModel):
    # Secondes actives écoulées depuis le dernier battement (voir ReaderView.vue) — jamais la
    # durée totale de la session, seulement l'incrément à ajouter. Bornée côté serveur (voir
    # reader_heartbeat) plutôt que de faire confiance à la valeur envoyée.
    seconds: int


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
    CommunityRating: Optional[str] = None
    bedetheque_votes: Optional[int] = None

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
    # Série locale déjà identifiée (ex. import d'un nouvel album dans une série existante) —
    # si elle a une URL Bedetheque confirmée, la recherche l'utilise directement au lieu de
    # deviner par nom, seule façon d'être sûr de chercher dans la bonne série.
    series_id: Optional[int] = None

class BedethequeBulkIn(BaseModel):
    # Soit une URL directe (nouvelle série), soit l'id d'une série locale déjà identifiée sur
    # Bedetheque (import dans une série existante) — series_id prioritaire si les deux sont
    # fournis, voir scrape_bedetheque_bulk.
    url: Optional[str] = None
    series_id: Optional[int] = None


class BedethequeBulkAlbumOut(BaseModel):
    number: Optional[str] = None
    title: Optional[str] = None
    writer: Optional[str] = None
    penciller: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[str] = None


class BedethequeSuggestIn(BaseModel):
    name: str


class BedethequeSuggestOut(BaseModel):
    name: str
    url: str
    album_count: int
    status: Optional[str] = None
    year_min: Optional[str] = None
    year_max: Optional[str] = None


class BedethequeAlbumSummaryIn(BaseModel):
    url: str


class BedethequeAlbumSummaryOut(BaseModel):
    summary: Optional[str] = None


class ScraperResultOut(BaseModel):
    title: str
    series: Optional[str] = None
    number: Optional[str] = None
    authors: list[str] = []
    publisher: Optional[str] = None
    year: Optional[str] = None
    cover_url: Optional[str] = None
    isbn: Optional[str] = None
    pages: Optional[int] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    url: Optional[str] = None
    source: str = "google_books"


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    library_subdir: str
    media_root_name: str = ""
    google_books_configured: bool
    comicvine_configured: bool
    rename_pattern: str = ""

class SettingsIn(BaseModel):
    library_subdir: Optional[str] = None
    google_books_api_key: Optional[str] = None
    comicvine_api_key: Optional[str] = None
    rename_pattern: Optional[str] = None


# ── Rename ────────────────────────────────────────────────────────────────────

class RenameIn(BaseModel):
    pattern: str

class RenameBulkIn(BaseModel):
    ids: list[int]
    pattern: str


class MoveTomesIn(BaseModel):
    tome_ids: list[int]
    target_series_id: int


class DeleteBulkIn(BaseModel):
    tome_ids: list[int]


class DeleteSeriesBulkIn(BaseModel):
    series_ids: list[int]


class MetadataBulkIn(BaseModel):
    tome_ids: list[int]
    fields: dict[str, str]


class RenameToIn(BaseModel):
    new_filename: str


class RenameItemIn(BaseModel):
    id: int
    new_filename: str


class RenameBulkToIn(BaseModel):
    renames: list[RenameItemIn]


# ── Albums manquants ──────────────────────────────────────────────────────────

class MissingAlbumOut(BaseModel):
    id: int
    series_id: int
    series_name: str
    number: str
    title: Optional[str] = None
    cover_url: Optional[str] = None
    year: Optional[str] = None
    bedetheque_url: Optional[str] = None
    detected_at: Optional[datetime] = None
    writer: Optional[str] = None
    penciller: Optional[str] = None
    publisher: Optional[str] = None

    model_config = {"from_attributes": True}


class NotFoundSeriesOut(BaseModel):
    id: int
    name: str


class MissingAlbumsScanStartOut(BaseModel):
    job_id: int


class MissingAlbumsScanStatusOut(BaseModel):
    job_id: int
    status: str
    processed: int
    total: int
    error_msg: Optional[str] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TrackedSeriesOut(BaseModel):
    id: int
    name: str
    track_new_albums: bool
    bedetheque_match_status: Optional[str] = None
    missing_count: int = 0


class TrackToggleIn(BaseModel):
    track_new_albums: bool


class BedethequeUrlIn(BaseModel):
    url: Optional[str] = None


class BedethequeStatusIn(BaseModel):
    status: Optional[str] = None  # "Série en cours" / "Série finie" / None (non précisé)


class MissingAlbumsCountOut(BaseModel):
    count: int


class IgnoredAlbumOut(BaseModel):
    id: int
    series_id: int
    series_name: str
    number: str
    title: Optional[str] = None


# ── Doublons ──────────────────────────────────────────────────────────────────

class DuplicateScanStartOut(BaseModel):
    job_id: int


class DuplicateScanStatusOut(BaseModel):
    job_id: int
    status: str
    processed: int
    total: int
    error_msg: Optional[str] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Notifications de nouveautés ──────────────────────────────────────────────────

class NewContentItemOut(BaseModel):
    type: str  # 'tome' | 'series'
    id: int
    title: str
    series_id: int
    series_name: str
    cover_url: Optional[str] = None
    created_at: datetime


class NotificationsOut(BaseModel):
    count: int
    items: list[NewContentItemOut]


# ── Alertes de sécurité ─────────────────────────────────────────────────────────

class SecurityAlertOut(BaseModel):
    severity: str  # info/warning/error
    label: str
    detail: str
    created_at: datetime


# ── Smart lists ───────────────────────────────────────────────────────────────

class SmartListConditionIn(BaseModel):
    source: str
    field: str
    operator: str
    value: Optional[str] = None
    value2: Optional[str] = None


class SmartListGroupIn(BaseModel):
    conditions: list[SmartListConditionIn] = []


class SmartListRulesIn(BaseModel):
    groups: list[SmartListGroupIn] = []


class SmartListIn(BaseModel):
    name: str
    shared: bool = False
    rules: SmartListRulesIn


class SmartListPatchIn(BaseModel):
    name: Optional[str] = None
    shared: Optional[bool] = None
    rules: Optional[SmartListRulesIn] = None


class SmartListReorderIn(BaseModel):
    ids: list[int]


class SmartListOut(BaseModel):
    id: int
    name: str
    owner_id: int
    owner_username: Optional[str] = None
    shared: bool
    is_default: bool
    rules: SmartListRulesIn
    # Nombre d'albums correspondant aux règles — l'affichage Albums/Séries est un choix de
    # présentation côté page de résultat (voir routers/smart_lists.py GET .../tomes vs
    # .../series), pas une propriété figée de la liste : ce compteur reste toujours au niveau
    # album, cohérent quel que soit le mode d'affichage choisi ensuite.
    result_count: int = 0
    can_edit: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SmartListFieldOut(BaseModel):
    source: str
    field: str
    label: str
    type: str
    operators: list[str]
    choices: Optional[list[str]] = None


# ── Filename parse ────────────────────────────────────────────────────────────

class ParseFilenameOut(BaseModel):
    series: Optional[str] = None
    number: Optional[str] = None
    title: Optional[str] = None
