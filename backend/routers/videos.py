import json
import os
import traceback
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, async_session_factory
from models.orm import Video, Sentence, RawSubtitle, VideoStatus
from models.schemas import (
    VideoAddRequest, VideoOut, VideoUpdate, SentenceOut, SentenceUpdate, SentenceCreate,
)
from config import VIDEOS_DIR

router = APIRouter(prefix="/api/videos", tags=["videos"])

# WebSocket connection pool: video_id → list[WebSocket]
ws_connections: dict[str, list[WebSocket]] = {}


def _video_to_out(v: Video, sentence_count: int = 0) -> VideoOut:
    return VideoOut(
        id=v.id,
        url=v.url,
        title=v.title,
        thumbnail=v.thumbnail,
        category_id=v.category_id,
        status=v.compute_legacy_status(),
        progress=v.compute_legacy_progress(),
        progress_message=v.progress_message,
        original_language=v.original_language,
        error_message=v.error_message,
        duration=v.duration,
        stream_url=v.stream_url,
        local_video_path=v.local_video_path,
        created_at=v.created_at,
        updated_at=v.updated_at,
        sentence_count=sentence_count,
        source_type=v.source_type,
        import_status=v.import_status or "not_started",
        import_progress=v.import_progress or 0,
        import_progress_message=v.import_progress_message or "",
        import_error_message=v.import_error_message,
        subtitle_status=v.subtitle_status or "not_started",
        subtitle_method=v.subtitle_method,
        subtitle_progress=v.subtitle_progress or 0,
        subtitle_progress_message=v.subtitle_progress_message or "",
        subtitle_error_message=v.subtitle_error_message,
        segment_status=v.segment_status or "not_started",
        segment_progress=v.segment_progress or 0,
        segment_progress_message=v.segment_progress_message or "",
        segment_error_message=v.segment_error_message,
        translate_status=v.translate_status or "not_started",
        translate_progress=v.translate_progress or 0,
        translate_progress_message=v.translate_progress_message or "",
        translate_error_message=v.translate_error_message,
    )


async def notify_progress(video: Video, step: str = ""):
    """Push video progress update to all connected WebSocket clients."""
    if video.id not in ws_connections:
        return
    data = {
        "type": "progress",
        "video_id": video.id,
        "step": step,
        "status": video.compute_legacy_status(),
        "progress": video.compute_legacy_progress(),
        "progress_message": video.progress_message,
        "error_message": video.error_message,
        "import_status": video.import_status,
        "import_progress": video.import_progress,
        "import_progress_message": video.import_progress_message,
        "subtitle_status": video.subtitle_status,
        "subtitle_progress": video.subtitle_progress,
        "subtitle_progress_message": video.subtitle_progress_message,
        "segment_status": video.segment_status,
        "segment_progress": video.segment_progress,
        "segment_progress_message": video.segment_progress_message,
        "translate_status": video.translate_status,
        "translate_progress": video.translate_progress,
        "translate_progress_message": video.translate_progress_message,
    }
    dead: list[WebSocket] = []
    for ws in ws_connections.get(video.id, []):
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_connections.get(video.id, []).remove(ws)


# ── Status mapping for filtering ──
def _matches_status(v: Video, status_filter: str) -> bool:
    """Match a video against a legacy status filter using per-step states."""
    if status_filter == "completed":
        return v.compute_legacy_status() == "completed"
    if status_filter == "failed":
        return (
            v.import_status == "failed"
            or v.subtitle_status == "failed"
            or v.segment_status == "failed"
            or v.translate_status == "failed"
        )
    if status_filter == "processing":
        legacy = v.compute_legacy_status()
        return legacy not in ("pending", "completed", "failed")
    return True


@router.get("", response_model=list[VideoOut])
async def list_videos(
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Video)
    if category_id:
        query = query.where(Video.category_id == category_id)
    query = query.order_by(Video.created_at.desc())
    result = await db.execute(query)
    videos = result.scalars().all()

    out: list[VideoOut] = []
    for v in videos:
        if status and not _matches_status(v, status):
            continue
        count_result = await db.execute(
            select(Sentence).where(Sentence.video_id == v.id)
        )
        sentence_count = len(count_result.scalars().all())
        out.append(_video_to_out(v, sentence_count))
    return out


@router.get("/{video_id}", response_model=VideoOut)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    count_result = await db.execute(select(Sentence).where(Sentence.video_id == v.id))
    sentence_count = len(count_result.scalars().all())
    return _video_to_out(v, sentence_count)


@router.post("", response_model=VideoOut)
async def add_video(body: VideoAddRequest, db: AsyncSession = Depends(get_db)):
    """Create a video record. Does NOT auto-trigger processing.
    Use /api/videos/{id}/import/* endpoints to start importing.
    """
    video = Video(
        url=body.url,
        original_language=body.original_language,
        category_id=body.category_id,
        source_type=body.source_type,
        trim_start=body.trim_start,
        trim_end=body.trim_end,
        status=VideoStatus.pending,
        progress=0,
        progress_message="等待导入...",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return _video_to_out(video, 0)


@router.put("/{video_id}", response_model=VideoOut)
async def update_video(video_id: str, body: VideoUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if body.title is not None:
        v.title = body.title
    if body.category_id is not None:
        v.category_id = body.category_id
    if body.original_language is not None:
        v.original_language = body.original_language
    await db.commit()
    await db.refresh(v)
    count_result = await db.execute(select(Sentence).where(Sentence.video_id == v.id))
    sentence_count = len(count_result.scalars().all())
    return _video_to_out(v, sentence_count)


@router.delete("/{video_id}")
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    # Delete local video file
    if v.local_video_path and os.path.exists(v.local_video_path):
        os.remove(v.local_video_path)
    # Delete subtitle file
    if v.subtitle_path and os.path.exists(v.subtitle_path):
        os.remove(v.subtitle_path)
    await db.delete(v)
    await db.commit()
    return {"message": "已删除"}


@router.get("/{video_id}/sentences", response_model=list[SentenceOut])
async def get_sentences(video_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Sentence).where(Sentence.video_id == video_id).order_by(Sentence.index)
    )
    rows = result.scalars().all()
    return [SentenceOut.model_validate(r) for r in rows]


@router.put("/{video_id}/sentences/{sentence_id}", response_model=SentenceOut)
async def update_sentence(
    video_id: str,
    sentence_id: str,
    body: SentenceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Edit a sentence's text or timestamps inline."""
    result = await db.execute(
        select(Sentence).where(Sentence.id == sentence_id, Sentence.video_id == video_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="句子不存在")
    if body.original_text is not None:
        s.original_text = body.original_text
    if body.translated_text is not None:
        s.translated_text = body.translated_text
    if body.start_time is not None:
        s.start_time = body.start_time
    if body.end_time is not None:
        s.end_time = body.end_time
        if s.start_time is not None:
            s.duration = round(s.end_time - s.start_time, 3)
    s.edited_at = datetime.utcnow()
    await db.commit()
    await db.refresh(s)
    return SentenceOut.model_validate(s)


@router.post("/{video_id}/sentences", response_model=SentenceOut)
async def create_sentence(
    video_id: str,
    body: SentenceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Insert a new sentence at the given index, shifting later sentences down."""
    # Shift existing sentences at >= index
    result = await db.execute(
        select(Sentence).where(
            Sentence.video_id == video_id,
            Sentence.index >= body.index,
        )
    )
    for s in result.scalars().all():
        s.index += 1

    new_s = Sentence(
        video_id=video_id,
        index=body.index,
        original_text=body.original_text,
        translated_text=body.translated_text,
        start_time=body.start_time,
        end_time=body.end_time,
        duration=round(body.end_time - body.start_time, 3) if body.end_time and body.start_time else 0,
    )
    db.add(new_s)
    await db.commit()
    await db.refresh(new_s)
    return SentenceOut.model_validate(new_s)


@router.delete("/{video_id}/sentences/{sentence_id}")
async def delete_sentence(
    video_id: str,
    sentence_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a sentence and renumber the rest."""
    result = await db.execute(
        select(Sentence).where(Sentence.id == sentence_id, Sentence.video_id == video_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="句子不存在")

    deleted_index = s.index
    await db.delete(s)

    # Renumber following sentences
    result = await db.execute(
        select(Sentence).where(
            Sentence.video_id == video_id,
            Sentence.index > deleted_index,
        ).order_by(Sentence.index)
    )
    for following in result.scalars().all():
        following.index -= 1

    await db.commit()
    return {"message": "已删除"}


@router.get("/{video_id}/subtitles", response_model=list[dict])
async def get_raw_subtitles(video_id: str, db: AsyncSession = Depends(get_db)):
    """Get raw subtitle entries (before segmentation)."""
    result = await db.execute(
        select(RawSubtitle).where(RawSubtitle.video_id == video_id).order_by(RawSubtitle.index)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "index": r.index,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "text": r.text,
        }
        for r in rows
    ]


@router.get("/{video_id}/stream")
async def stream_video(video_id: str, db: AsyncSession = Depends(get_db)):
    """Serve locally cached video file with native Range request support for seeking."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v or not v.local_video_path:
        raise HTTPException(status_code=404, detail="视频文件不存在")
    if not os.path.exists(v.local_video_path):
        raise HTTPException(status_code=404, detail="视频文件未找到，请重新处理")
    return FileResponse(
        v.local_video_path,
        media_type="video/mp4",
        filename=f"{v.title or video_id}.mp4",
    )


@router.get("/{video_id}/thumbnail")
async def thumbnail(video_id: str, db: AsyncSession = Depends(get_db)):
    """Serve video thumbnail. Serves local file if cached, otherwise redirects to stored URL."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if not v.thumbnail:
        raise HTTPException(status_code=404, detail="无封面")

    # Check for local thumbnail file
    thumb_file = os.path.join(VIDEOS_DIR, f"{video_id}_thumb.jpg")
    if os.path.exists(thumb_file) and os.path.getsize(thumb_file) > 0:
        return FileResponse(thumb_file, media_type="image/jpeg")

    # Fall back to stored URL (backward compat for old videos)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=v.thumbnail, status_code=302)


@router.websocket("/ws/{video_id}")
async def video_websocket(ws: WebSocket, video_id: str):
    await ws.accept()
    ws_connections.setdefault(video_id, []).append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_connections.get(video_id, []).remove(ws)


# ── Legacy pipeline (for backward compat / one-click) ──
async def _run_pipeline_task(video_id: str, url: str, language: str):
    """Run full pipeline in background with its own DB session."""
    from services.pipeline import run_pipeline
    async with async_session_factory() as db:
        try:
            await run_pipeline(video_id, url, language, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()
            result = await db.execute(select(Video).where(Video.id == video_id))
            video = result.scalar_one_or_none()
            if video:
                video.status = VideoStatus.failed
                video.error_message = str(e) or repr(e)
                video.progress_message = f"处理失败: {video.error_message}"
                await db.commit()
                await notify_progress(video)
