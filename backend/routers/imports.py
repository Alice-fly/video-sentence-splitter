"""Video import triggers: YouTube, Bilibili, local file."""

import traceback
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, async_session_factory
from models.orm import Video, VideoStatus
from models.schemas import ImportStart
from services.workflow import run_import_youtube, run_import_bilibili
from routers.videos import notify_progress, _video_to_out
from config import VIDEOS_DIR
import asyncio
import os

router = APIRouter(prefix="/api/videos", tags=["imports"])


@router.post("/{video_id}/import/youtube")
async def trigger_import_youtube(
    video_id: str,
    body: ImportStart,
    db: AsyncSession = Depends(get_db),
):
    """Trigger YouTube video download with yt-dlp."""
    from sqlalchemy import select

    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if v.import_status == "processing":
        raise HTTPException(status_code=400, detail="视频正在导入中")

    v.url = body.url or v.url
    v.original_language = body.original_language or v.original_language
    v.source_type = "youtube"
    await db.commit()

    asyncio.create_task(_run_import_task(video_id, "youtube", body.url or v.url, body.original_language or v.original_language))

    return {"message": "YouTube 导入已开始", "video_id": video_id}


@router.post("/{video_id}/import/bilibili")
async def trigger_import_bilibili(
    video_id: str,
    body: ImportStart,
    db: AsyncSession = Depends(get_db),
):
    """Trigger Bilibili video download with yt-dlp."""
    from sqlalchemy import select

    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if v.import_status == "processing":
        raise HTTPException(status_code=400, detail="视频正在导入中")

    v.url = body.url or v.url
    v.original_language = body.original_language or v.original_language
    v.source_type = "bilibili"
    await db.commit()

    asyncio.create_task(_run_import_task(video_id, "bilibili", body.url or v.url, body.original_language or v.original_language))

    return {"message": "B站导入已开始", "video_id": video_id}


@router.post("/local")
async def add_local_video(
    file: UploadFile = File(...),
    original_language: str = Form("auto"),
    category_id: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a local video file and create a video record with import completed."""
    video = Video(
        url=f"local://{file.filename}",
        original_language=original_language,
        category_id=category_id,
        source_type="local_file",
        uploaded_filename=file.filename,
        status=VideoStatus.pending,
        progress=0,
        progress_message="本地文件已就绪",
        import_status="completed",
        import_progress=100,
        import_progress_message="本地文件已就绪",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    video_path = os.path.join(VIDEOS_DIR, f"{video.id}.mp4")
    content = await file.read()
    with open(video_path, "wb") as f:
        f.write(content)

    # Extract duration via ffprobe
    try:
        from utils.subprocess import run_cmd
        result = await run_cmd([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ])
        if result.returncode == 0:
            dur = float(result.stdout.decode("utf-8", errors="replace").strip())
            video.duration = dur
    except Exception:
        pass

    video.local_video_path = video_path
    await db.commit()
    await db.refresh(video)

    return _video_to_out(video, 0)


@router.post("/{video_id}/process-all")
async def process_all(video_id: str, db: AsyncSession = Depends(get_db)):
    """One-click: run the full pipeline (import → subtitle → segment → translate)."""
    from sqlalchemy import select
    from services.workflow import run_full_pipeline

    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")

    asyncio.create_task(_run_full_pipeline_task(video_id, v.url, v.original_language or "auto"))
    return {"message": "全流程处理已开始", "video_id": video_id}


async def _run_full_pipeline_task(video_id: str, url: str, language: str):
    """Run full pipeline in background with its own DB session."""
    from services.workflow import run_full_pipeline
    async with async_session_factory() as db:
        try:
            await run_full_pipeline(video_id, url, language, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()


async def _run_import_task(video_id: str, source: str, url: str, language: str):
    """Run import in background with its own DB session."""
    async with async_session_factory() as db:
        try:
            if source == "youtube":
                await run_import_youtube(video_id, url, language, db, notify=notify_progress)
            elif source == "bilibili":
                await run_import_bilibili(video_id, url, language, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()
