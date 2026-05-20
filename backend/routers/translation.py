"""LLM translation trigger."""

import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, async_session_factory
from models.orm import Video
from services.workflow import run_translate
from routers.videos import notify_progress
import asyncio

router = APIRouter(prefix="/api/videos", tags=["translation"])


@router.post("/{video_id}/translate")
async def trigger_translate(video_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger LLM translation for all sentences in a video."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if v.segment_status != "completed":
        raise HTTPException(status_code=400, detail="请先完成断句")
    if v.translate_status == "processing":
        raise HTTPException(status_code=400, detail="翻译正在进行中")

    asyncio.create_task(_run_translate_task(video_id))
    return {"message": "AI 翻译已开始", "video_id": video_id}


async def _run_translate_task(video_id: str):
    """Run translation in background with its own DB session."""
    async with async_session_factory() as db:
        try:
            await run_translate(video_id, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()
