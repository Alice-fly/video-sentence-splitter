from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


# ── Subtitle ──
class SubtitleEntry(BaseModel):
    index: int
    start: float
    end: float
    text: str


# ── LLM 断句输入 ──
class SegmentInput(BaseModel):
    index: int
    start: float
    end: float
    text: str


# ── LLM 返回 ──
class SentenceSegment(BaseModel):
    index: int
    original_text: str
    translated_text: str
    start_time: float
    end_time: float


# ── Category ──
class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None
    sort_order: int = 0


class CategoryOut(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    sort_order: int
    created_at: datetime
    children: list["CategoryOut"] = []

    class Config:
        from_attributes = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None


# ── Video ──
class VideoAddRequest(BaseModel):
    url: str = ""
    source_type: Literal["youtube", "bilibili", "local_file"] = "youtube"
    category_id: Optional[str] = None
    original_language: Literal["auto", "ja", "en", "zh"] = "auto"
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None


class VideoOut(BaseModel):
    id: str
    url: str
    title: str
    thumbnail: Optional[str] = None
    category_id: Optional[str] = None
    status: str
    progress: int
    progress_message: str
    original_language: str
    error_message: Optional[str] = None
    duration: Optional[float] = None
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None
    stream_url: Optional[str] = None
    local_video_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sentence_count: int = 0
    # Per-step status
    source_type: Optional[str] = None
    import_status: str = "not_started"
    import_progress: int = 0
    import_progress_message: str = ""
    import_error_message: Optional[str] = None
    subtitle_status: str = "not_started"
    subtitle_method: Optional[str] = None
    subtitle_progress: int = 0
    subtitle_progress_message: str = ""
    subtitle_error_message: Optional[str] = None
    segment_status: str = "not_started"
    segment_progress: int = 0
    segment_progress_message: str = ""
    segment_error_message: Optional[str] = None
    translate_status: str = "not_started"
    translate_progress: int = 0
    translate_progress_message: str = ""
    translate_error_message: Optional[str] = None

    class Config:
        from_attributes = True


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    category_id: Optional[str] = None
    original_language: Optional[Literal["auto", "ja", "en", "zh"]] = None


# ── Sentence ──
class SentenceOut(BaseModel):
    id: str
    video_id: str
    index: int
    original_text: str
    translated_text: str
    start_time: float
    end_time: float
    duration: Optional[float] = None
    edited_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SentenceUpdate(BaseModel):
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class SentenceCreate(BaseModel):
    index: int
    original_text: str = ""
    translated_text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0


# ── Raw Subtitle ──
class RawSubtitleOut(BaseModel):
    id: str
    index: int
    start_time: float
    end_time: float
    text: str

    class Config:
        from_attributes = True


# ── Import triggers ──
class ImportStart(BaseModel):
    url: str = ""
    original_language: str = "auto"
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None


# ── Settings ──
class SettingsOut(BaseModel):
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = ""
    deepseek_max_mode: bool = False
    target_language: str = "chinese"
    video_quality: str = "720p"
    cookies_from_browser_youtube: str = ""
    cookies_text_youtube: str = ""
    cookies_from_browser_bilibili: str = ""
    cookies_text_bilibili: str = ""
    # Whisper settings
    subtitle_method: str = "whisper"
    whisper_model_size: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_beam_size: int = 5
    whisper_vad_filter: bool = True
    # Translation
    translate_method: str = "deepseek"
    microsoft_translator_key: str = ""
    microsoft_translator_region: str = "eastasia"


class SettingsUpdate(BaseModel):
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: Optional[str] = None
    deepseek_model: Optional[str] = None
    deepseek_max_mode: Optional[bool] = None
    target_language: Optional[str] = None
    video_quality: Optional[str] = None
    cookies_from_browser_youtube: Optional[str] = None
    cookies_text_youtube: Optional[str] = None
    cookies_from_browser_bilibili: Optional[str] = None
    cookies_text_bilibili: Optional[str] = None
    # Whisper settings
    subtitle_method: Optional[str] = None
    whisper_model_size: Optional[str] = None
    whisper_device: Optional[str] = None
    whisper_compute_type: Optional[str] = None
    whisper_beam_size: Optional[int] = None
    whisper_vad_filter: Optional[bool] = None
    # Translation
    translate_method: Optional[str] = None
    microsoft_translator_key: Optional[str] = None
    microsoft_translator_region: Optional[str] = None


# ── Cookie validation ──
class CookieValidateRequest(BaseModel):
    platform: Literal["youtube", "bilibili"]
    browser: Optional[str] = None
    cookies_text: Optional[str] = None


class CookieValidateResponse(BaseModel):
    success: bool
    message: str
    details: Optional[str] = None


class CookieFetchRequest(BaseModel):
    browser: str
    platform: Literal["youtube", "bilibili"]


class CookieFetchResponse(BaseModel):
    success: bool
    message: str
    cookies_text: Optional[str] = None
    cookie_count: int = 0
    domains: list[str] = []


# ── Whisper preload ──
class WhisperPreloadRequest(BaseModel):
    model_size: str = "small"
    device: str = "auto"
    compute_type: str = "auto"


class WhisperPreloadResponse(BaseModel):
    success: bool
    message: str
    cache_path: str = ""


# ── Generic ──
class MessageOut(BaseModel):
    message: str
