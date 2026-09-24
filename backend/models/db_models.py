from datetime import datetime, timezone
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Float, ForeignKey, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
from ..database import Base


class UTCDateTime(TypeDecorator):
    """Toute l'app écrit des datetimes naïfs mais toujours en UTC (datetime.utcnow()). Sans
    ce type, ils ressortent de l'API sans indicateur de fuseau (ex: "2026-08-24T17:11:23"),
    que le JS du frontend interprète comme une heure LOCALE plutôt qu'UTC — d'où un décalage
    affiché égal au fuseau du navigateur (2h en France l'été). Ce type rend le datetime lu
    depuis la base explicitement UTC-aware, pour que la sérialisation JSON (Pydantic/
    isoformat()) inclue "+00:00" et que le JS convertisse correctement vers l'heure locale."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    folder_path: Mapped[str] = mapped_column(String, nullable=False)
    cover_tome_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tomes.id"), nullable=True)
    tome_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    # Détection d'albums manquants (Bedetheque)
    track_new_albums: Mapped[bool] = mapped_column(Boolean, default=True)
    bedetheque_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bedetheque_match_status: Mapped[str | None] = mapped_column(String, nullable=True)  # found/not_found, None = jamais scanné
    bedetheque_status: Mapped[str | None] = mapped_column(String, nullable=True)  # "Série finie" / "Série en cours", tel qu'affiché par Bedetheque
    bedetheque_resume: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Liste fermée (voir services/permissions.py-like catalogue dans routers/library.py) —
    # quasiment toujours constante sur toute une série (Dragon Ball reste manga du premier au
    # dernier tome), contrairement à Genre qui peut varier album par album. Volontairement au
    # niveau série, jamais dupliqué sur Tome/Metadata.
    classification: Mapped[str | None] = mapped_column(String, nullable=True)

    # Public conseillé — même principe que classification (catalogue fermé propre à l'app,
    # voir services/age_rating.py) : pas un passage du champ ComicInfo.xml AgeRating, trop
    # rarement renseigné et en anglais pour être présentable tel quel.
    age_rating: Mapped[str | None] = mapped_column(String, nullable=True)

    # Images de la fiche "hero" (fond/logo/personnage détouré) — pas de chemin en base,
    # juste un compteur incrémenté à chaque upload/suppression (même mécanique que
    # User.avatar_version) : le fichier vit sous COVER_CACHE_DIR/../series_hero/, jamais
    # référencé par nom côté frontend, seul le compteur sert au cache-busting et à savoir
    # si l'image existe (0 = aucune, repli sur le dégradé/titre texte).
    hero_background_version: Mapped[int] = mapped_column(Integer, default=0)
    hero_logo_version: Mapped[int] = mapped_column(Integer, default=0)
    hero_character_version: Mapped[int] = mapped_column(Integer, default=0)

    tomes: Mapped[list["Tome"]] = relationship(
        "Tome", back_populates="series",
        foreign_keys="Tome.series_id",
        cascade="all, delete-orphan",
        order_by="Tome.number"
    )
    missing_albums: Mapped[list["MissingAlbum"]] = relationship(
        "MissingAlbum", back_populates="series", cascade="all, delete-orphan"
    )
    # Sans ces deux relations, supprimer une série ne nettoyait ni les albums ignorés ni
    # les masquages par utilisateur qui la référençaient (aucune des 4 routes de suppression
    # ne le faisait explicitement) — des lignes orphelines restaient en base, prêtes à se
    # rattacher silencieusement à une série recréée plus tard si SQLite réutilise le même id
    # (cas réel : supprimer une série puis la réimporter aussitôt).
    ignored_missing_albums: Mapped[list["IgnoredMissingAlbum"]] = relationship(
        "IgnoredMissingAlbum", cascade="all, delete-orphan"
    )
    hidden_by_users: Mapped[list["UserHiddenSeries"]] = relationship(
        "UserHiddenSeries", cascade="all, delete-orphan"
    )


class Tome(Base):
    __tablename__ = "tomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    filepath: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    file_format: Mapped[str] = mapped_column(String, nullable=False)  # cbz/cbr/pdf
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_mtime: Mapped[float | None] = mapped_column(Float, nullable=True)
    number: Mapped[str | None] = mapped_column(String, nullable=True)  # "01", "02"…
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_metadata: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="no_metadata")  # ok/no_metadata/error/cbr_unsupported
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    # Album indépendant, sans rapport avec les autres tomes de son dossier/série (ex. dossier
    # "One Shot" regroupant des albums sans lien narratif) — posé manuellement, jamais déduit
    # automatiquement (trop de faux positifs avec le premier tome d'une série qu'on vient de
    # commencer). Conséquences câblées ailleurs : badge au lieu de "T{numéro}", requête de
    # recherche de métadonnées basée sur le titre plutôt que série+numéro, exclu du calcul
    # "plus grosses séries" (stats.py), modèle de renommage réduit à {Titre} (apply_pattern).
    is_oneshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # SHA-256 du contenu du fichier, calculé à la demande par le scan de doublons
    # (services/duplicates.py) — jamais au scan normal, trop coûteux en I/O pour tourner à
    # chaque scan de routine. None tant que jamais haché, ou remis à None par le scanner
    # (scanner.py::_process_file) quand le fichier a changé — le prochain scan de doublons
    # le recalculera.
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    # Dimensions de la couverture mise en cache — peuplées paresseusement au premier
    # affichage (routers/covers.py::get_cover), pas au scan : évite de rouvrir chaque image
    # d'une grosse bibliothèque juste pour cette info secondaire (fiche album uniquement).
    cover_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    series: Mapped["Series"] = relationship("Series", back_populates="tomes", foreign_keys=[series_id])
    metadata_: Mapped["Metadata | None"] = relationship("Metadata", back_populates="tome", uselist=False, cascade="all, delete-orphan")
    # Sans cette relation, supprimer un tome ne supprimait jamais sa progression de lecture/
    # note/notes (User.tome_data ne cascade que quand c'est l'UTILISATEUR qui est supprimé,
    # pas le tome) — la ligne restait orpheline en base et se rattachait silencieusement à
    # un nouveau tome si SQLite réutilisait le même id (cas réel signalé : supprimer un album
    # puis le réimporter aussitôt fait réapparaître son ancienne progression de lecture).
    user_data: Mapped[list["UserTomeData"]] = relationship("UserTomeData", cascade="all, delete-orphan")
    # Même raisonnement : sans cascade, les cases mises en cache pour un tome supprimé
    # resteraient orphelines et pourraient se rattacher à tort à un nouveau tome recréé
    # avec le même id.
    page_panels: Mapped[list["TomePagePanels"]] = relationship("TomePagePanels", cascade="all, delete-orphan")
    # Idem pour le temps de lecture (statistiques) — test : tests/test_deletion_cleanup.py.
    reading_activity: Mapped[list["ReadingActivity"]] = relationship("ReadingActivity", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tomes_series_id", "series_id"),
        Index("idx_tomes_number", "series_id", "number"),
        Index("idx_tomes_content_hash", "content_hash"),
    )


class Metadata(Base):
    __tablename__ = "metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id", ondelete="CASCADE"), nullable=False, unique=True)

    Title: Mapped[str | None] = mapped_column(Text, nullable=True)
    Series: Mapped[str | None] = mapped_column(Text, nullable=True)
    Number: Mapped[str | None] = mapped_column(Text, nullable=True)
    Volume: Mapped[str | None] = mapped_column(Text, nullable=True)
    AlternateSeries: Mapped[str | None] = mapped_column(Text, nullable=True)
    AlternateNumber: Mapped[str | None] = mapped_column(Text, nullable=True)
    StoryArc: Mapped[str | None] = mapped_column(Text, nullable=True)
    SeriesGroup: Mapped[str | None] = mapped_column(Text, nullable=True)
    Publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    Year: Mapped[str | None] = mapped_column(Text, nullable=True)
    Month: Mapped[str | None] = mapped_column(Text, nullable=True)
    Day: Mapped[str | None] = mapped_column(Text, nullable=True)
    LanguageISO: Mapped[str | None] = mapped_column(Text, nullable=True)
    Format: Mapped[str | None] = mapped_column(Text, nullable=True)
    Web: Mapped[str | None] = mapped_column(Text, nullable=True)
    Writer: Mapped[str | None] = mapped_column(Text, nullable=True)
    Penciller: Mapped[str | None] = mapped_column(Text, nullable=True)
    Inker: Mapped[str | None] = mapped_column(Text, nullable=True)
    Colorist: Mapped[str | None] = mapped_column(Text, nullable=True)
    Letterer: Mapped[str | None] = mapped_column(Text, nullable=True)
    CoverArtist: Mapped[str | None] = mapped_column(Text, nullable=True)
    Editor: Mapped[str | None] = mapped_column(Text, nullable=True)
    Translator: Mapped[str | None] = mapped_column(Text, nullable=True)
    Genre: Mapped[str | None] = mapped_column(Text, nullable=True)
    Tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    AgeRating: Mapped[str | None] = mapped_column(Text, nullable=True)
    Characters: Mapped[str | None] = mapped_column(Text, nullable=True)
    Teams: Mapped[str | None] = mapped_column(Text, nullable=True)
    Locations: Mapped[str | None] = mapped_column(Text, nullable=True)
    Summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    Notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    PageCount: Mapped[str | None] = mapped_column(Text, nullable=True)
    BlackAndWhite: Mapped[str | None] = mapped_column(Text, nullable=True)
    Manga: Mapped[str | None] = mapped_column(Text, nullable=True)
    ScanInformation: Mapped[str | None] = mapped_column(Text, nullable=True)
    GTIN: Mapped[str | None] = mapped_column(Text, nullable=True)
    ISBN: Mapped[str | None] = mapped_column(Text, nullable=True)
    CommunityRating: Mapped[str | None] = mapped_column(Text, nullable=True)  # note Bedetheque /5, champ standard ComicInfo.xml
    # Nombre de votes Bedetheque — pas un champ ComicInfo.xml standard, jamais écrit dans le
    # fichier (uniquement affiché dans l'app à côté de CommunityRating).
    bedetheque_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tome: Mapped["Tome"] = relationship("Tome", back_populates="metadata_")


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/running/done/error
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class DuplicateScanJob(Base):
    """Même forme que ScanJob/MissingAlbumsScanJob — job de hashing de contenu pour la
    détection de doublons (services/duplicates.py), volontairement séparé du scan normal
    (trop coûteux en I/O pour tourner à chaque scan de routine)."""
    __tablename__ = "duplicate_scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/running/done/error
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ConvertJob(Base):
    __tablename__ = "convert_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preset: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    dest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    delete_source: Mapped[bool] = mapped_column(Boolean, default=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable : jobs créés avant l'ajout de cette colonne. Sert uniquement à restreindre la
    # consultation du statut/annulation au créateur du job (ou à un admin) — un job d'un autre
    # utilisateur ne doit pas être consultable/annulable en devinant son id.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    tomes: Mapped[list["ConvertJobTome"]] = relationship("ConvertJobTome", back_populates="job", cascade="all, delete-orphan")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String, nullable=False)  # scan/convert/delete_series/delete_tome/rename
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok/error
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)

    # Multi-utilisateur (câblage à l'étape 2) — username_snapshot, pas user_id, est le champ
    # affiché : l'historique doit rester lisible même après suppression du compte, et SQLite
    # n'applique pas les FK au niveau base ici (pas de PRAGMA foreign_keys=ON), donc se fier à
    # une jointure vivante sur user_id serait fragile de toute façon.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    username_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)


class MissingAlbum(Base):
    __tablename__ = "missing_albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[str | None] = mapped_column(String, nullable=True)
    bedetheque_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)

    # Déjà parsés depuis la page série Bedetheque (voir scraper_bedetheque._parse_album_block)
    # mais jusqu'ici jetés — utiles pour pré-remplir les métadonnées lors de l'ajout d'un
    # album manquant depuis son fichier (voir MissingAlbumUploadModal côté frontend).
    writer: Mapped[str | None] = mapped_column(String, nullable=True)
    penciller: Mapped[str | None] = mapped_column(String, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String, nullable=True)

    series: Mapped["Series"] = relationship("Series", back_populates="missing_albums")

    __table_args__ = (
        Index("idx_missing_albums_series_id", "series_id"),
    )


class MissingAlbumsScanJob(Base):
    __tablename__ = "missing_albums_scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/running/done/error
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class IgnoredMissingAlbum(Base):
    __tablename__ = "ignored_missing_albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("series_id", "number", name="uq_ignored_missing_albums_series_number"),
    )


class ConvertJobTome(Base):
    __tablename__ = "convert_job_tomes"

    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("convert_jobs.id", ondelete="CASCADE"), primary_key=True)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)

    job: Mapped["ConvertJob"] = relationship("ConvertJob", back_populates="tomes")


class AuthConfig(Base):
    """Une seule ligne toujours. Ne porte plus que la clé de signature globale des cookies de
    session (itsdangerous) depuis le passage au multi-compte (voir User) — les colonnes
    username/password_hash restent physiquement présentes (installations existantes,
    pas de migration destructive) mais ne sont plus lues : les identifiants de connexion
    vivent désormais dans User.password_hash. L'invalidation de session se fait maintenant
    par utilisateur via User.token_version, plus par rotation de cette clé (qui invaliderait
    tout le monde à la fois)."""
    __tablename__ = "auth_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    secret_key: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Profile(Base):
    """Profil de droits réutilisable, assignable à plusieurs utilisateurs non-admin.
    permissions est une liste JSON de clés (catalogue introduit à l'étape 2) — même
    convention que Tome.user_tag_list (JSON stocké en Text, lu/écrit avec un garde-fou
    try/except plutôt qu'un type JSON SQLite dédié)."""
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array de clés
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Indépendant du profil : un admin a tous les droits + les réglages système (jamais
    # paramétrables via un profil), sans dépendre du catalogue de permissions. profile_id ne
    # concerne que les comptes non-admin, il reste NULL pour un admin.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("profiles.id"), nullable=True)
    # Liste JSON de clés de permissions (même convention que Profile.permissions) qui, si
    # renseignée, prime sur celles du profil — permet de personnaliser les droits d'un
    # utilisateur précis sans créer un profil nommé juste pour lui. profile_id reste
    # renseigné même dans ce cas, uniquement pour l'affichage ("Contributeur (modifié)") —
    # voir dependencies._profile_permissions pour la résolution effective.
    custom_permissions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plafond de public (catalogue AGE_RATINGS, services/age_rating.py) que cet utilisateur
    # peut voir. NULL = aucune restriction (voit tout, y compris les séries sans Public
    # défini) — réservé de fait aux administrateurs (qui bypass ce filtre entièrement, voir
    # is_admin dans hidden_series.py) : les routes users.py forcent AGE_RATINGS[0] ("Tout
    # public") par défaut pour tout compte non-admin, jamais de "Illimité" implicite pour eux
    # (sécurité par défaut). Une série sans Public défini est traitée comme la plus
    # restrictive (invisible) dès qu'une limite est fixée : voir services/hidden_series.py.
    age_rating_limit: Mapped[str | None] = mapped_column(String, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Incrémenté pour invalider les sessions de CET utilisateur seulement (changement de mot
    # de passe, "déconnexion de tous les appareils") — pas la clé de signature globale
    # (AuthConfig.secret_key), qui invaliderait tout le monde à la fois.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Incrémenté à chaque upload/suppression de photo de profil — sert de cache-buster pour
    # l'URL de l'avatar côté frontend (même principe que cover_url_version pour les tomes),
    # sans avoir besoin d'un booléen "a un avatar" séparé (0 = pas de photo).
    avatar_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Horodatage de dernière consultation du menu "Nouveautés" — tout Tome/Series créé après
    # compte comme nouveau. Initialisé à la création du compte (voir services/auth.py) plutôt
    # que laissé à NULL, sinon un compte fraîchement créé se retrouverait avec des mois
    # d'historique de bibliothèque marqués "nouveau" à la première connexion.
    notifications_last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile: Mapped["Profile | None"] = relationship("Profile")
    tome_data: Mapped[list["UserTomeData"]] = relationship("UserTomeData", cascade="all, delete-orphan")
    hidden_series: Mapped[list["UserHiddenSeries"]] = relationship("UserHiddenSeries", cascade="all, delete-orphan")
    # Le ON DELETE CASCADE des clés étrangères n'est pas appliqué par SQLite ici (pas de PRAGMA
    # foreign_keys=ON) : sans ces relations, le temps de lecture et les listes intelligentes
    # d'un compte supprimé restaient en base, et passaient au prochain compte créé avec le
    # même id. Test : tests/test_deletion_cleanup.py.
    reading_activity: Mapped[list["ReadingActivity"]] = relationship("ReadingActivity", cascade="all, delete-orphan")
    smart_lists: Mapped[list["SmartList"]] = relationship("SmartList", cascade="all, delete-orphan")


class UserHiddenSeries(Base):
    """Masque une série précise pour un utilisateur précis — indépendant de Series.hidden
    (qui masque globalement, à tout le monde). Inerte jusqu'à l'étape 6."""
    __tablename__ = "user_hidden_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "series_id", name="uq_user_hidden_series"),
    )


class UserTomeData(Base):
    """La relation d'un utilisateur à un album : note, notes texte, étiquettes, progression
    de lecture — remplace les anciennes colonnes partagées Tome.user_rating/user_notes/
    user_tag_list et la table reading_progress (une seule ligne par tome, migrées vers ici
    au démarrage, voir services/auth.migrate_personal_data)."""
    __tablename__ = "user_tome_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    last_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "Lu" — mis à True automatiquement dès que last_page atteint 95% de page_count (voir
    # routers/tomes.py::save_progress), ou basculé manuellement (icône dédiée). Jamais remis
    # à False automatiquement : une relecture qui repasse par-dessus le seuil ne fait que
    # confirmer un état déjà vrai, et un décochage manuel n'est jamais écrasé par la suite.
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "tome_id", name="uq_user_tome_data"),
    )


class SmartList(Base):
    """Liste dynamique définie par un arbre de règles (voir services/smart_lists.py), jamais
    par une liste de tome_id précalculée — le contenu est toujours recalculé à la demande,
    donc reste à jour sans job de maintenance. rules est un JSON de la forme
    {"groups": [{"conditions": [{"source", "field", "operator", "value", "value2"}]}]} —
    OU entre groupes, ET entre conditions d'un même groupe."""
    __tablename__ = "smart_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Visible/éditable par tous les comptes (pas seulement l'admin) une fois partagée — voir
    # décision produit : n'importe quel utilisateur peut créer une liste partagée.
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rules: Mapped[str] = mapped_column(Text, nullable=False)  # JSON, voir docstring de la classe
    # Listes semées au premier démarrage (Manga/Comics/BD/One-shot) — un simple marqueur
    # d'origine, n'empêche ni l'édition ni la suppression par un utilisateur.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Ordre d'affichage dans la barre latérale — partagé entre tous les utilisateurs (pas de
    # préférence par compte, cohérent avec le reste de la fonctionnalité : n'importe qui peut
    # créer/réordonner une liste partagée). Modifié par glisser-déposer côté frontend.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Ancien réglage figé "tome"/"series" — remplacé par un bascule Albums/Séries côté page
    # de résultat (choix de présentation ponctuel, jamais enregistré : les mêmes règles
    # peuvent se regarder des deux façons sans dupliquer la liste). Colonne conservée mais
    # plus lue ni écrite, pour ne pas imposer de migration destructive (même principe que
    # AuthConfig.username/password_hash, voir services/auth.py).
    result_type: Mapped[str] = mapped_column(String, nullable=False, default="tome")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_smart_lists_owner_id", "owner_id"),
    )


class TomePagePanels(Base):
    """Cases détectées sur une page d'un tome (services/panel_detector.py), pour l'option
    "Zoom sur les cases" du lecteur (désactivée par défaut) — calculées à la demande la
    première fois qu'une page est vue avec l'option active, jamais recalculées ensuite.
    Coordonnées normalisées [0,1] (indépendantes de la résolution réelle de l'image),
    déjà triées dans l'ordre de lecture."""
    __tablename__ = "tome_page_panels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id", ondelete="CASCADE"), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    panels_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: [[x1,y1,x2,y2], ...]
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tome_id", "page_index", name="uq_tome_page_panels"),
    )


class ReadingActivity(Base):
    """Temps de lecture actif, agrégé par jour (pas par session précise) — routers/reader.py
    ::reader_heartbeat incrémente la ligne du jour courant à chaque battement envoyé par le
    lecteur (voir ReaderView.vue), plutôt que d'enregistrer un début/fin de session exact.
    Granularité suffisante pour les statistiques personnelles (temps total, par genre, par
    jour) sans avoir à gérer de fusion de sessions qui se chevauchent ou expirent."""
    __tablename__ = "reading_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[str] = mapped_column(String, nullable=False)  # "YYYY-MM-DD", UTC
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "tome_id", "day", name="uq_reading_activity"),
        Index("idx_reading_activity_user_day", "user_id", "day"),
    )
