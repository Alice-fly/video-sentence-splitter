"""Subtitle acquisition triggers: Whisper, file import."""

import traceback
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, async_session_factory
from models.orm import Video, RawSubtitle
from services.workflow import run_subtitle_whisper, run_subtitle_embedded
from routers.videos import notify_progress
from utils.subtitle_parser import parse_vtt, parse_srt
import asyncio

router = APIRouter(prefix="/api/videos", tags=["subtitles"])


@router.post("/{video_id}/subtitle/whisper")
async def trigger_subtitle_whisper(video_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger Whisper speech recognition for a video."""
    v = await _get_video(video_id, db)
    if v.subtitle_status == "processing":
        raise HTTPException(status_code=400, detail="字幕提取正在进行中")

    asyncio.create_task(_run_subtitle_task(video_id, "whisper"))
    return {"message": "Whisper 语音识别已开始", "video_id": video_id}


@router.post("/{video_id}/subtitle/import")
async def trigger_subtitle_import(
    video_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import subtitles from an SRT or VTT file."""
    v = await _get_video(video_id, db)
    if v.subtitle_status == "processing":
        raise HTTPException(status_code=400, detail="字幕提取正在进行中")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    if file.filename and file.filename.endswith(".vtt"):
        entries = parse_vtt(text)
    else:
        entries = parse_srt(text)

    if not entries:
        raise HTTPException(status_code=400, detail="字幕文件解析为空")

    # Clear old, save new
    await db.execute(select(RawSubtitle).where(RawSubtitle.video_id == video_id))
    from sqlalchemy import delete
    await db.execute(delete(RawSubtitle).where(RawSubtitle.video_id == video_id))

    for e in entries:
        db.add(RawSubtitle(
            video_id=video_id,
            index=e.index,
            start_time=e.start,
            end_time=e.end,
            text=e.text,
        ))

    v.subtitle_status = "completed"
    v.subtitle_method = "local_import"
    v.subtitle_progress = 100
    v.subtitle_progress_message = f"已导入字幕 ({len(entries)} 条)"
    v.segment_status = "not_started"
    v.translate_status = "not_started"
    await db.commit()

    return {"message": f"已导入 {len(entries)} 条字幕", "video_id": video_id, "count": len(entries)}


@router.get("/{video_id}/subtitles")
async def get_raw_subtitles(video_id: str, db: AsyncSession = Depends(get_db)):
    """Get raw subtitle entries for a video."""
    result = await db.execute(
        select(RawSubtitle).where(RawSubtitle.video_id == video_id).order_by(RawSubtitle.index)
    )
    rows = result.scalars().all()
    return [
        {"id": r.id, "index": r.index, "start_time": r.start_time,
         "end_time": r.end_time, "text": r.text}
        for r in rows
    ]


async def _get_video(video_id: str, db: AsyncSession) -> Video:
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    return v


async def _run_subtitle_task(video_id: str, method: str):
    """Run subtitle acquisition in background with its own DB session."""
    async with async_session_factory() as db:
        try:
            if method == "whisper":
                await run_subtitle_whisper(video_id, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()
