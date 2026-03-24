from datetime import datetime
from sqlalchemy import (
    Integer, String, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    folder_path: Mapped[str] = mapped_column(String, nullable=False)
    cover_tome_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tomes.id"), nullable=True)
    tome_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    tomes: Mapped[list["Tome"]] = relationship(
        "Tome", back_populates="series",
        foreign_keys="Tome.series_id",
        cascade="all, delete-orphan",
        order_by="Tome.number"
    )


class Tome(Base):
    __tablename__ = "tomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    filepath: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    file_format: Mapped[str] = mapped_column(String, nullable=False)  # cbz/cbr/pdf
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number: Mapped[str | None] = mapped_column(String, nullable=True)  # "01", "02"…
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_metadata: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="no_metadata")  # ok/no_metadata/error/cbr_unsupported
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Annotations utilisateur
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1-5
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON array
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    series: Mapped["Series"] = relationship("Series", back_populates="tomes", foreign_keys=[series_id])
    metadata_: Mapped["Metadata | None"] = relationship("Metadata", back_populates="tome", uselist=False, cascade="all, delete-orphan")
    reading_progress: Mapped["ReadingProgress | None"] = relationship("ReadingProgress", back_populates="tome", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tomes_series_id", "series_id"),
        Index("idx_tomes_number", "series_id", "number"),
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

    tome: Mapped["Tome"] = relationship("Tome", back_populates="metadata_")


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id", ondelete="CASCADE"), nullable=False, unique=True)
    last_page: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tome: Mapped["Tome"] = relationship("Tome", back_populates="reading_progress")


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/running/done/error
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tomes: Mapped[list["ConvertJobTome"]] = relationship("ConvertJobTome", back_populates="job", cascade="all, delete-orphan")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String, nullable=False)  # scan/convert/delete_series/delete_tome/rename
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok/error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConvertJobTome(Base):
    __tablename__ = "convert_job_tomes"

    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("convert_jobs.id", ondelete="CASCADE"), primary_key=True)
    tome_id: Mapped[int] = mapped_column(Integer, ForeignKey("tomes.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)

    job: Mapped["ConvertJob"] = relationship("ConvertJob", back_populates="tomes")
