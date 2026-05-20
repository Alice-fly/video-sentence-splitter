import traceback
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.orm import Video, Sentence, VideoStatus, Settings
from services.fetcher import fetch_video_info, _detect_platform
from services.segmenter import segment, translate
from services.whisper import extract_subtitles_whisper
from utils.subtitle_parser import parse_vtt, parse_srt


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(Settings).where(Settings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def _get_all_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(Settings))
    rows = result.scalars().all()
    return {r.key: r.value for r in rows}


async def _update_progress(
    db: AsyncSession,
    video: Video,
    status: VideoStatus,
    message: str,
    progress: int,
    notify: Optional[Callable] = None,
):
    video.status = status
    video.progress = progress
    video.progress_message = message
    await db.commit()
    await db.refresh(video)
    if notify:
        await notify(video)


async def run_pipeline(
    video_id: str,
    url: str,
    original_language: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Streaming pipeline: download video + subtitles → segment → save timestamps."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    try:
        # ── Step 0: Load settings ──
        video_quality = await _get_setting(db, "video_quality", "720p")
        subtitle_method = await _get_setting(db, "subtitle_method", "whisper")
        whisper_model_size = await _get_setting(db, "whisper_model_size", "small")
        whisper_device = await _get_setting(db, "whisper_device", "auto")
        whisper_compute_type = await _get_setting(db, "whisper_compute_type", "auto")
        whisper_beam_size_str = await _get_setting(db, "whisper_beam_size", "5")
        try:
            whisper_beam_size = int(whisper_beam_size_str)
        except (ValueError, TypeError):
            whisper_beam_size = 5
        whisper_vad_filter = await _get_setting(db, "whisper_vad_filter", "true") in ("true", "True", "1")

        # Platform-aware cookie selection
        platform = _detect_platform(url)
        if platform == "youtube":
            cookies_from_browser = await _get_setting(db, "cookies_from_browser_youtube", "")
            cookies_text = await _get_setting(db, "cookies_text_youtube", "")
        elif platform == "bilibili":
            cookies_from_browser = await _get_setting(db, "cookies_from_browser_bilibili", "")
            cookies_text = await _get_setting(db, "cookies_text_bilibili", "")
        else:
            cookies_from_browser = ""
            cookies_text = ""

        # ── Step 1: Download video to local cache + extract subtitles ──
        await _update_progress(db, video, VideoStatus.fetching, "正在下载视频...", 5, notify)

        local_video_path, subtitle_path, title, thumbnail, duration = await fetch_video_info(
            url, video_id, quality=video_quality,
            cookies_from_browser=cookies_from_browser,
            cookies_text=cookies_text,
        )

        video.title = title or "Untitled"
        video.thumbnail = thumbnail
        video.stream_url = local_video_path  # keep for backward compat, now points to local file
        video.local_video_path = local_video_path
        video.subtitle_path = subtitle_path or ""
        video.duration = duration
        await db.commit()

        # ── Step 2: Get subtitle entries (file / Whisper) ──
        if subtitle_path:
            # ── Branch A: Soft subtitles from file ──
            await _update_progress(db, video, VideoStatus.fetching, "正在读取字幕文件...", 20, notify)

            with open(subtitle_path, "r", encoding="utf-8") as f:
                sub_content = f.read()

            if subtitle_path.endswith(".vtt"):
                entries = parse_vtt(sub_content)
            else:
                entries = parse_srt(sub_content)

        elif subtitle_method == "whisper":
            # ── Branch B: Whisper speech recognition ──
            await _update_progress(db, video, VideoStatus.subtitle_extracting,
                "无软字幕，正在 Whisper 语音识别字幕...", 20, notify)

            async def whisper_progress(stage: str, current: int = 0, total: int = 0):
                if stage == "extracting_audio":
                    await _update_progress(db, video, VideoStatus.subtitle_extracting,
                        "正在从视频中提取音频...", 25, notify)
                elif stage == "loading_model":
                    await _update_progress(db, video, VideoStatus.subtitle_extracting,
                        "正在加载 Whisper 模型...", 28, notify)
                elif stage == "transcribing":
                    if total > 0 and current >= total:
                        await _update_progress(db, video, VideoStatus.subtitle_extracting,
                            f"Whisper 语音识别完成 ({current} 段)...", 45, notify)
                    elif total > 0:
                        pct = 28 + int((current / total) * 17)
                        await _update_progress(db, video, VideoStatus.subtitle_extracting,
                            f"正在 Whisper 语音识别 ({current}/{total})...", pct, notify)
                    else:
                        # Indeterminate progress: pulse between 28-42
                        pct = 28 + (current % 100) % 15
                        await _update_progress(db, video, VideoStatus.subtitle_extracting,
                            f"正在 Whisper 语音识别 (已识别 {current} 段)...", pct, notify)

            entries = await extract_subtitles_whisper(
                local_video_path, video_id,
                language=original_language,
                progress_callback=whisper_progress,
                model_size=whisper_model_size,
                device=whisper_device,
                compute_type=whisper_compute_type,
                beam_size=whisper_beam_size,
                vad_filter=whisper_vad_filter,
            )

        if not entries:
            raise ValueError("未能提取到任何字幕文本，该视频可能无字幕或字幕无法识别。")

        # ── Step 3: LLM semantic segmentation ──
        entry_count = len(entries)
        if entry_count > 200:
            await _update_progress(db, video, VideoStatus.segmenting,
                f"字幕条目较多({entry_count}条)，正在分批调用 AI 进行语义断句...", 50, notify)
        else:
            await _update_progress(db, video, VideoStatus.segmenting,
                "正在调用 AI 进行语义断句...", 50, notify)

        settings = await _get_all_settings(db)
        api_key = settings.get("deepseek_api_key", "")
        base_url = settings.get("deepseek_base_url", "https://api.deepseek.com")
        model = settings.get("deepseek_model", "")
        target_language = settings.get("target_language", "中文")
        max_mode = settings.get("deepseek_max_mode", "false") in ("true", "True", "1")

        if not api_key:
            raise ValueError("请先在设置页面配置 DeepSeek API Key。")
        if not model:
            raise ValueError("请先在设置页面检测并选择模型。")

        async def segment_progress(current: int, total: int):
            if total > 1:
                pct = 50 + int((current / total) * 20)
                await _update_progress(db, video, VideoStatus.segmenting,
                    f"正在分批调用 AI 断句 ({current + 1}/{total})...", pct, notify)

        segments = await segment(
            entries=entries,
            api_key=api_key,
            base_url=base_url,
            model=model,
            source_language=original_language,
            max_mode=max_mode,
            progress_callback=segment_progress,
        )

        # ── Step 4: LLM translation ──
        await _update_progress(db, video, VideoStatus.segmenting,
            f"正在调用 AI 翻译 ({len(segments)} 句 → {target_language})...", 70, notify)

        async def translate_progress(current: int, total: int):
            if total > 1:
                pct = 70 + int((current / total) * 20)
                await _update_progress(db, video, VideoStatus.segmenting,
                    f"正在分批翻译 ({current + 1}/{total})...", pct, notify)

        segments = await translate(
            sentences=segments,
            api_key=api_key,
            base_url=base_url,
            model=model,
            target_language=target_language,
            progress_callback=translate_progress,
        )

        # ── Step 5: Save sentences (timestamps only, no clips) ──
        await _update_progress(db, video, VideoStatus.segmenting, "正在保存结果...", 90, notify)

        for seg in segments:
            sentence = Sentence(
                video_id=video.id,
                index=seg.index,
                original_text=seg.original_text,
                translated_text=seg.translated_text,
                start_time=seg.start_time,
                end_time=seg.end_time,
                duration=round(seg.end_time - seg.start_time, 3),
            )
            db.add(sentence)

        await _update_progress(db, video, VideoStatus.completed, "处理完成", 100, notify)

    except Exception as e:
        traceback.print_exc()
        video.status = VideoStatus.failed
        video.error_message = str(e) or repr(e)
        video.progress_message = f"处理失败: {video.error_message}"
        await db.commit()
        if notify:
            await notify(video)
