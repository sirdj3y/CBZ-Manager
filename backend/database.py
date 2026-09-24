from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.DB_PATH}",
    echo=settings.DEV_MODE,
    connect_args={"check_same_thread": False, "timeout": 30},
)


async def _set_wal_mode(conn):
    await conn.execute(__import__('sqlalchemy').text("PRAGMA journal_mode=WAL"))
    await conn.execute(__import__('sqlalchemy').text("PRAGMA busy_timeout=30000"))

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    from . import models  # noqa: F401 — ensures models are registered
    async with engine.begin() as conn:
        await _set_wal_mode(conn)
        await conn.run_sync(Base.metadata.create_all)
        # Migrations manuelles pour colonnes ajoutées après création initiale
        for sql in [
            "ALTER TABLE series ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE tomes ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE series ADD COLUMN track_new_albums BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE series ADD COLUMN bedetheque_url TEXT",
            "ALTER TABLE series ADD COLUMN bedetheque_match_status TEXT",
            "ALTER TABLE tomes ADD COLUMN file_mtime REAL",
            "ALTER TABLE series ADD COLUMN bedetheque_status TEXT",
            "ALTER TABLE metadata ADD COLUMN CommunityRating TEXT",
            "ALTER TABLE metadata ADD COLUMN bedetheque_votes INTEGER",
            "ALTER TABLE series ADD COLUMN bedetheque_resume TEXT",
            "ALTER TABLE activity_log ADD COLUMN user_id INTEGER",
            "ALTER TABLE activity_log ADD COLUMN username_snapshot TEXT",
            "ALTER TABLE activity_log ADD COLUMN ip_address TEXT",
            "ALTER TABLE users ADD COLUMN avatar_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE convert_jobs ADD COLUMN user_id INTEGER",
            "ALTER TABLE tomes ADD COLUMN content_hash TEXT",
            "ALTER TABLE users ADD COLUMN notifications_last_seen_at TEXT",
            "ALTER TABLE tomes ADD COLUMN is_oneshot BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN custom_permissions TEXT",
            "ALTER TABLE series ADD COLUMN classification TEXT",
            "ALTER TABLE smart_lists ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE smart_lists ADD COLUMN result_type TEXT NOT NULL DEFAULT 'tome'",
            "ALTER TABLE missing_albums ADD COLUMN writer TEXT",
            "ALTER TABLE missing_albums ADD COLUMN penciller TEXT",
            "ALTER TABLE missing_albums ADD COLUMN publisher TEXT",
            "ALTER TABLE series ADD COLUMN age_rating TEXT",
            "ALTER TABLE series ADD COLUMN hero_background_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE series ADD COLUMN hero_logo_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE series ADD COLUMN hero_character_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tomes ADD COLUMN cover_width INTEGER",
            "ALTER TABLE tomes ADD COLUMN cover_height INTEGER",
            "ALTER TABLE user_tome_data ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN age_rating_limit TEXT",
        ]:
            try:
                await conn.execute(__import__('sqlalchemy').text(sql))
            except Exception:
                pass  # Colonne déjà existante

        # CREATE INDEX IF NOT EXISTS est nativement idempotent (pas besoin du try/except
        # ci-dessus) — create_all() ne crée les index déclarés dans __table_args__ que pour
        # une table neuve, jamais rétroactivement sur une table déjà existante (tomes ici).
        await conn.execute(__import__('sqlalchemy').text(
            "CREATE INDEX IF NOT EXISTS idx_tomes_content_hash ON tomes(content_hash)"
        ))

        # Table minimale de suivi des migrations ponctuelles (celles qui ne sont pas de
        # simples ALTER TABLE idempotents) — sans ça, un backfill exécuté "sans effet sur les
        # lignes déjà à jour" peut quand même annuler un choix manuel fait ENTRE deux
        # démarrages (voir juste en dessous).
        await conn.execute(__import__('sqlalchemy').text(
            "CREATE TABLE IF NOT EXISTS applied_migrations (name TEXT PRIMARY KEY, applied_at TEXT)"
        ))
        already_applied = {
            row[0] for row in (await conn.execute(__import__('sqlalchemy').text(
                "SELECT name FROM applied_migrations"
            ))).fetchall()
        }

        # Pré-remplissage ponctuel de is_read (colonne neuve, toujours à 0 par défaut) pour
        # les lectures déjà terminées avant l'introduction du champ — sans ça, tous les
        # albums déjà lus à ≥95% réapparaîtraient d'un coup dans "Poursuivre la lecture"
        # (qui se base maintenant sur is_read plutôt que de recalculer le seuil à la volée).
        # Exécuté UNE SEULE FOIS (voir applied_migrations ci-dessus) : rejoué à chaque
        # démarrage, il annulerait un "marquer comme non lu" manuel fait après coup sur un
        # album dont last_page est resté ≥95% (l'utilisateur n'a pas forcément remis la page
        # à 0 en décochant) — le WHERE is_read = 0 de cette requête ne protège que contre les
        # lignes déjà repassées à 1, pas contre celles explicitement repassées à 0 entre deux
        # démarrages.
        if "is_read_backfill_2026" not in already_applied:
            await conn.execute(__import__('sqlalchemy').text(
                """
                UPDATE user_tome_data SET is_read = 1
                WHERE is_read = 0
                  AND (SELECT page_count FROM tomes WHERE tomes.id = user_tome_data.tome_id) > 0
                  AND last_page >= 0.95 * (SELECT page_count FROM tomes WHERE tomes.id = user_tome_data.tome_id)
                """
            ))
            await conn.execute(
                __import__('sqlalchemy').text("INSERT INTO applied_migrations (name, applied_at) VALUES (:name, :now)"),
                {"name": "is_read_backfill_2026", "now": __import__('datetime').datetime.utcnow().isoformat()},
            )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
