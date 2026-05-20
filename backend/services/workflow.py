"""Per-step workflow functions — each independently triggerable by its router."""

import asyncio
import traceback
import logging
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.orm import Video, Sentence, RawSubtitle, Settings
from services.fetcher import fetch_video_info, _detect_platform
from services.segmenter import segment, translate
from services.whisper import extract_subtitles_whisper
from utils.subtitle_parser import parse_vtt, parse_srt

logger = logging.getLogger(__name__)


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(Settings).where(Settings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def _get_all_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(Settings))
    rows = result.scalars().all()
    return {r.key: r.value for r in rows}


async def _update_step(
    db: AsyncSession,
    video: Video,
    step: str,
    status: str,
    message: str,
    progress: int,
    notify: Optional[Callable] = None,
):
    """Update a specific step's status fields on the Video row."""
    setattr(video, f"{step}_status", status)
    setattr(video, f"{step}_progress", progress)
    setattr(video, f"{step}_progress_message", message)
    video.progress_message = message
    await db.commit()
    await db.refresh(video)
    if notify:
        await notify(video, step)


async def run_import_youtube(
    video_id: str,
    url: str,
    language: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Download a YouTube video via yt-dlp."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    video.source_type = "youtube"
    video.import_status = "processing"
    video.progress_message = "正在下载 YouTube 视频..."
    await db.commit()

    try:
        video_quality = await _get_setting(db, "video_quality", "720p")
        cookies_from_browser = await _get_setting(db, "cookies_from_browser_youtube", "")
        cookies_text = await _get_setting(db, "cookies_text_youtube", "")

        await _update_step(db, video, "import", "processing", "正在下载视频...", 10, notify)

        local_video_path, subtitle_path, title, thumbnail, duration = await fetch_video_info(
            url, video_id, quality=video_quality,
            cookies_from_browser=cookies_from_browser,
            cookies_text=cookies_text,
        )

        video.title = title or "Untitled"
        video.thumbnail = thumbnail
        video.stream_url = local_video_path
        video.local_video_path = local_video_path
        video.subtitle_path = subtitle_path or ""
        video.duration = duration
        video.original_language = language

        # If yt-dlp found embedded subtitles, mark subtitle step as completed
        if subtitle_path:
            video.subtitle_status = "completed"
            video.subtitle_method = "embedded"
            video.subtitle_progress = 100
            video.subtitle_progress_message = "内嵌字幕已提取"

        await _update_step(db, video, "import", "completed", "视频下载完成", 100, notify)

    except Exception as e:
        logger.exception("YouTube import failed for %s", video_id)
        video.import_status = "failed"
        video.import_error_message = str(e)
        video.error_message = str(e)
        video.progress_message = f"下载失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "import")
        raise


async def run_import_bilibili(
    video_id: str,
    url: str,
    language: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Download a Bilibili video via yt-dlp."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    video.source_type = "bilibili"
    video.import_status = "processing"
    video.progress_message = "正在下载 B站视频..."
    await db.commit()

    try:
        video_quality = await _get_setting(db, "video_quality", "720p")
        cookies_from_browser = await _get_setting(db, "cookies_from_browser_bilibili", "")
        cookies_text = await _get_setting(db, "cookies_text_bilibili", "")

        await _update_step(db, video, "import", "processing", "正在下载视频...", 10, notify)

        local_video_path, subtitle_path, title, thumbnail, duration = await fetch_video_info(
            url, video_id, quality=video_quality,
            cookies_from_browser=cookies_from_browser,
            cookies_text=cookies_text,
        )

        video.title = title or "Untitled"
        video.thumbnail = thumbnail
        video.stream_url = local_video_path
        video.local_video_path = local_video_path
        video.subtitle_path = subtitle_path or ""
        video.duration = duration
        video.original_language = language

        if subtitle_path:
            video.subtitle_status = "completed"
            video.subtitle_method = "embedded"
            video.subtitle_progress = 100
            video.subtitle_progress_message = "内嵌字幕已提取"

        await _update_step(db, video, "import", "completed", "视频下载完成", 100, notify)

    except Exception as e:
        logger.exception("Bilibili import failed for %s", video_id)
        video.import_status = "failed"
        video.import_error_message = str(e)
        video.error_message = str(e)
        video.progress_message = f"下载失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "import")
        raise


async def run_subtitle_whisper(
    video_id: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Run Whisper ASR and store raw subtitle entries.

    Whisper recognition runs in a thread pool (via asyncio.to_thread) and
    receives NO database session.  All DB work happens in the main async
    function after the thread returns pure data.
    """
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    if not video.local_video_path or video.import_status != "completed":
        raise ValueError("请先完成视频导入")

    video.subtitle_status = "processing"
    video.subtitle_method = "whisper"
    await db.commit()

    try:
        whisper_model_size = await _get_setting(db, "whisper_model_size", "small")
        whisper_device = await _get_setting(db, "whisper_device", "auto")
        whisper_compute_type = await _get_setting(db, "whisper_compute_type", "auto")
        whisper_beam_size_str = await _get_setting(db, "whisper_beam_size", "5")
        try:
            whisper_beam_size = int(whisper_beam_size_str)
        except (ValueError, TypeError):
            whisper_beam_size = 5
        whisper_vad_filter = await _get_setting(db, "whisper_vad_filter", "true") in ("true", "True", "1")
        whisper_language = video.original_language or "auto"

        await _update_step(db, video, "subtitle", "processing", "正在 Whisper 语音识别...", 5, notify)
        await db.commit()

        # ── Run Whisper in thread pool — NO db session passed ──
        entries = await asyncio.to_thread(
            _run_whisper_thread,
            video_path=video.local_video_path,
            video_id=video_id,
            model_size=whisper_model_size,
            device=whisper_device,
            compute_type=whisper_compute_type,
            language=whisper_language,
            beam_size=whisper_beam_size,
            vad_filter=whisper_vad_filter,
        )

        if not entries:
            raise ValueError("Whisper 未能识别到任何语音内容")

        # ── All DB writes happen here in the main async thread ──
        await _clear_raw_subtitles(db, video_id)
        await db.commit()
        for e in entries:
            db.add(RawSubtitle(
                video_id=video_id,
                index=e["index"],
                start_time=e["start_time"],
                end_time=e["end_time"],
                text=e["text"],
            ))

        await _update_step(db, video, "subtitle", "completed",
            f"Whisper 识别完成 ({len(entries)} 条)", 100, notify)

    except Exception as e:
        logger.exception("Whisper subtitle failed for %s", video_id)
        video.subtitle_status = "failed"
        video.subtitle_error_message = str(e)
        video.progress_message = f"字幕提取失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "subtitle")
        raise


def _run_whisper_thread(
    video_path: str,
    video_id: str,
    model_size: str,
    device: str,
    compute_type: str,
    language: str,
    beam_size: int,
    vad_filter: bool,
) -> list[dict]:
    """Synchronous wrapper called via asyncio.to_thread.

    Runs ffmpeg audio extraction + faster-whisper transcription in a
    thread pool.  Returns a list of plain dicts — NO database access.
    """
    import subprocess
    import os
    import tempfile
    from config import FFMPEG, OUTPUTS_DIR

    audio_dir = os.path.join(OUTPUTS_DIR, video_id, "_whisper_audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, "audio.wav")

    # ── Step 1: ffmpeg extract audio ──
    ffmpeg_cmd = [
        FFMPEG, "-y", "-i", video_path, "-vn",
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        "-loglevel", "error", audio_path,
    ]
    proc = subprocess.run(ffmpeg_cmd, capture_output=True)
    if proc.returncode != 0:
        stderr_text = proc.stderr.decode("utf-8", errors="replace")[:500] if proc.stderr else "no output"
        raise RuntimeError(f"ffmpeg audio extraction failed (code {proc.returncode}): {stderr_text}")
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError("Extracted audio file is empty")

    # ── Step 2: faster-whisper transcribe ──
    _lang_map = {"ja": "ja", "jp": "ja", "en": "en", "zh": "zh", "ch": "zh"}
    whisper_lang = _lang_map.get(language, None) if language != "auto" else None

    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        audio_path,
        language=whisper_lang,
        beam_size=beam_size,
        vad_filter=vad_filter,
        word_timestamps=False,
    )

    entries = []
    idx = 0
    for seg in segments:
        entries.append({
            "index": idx,
            "start_time": round(seg.start, 3),
            "end_time": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        idx += 1

    # Clean up temp audio
    try:
        os.remove(audio_path)
        os.rmdir(audio_dir)
    except OSError:
        pass

    return entries


async def run_subtitle_embedded(
    video_id: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Parse embedded subtitles from yt-dlp's extracted file."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    if not video.subtitle_path:
        raise ValueError("没有可用的内嵌字幕文件")

    try:
        await _update_step(db, video, "subtitle", "processing", "正在读取字幕文件...", 50, notify)

        with open(video.subtitle_path, "r", encoding="utf-8") as f:
            content = f.read()

        if video.subtitle_path.endswith(".vtt"):
            entries = parse_vtt(content)
        else:
            entries = parse_srt(content)

        if not entries:
            raise ValueError("字幕文件内容为空")

        await _clear_raw_subtitles(db, video_id)
        await db.commit()
        for e in entries:
            db.add(RawSubtitle(
                video_id=video_id,
                index=e.index,
                start_time=e.start,
                end_time=e.end,
                text=e.text,
            ))

        await _update_step(db, video, "subtitle", "completed",
            f"字幕已解析 ({len(entries)} 条)", 100, notify)

    except Exception as e:
        logger.exception("Embedded subtitle parse failed for %s", video_id)
        video.subtitle_status = "failed"
        video.subtitle_error_message = str(e)
        video.progress_message = f"字幕解析失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "subtitle")
        raise


async def run_segment(
    video_id: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Run LLM semantic segmentation on raw subtitles, produce Sentence rows."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    if video.subtitle_status != "completed":
        raise ValueError("请先完成字幕提取")

    # Load raw subtitles
    raw_result = await db.execute(
        select(RawSubtitle).where(RawSubtitle.video_id == video_id).order_by(RawSubtitle.index)
    )
    raw_entries = raw_result.scalars().all()

    if not raw_entries:
        raise ValueError("没有可用的字幕条目进行断句")

    from models.schemas import SubtitleEntry
    entries = [
        SubtitleEntry(index=r.index, start=r.start_time, end=r.end_time, text=r.text)
        for r in raw_entries
    ]

    video.segment_status = "processing"
    await db.commit()

    try:
        settings = await _get_all_settings(db)
        api_key = settings.get("deepseek_api_key", "")
        base_url = settings.get("deepseek_base_url", "https://api.deepseek.com")
        model = settings.get("deepseek_model", "")
        max_mode = settings.get("deepseek_max_mode", "false") in ("true", "True", "1")

        if not api_key:
            raise ValueError("请先在设置页面配置 DeepSeek API Key")
        if not model:
            raise ValueError("请先在设置页面检测并选择模型")

        entry_count = len(entries)
        await _update_step(db, video, "segment", "processing",
            f"正在调用 AI 语义断句 ({entry_count} 条字幕)...", 10, notify)

        async def seg_progress(current: int, total: int):
            if total > 1:
                pct = 10 + int((current / total) * 85)
                await _update_step(db, video, "segment", "processing",
                    f"AI 断句中 ({current + 1}/{total})...", pct, notify)

        segments = await segment(
            entries=entries,
            api_key=api_key,
            base_url=base_url,
            model=model,
            source_language=video.original_language or "auto",
            max_mode=max_mode,
            progress_callback=seg_progress,
        )

        # Delete old sentences, save new ones
        old = await db.execute(select(Sentence).where(Sentence.video_id == video_id))
        for s in old.scalars().all():
            await db.delete(s)

        for seg in segments:
            db.add(Sentence(
                video_id=video_id,
                index=seg.index,
                original_text=seg.original_text,
                translated_text=seg.translated_text,
                start_time=seg.start_time,
                end_time=seg.end_time,
                duration=round(seg.end_time - seg.start_time, 3),
            ))

        video.translate_status = "not_started"
        await _update_step(db, video, "segment", "completed",
            f"断句完成 ({len(segments)} 句)", 100, notify)

    except Exception as e:
        logger.exception("Segmentation failed for %s", video_id)
        video.segment_status = "failed"
        video.segment_error_message = str(e)
        video.progress_message = f"断句失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "segment")
        raise


async def run_translate(
    video_id: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
    method: Optional[str] = None,
):
    """Run translation on existing Sentence rows. Dispatches to configured method."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    if video.segment_status != "completed":
        raise ValueError("请先完成断句")

    sent_result = await db.execute(
        select(Sentence).where(Sentence.video_id == video_id).order_by(Sentence.index)
    )
    sentences = sent_result.scalars().all()

    if not sentences:
        raise ValueError("没有可用的句子进行翻译")

    # Build simple dict list for translation
    sent_dicts = [
        {"index": s.index, "original_text": s.original_text}
        for s in sentences
    ]

    video.translate_status = "processing"
    await db.commit()

    try:
        settings = await _get_all_settings(db)
        target_language = settings.get("target_language", "中文")

        # Determine which translation method to use
        translate_method = method or settings.get("translate_method", "deepseek")

        await _update_step(db, video, "translate", "processing",
            f"正在翻译 ({translate_method}, {len(sent_dicts)} 句 → {target_language})...", 5, notify)

        if translate_method == "microsoft":
            ms_key = settings.get("microsoft_translator_key", "")
            ms_region = settings.get("microsoft_translator_region", "eastasia")
            if not ms_key:
                raise ValueError("请先在设置页面配置 Microsoft Translator API Key")
            from services.translator import translate_microsoft
            translated = await translate_microsoft(sent_dicts, ms_key, ms_region, target_language)

        elif translate_method == "google":
            from services.translator import translate_google
            await _update_step(db, video, "translate", "processing",
                f"正在 Google 翻译 ({len(sent_dicts)} 句)...", 10, notify)
            translated = await translate_google(sent_dicts, target_language)

        else:
            # deepseek (default LLM)
            from models.schemas import SentenceSegment
            segments = [
                SentenceSegment(
                    index=s.index,
                    original_text=s.original_text,
                    translated_text=s.translated_text,
                    start_time=s.start_time,
                    end_time=s.end_time,
                )
                for s in sentences
            ]

            api_key = settings.get("deepseek_api_key", "")
            base_url = settings.get("deepseek_base_url", "https://api.deepseek.com")
            model = settings.get("deepseek_model", "")
            max_mode = settings.get("deepseek_max_mode", "false") in ("true", "True", "1")

            if not api_key:
                raise ValueError("请先在设置页面配置 DeepSeek API Key")
            if not model:
                raise ValueError("请先在设置页面检测并选择模型")

            async def trans_progress(current: int, total: int):
                if total > 1:
                    pct = 10 + int((current / total) * 85)
                    await _update_step(db, video, "translate", "processing",
                        f"LLM 翻译中 ({current + 1}/{total})...", pct, notify)

            translated = await translate(
                sentences=segments,
                api_key=api_key,
                base_url=base_url,
                model=model,
                target_language=target_language,
                progress_callback=trans_progress,
            )

        # Update translations in place
        for t in translated:
            idx = t["index"] if isinstance(t, dict) else t.index
            text = t["translated_text"] if isinstance(t, dict) else t.translated_text
            stmt = select(Sentence).where(Sentence.video_id == video_id, Sentence.index == idx)
            r = await db.execute(stmt)
            s = r.scalar_one_or_none()
            if s and text:
                s.translated_text = text

        await _update_step(db, video, "translate", "completed",
            f"翻译完成 ({len(translated)} 句)", 100, notify)

    except Exception as e:
        logger.exception("Translation failed for %s", video_id)
        video.translate_status = "failed"
        video.translate_error_message = str(e)
        video.progress_message = f"翻译失败: {e}"
        await db.commit()
        if notify:
            await notify(video, "translate")
        raise


async def run_full_pipeline(
    video_id: str,
    url: str,
    language: str,
    db: AsyncSession,
    notify: Optional[Callable] = None,
):
    """Chain all steps: import → subtitle → segment → translate."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one()

    # Determine source type from URL
    platform = _detect_platform(url)
    if platform == "youtube":
        await run_import_youtube(video_id, url, language, db, notify)
    elif platform == "bilibili":
        await run_import_bilibili(video_id, url, language, db, notify)
    else:
        raise ValueError(f"不支持的视频链接: {url}")

    await db.refresh(video)

    # Subtitle step
    if video.subtitle_path:
        await run_subtitle_embedded(video_id, db, notify)
    else:
        await run_subtitle_whisper(video_id, db, notify)

    await db.refresh(video)

    # Segment
    await run_segment(video_id, db, notify)
    await db.refresh(video)

    # Translate
    await run_translate(video_id, db, notify)


async def _clear_raw_subtitles(db: AsyncSession, video_id: str):
    """Delete all raw subtitle entries for a video."""
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(RawSubtitle).where(RawSubtitle.video_id == video_id))
