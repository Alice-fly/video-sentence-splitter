"""LLM semantic segmentation trigger."""

import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, async_session_factory
from models.orm import Video
from services.workflow import run_segment
from routers.videos import notify_progress
import asyncio

router = APIRouter(prefix="/api/videos", tags=["segmentation"])


@router.post("/{video_id}/segment")
async def trigger_segment(video_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger LLM semantic sentence segmentation."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if v.subtitle_status != "completed":
        raise HTTPException(status_code=400, detail="请先完成字幕提取")
    if v.segment_status == "processing":
        raise HTTPException(status_code=400, detail="断句正在进行中")

    asyncio.create_task(_run_segment_task(video_id))
    return {"message": "AI 语义断句已开始", "video_id": video_id}


async def _run_segment_task(video_id: str):
    """Run segmentation in background with its own DB session."""
    async with async_session_factory() as db:
        try:
            await run_segment(video_id, db, notify=notify_progress)
        except Exception as e:
            traceback.print_exc()
