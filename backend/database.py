import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import DATA_DIR

DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'app.db')}"

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


async def _enable_wal():
    """Enable WAL mode for better concurrent read/write performance."""
    import aiosqlite
    db_path = os.path.join(DATA_DIR, "app.db")
    async with aiosqlite.connect(db_path) as db:
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


async def init_db():
    from models.orm import Video, Category, Sentence, Settings, RawSubtitle  # noqa: F401
    await _enable_wal()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_step_columns(conn)
        await _backfill_existing_videos(conn)
