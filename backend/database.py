import os
import shutil
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import DATA_DIR

logger = logging.getLogger(__name__)

DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'app.db')}"
DB_PATH = os.path.join(DATA_DIR, "app.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = 5

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _backup_database() -> str | None:
    """Create a timestamped backup of the database before running migrations.
    Returns the backup path if successful, None otherwise.
    """
    if not os.path.exists(DB_PATH):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"app_{timestamp}.db")
        shutil.copy2(DB_PATH, backup_path)

        # Rotate old backups: keep only the last MAX_BACKUPS
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith("app_") and f.endswith(".db")],
            reverse=True,
        )
        for old in backups[MAX_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, old))

        logger.info("Database backup created: %s", backup_path)
        return backup_path
    except Exception as e:
        logger.warning("Failed to create database backup: %s", e)
        return None


async def _enable_wal():
    """Enable WAL mode for better concurrent read/write performance."""
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")


async def _migrate_step_columns(conn):
    """Add per-step columns to Video if they don't exist yet."""
    new_columns = [
        ("source_type", "TEXT"),
        ("uploaded_filename", "TEXT"),
        ("import_status", "TEXT DEFAULT 'not_started'"),
        ("import_progress", "INTEGER DEFAULT 0"),
        ("import_progress_message", "TEXT DEFAULT ''"),
        ("import_error_message", "TEXT"),
        ("subtitle_status", "TEXT DEFAULT 'not_started'"),
        ("subtitle_method", "TEXT"),
        ("subtitle_progress", "INTEGER DEFAULT 0"),
        ("subtitle_progress_message", "TEXT DEFAULT ''"),
        ("subtitle_error_message", "TEXT"),
        ("segment_status", "TEXT DEFAULT 'not_started'"),
        ("segment_progress", "INTEGER DEFAULT 0"),
        ("segment_progress_message", "TEXT DEFAULT ''"),
        ("segment_error_message", "TEXT"),
        ("translate_status", "TEXT DEFAULT 'not_started'"),
        ("translate_progress", "INTEGER DEFAULT 0"),
        ("translate_progress_message", "TEXT DEFAULT ''"),
        ("translate_error_message", "TEXT"),
        ("trim_start", "REAL"),
        ("trim_end", "REAL"),
    ]

    # Get existing columns
    from sqlalchemy import text
    result = await conn.execute(text("PRAGMA table_info(videos)"))
    existing = {row[1] for row in result.fetchall()}

    for col_name, col_def in new_columns:
        if col_name not in existing:
            await conn.execute(text(f"ALTER TABLE videos ADD COLUMN {col_name} {col_def}"))

    # Add edited_at to sentences
    result = await conn.execute(text("PRAGMA table_info(sentences)"))
    sent_cols = {row[1] for row in result.fetchall()}
    if "edited_at" not in sent_cols:
        await conn.execute(text("ALTER TABLE sentences ADD COLUMN edited_at DATETIME"))


async def _backfill_existing_videos(conn):
    """Backfill per-step status for videos created before the migration."""
    from sqlalchemy import text

    result = await conn.execute(text("SELECT id, url, status, error_message FROM videos WHERE import_status = 'not_started'"))
    rows = result.fetchall()

    for vid_id, url, status, error_msg in rows:
        src = None
        if url:
            if "youtube.com" in url or "youtu.be" in url:
                src = "youtube"
            elif "bilibili.com" in url:
                src = "bilibili"

        if status == "completed":
            await conn.execute(text("""
                UPDATE videos SET
                    source_type = :src,
                    import_status = 'completed',
                    subtitle_status = 'completed',
                    segment_status = 'completed',
                    translate_status = 'completed'
                WHERE id = :id
            """), {"src": src, "id": vid_id})
        elif status == "failed":
            await conn.execute(text("""
                UPDATE videos SET
                    source_type = :src,
                    import_status = 'completed',
                    subtitle_status = 'failed',
                    subtitle_error_message = :err
                WHERE id = :id
            """), {"src": src, "err": error_msg, "id": vid_id})
        elif status == "fetching":
            await conn.execute(text("""
                UPDATE videos SET source_type = :src, import_status = 'processing' WHERE id = :id
            """), {"src": src, "id": vid_id})
        elif status == "subtitle_extracting":
            await conn.execute(text("""
                UPDATE videos SET
                    source_type = :src,
                    import_status = 'completed',
                    subtitle_status = 'processing'
                WHERE id = :id
            """), {"src": src, "id": vid_id})
        elif status == "segmenting":
            await conn.execute(text("""
                UPDATE videos SET
                    source_type = :src,
                    import_status = 'completed',
                    subtitle_status = 'completed',
                    segment_status = 'processing'
                WHERE id = :id
            """), {"src": src, "id": vid_id})
        # pending — leave all not_started


async def _run_integrity_check():
    """Run SQLite integrity check and log warnings if corruption detected."""
    import aiosqlite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            result = await db.execute("PRAGMA integrity_check")
            row = await result.fetchone()
            if row and row[0] != "ok":
                logger.warning("Database integrity check: %s", row[0])
            else:
                logger.info("Database integrity check: ok")
    except Exception as e:
        logger.warning("Database integrity check failed: %s", e)


async def checkpoint_database():
    """Flush WAL to main database file. Call on graceful shutdown to prevent data loss."""
    import aiosqlite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info("WAL checkpoint completed")
    except Exception as e:
        logger.warning("WAL checkpoint failed: %s", e)


async def init_db():
    """Initialize database: create tables, run migrations, backfill data.
    Creates a backup before any schema changes to prevent data loss.
    """
    from models.orm import Video, Category, Sentence, Settings, RawSubtitle  # noqa: F401

    # 1. Backup before any changes
    _backup_database()

    # 2. Enable WAL mode
    await _enable_wal()

    # 3. Run integrity check
    await _run_integrity_check()

    # 4. Create tables and run migrations in a single transaction
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _migrate_step_columns(conn)
            await _backfill_existing_videos(conn)
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
        raise
