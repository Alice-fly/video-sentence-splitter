import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base
import enum


class VideoStatus(str, enum.Enum):
    pending = "pending"
    fetching = "fetching"
    subtitle_extracting = "subtitle_extracting"
    segmenting = "segmenting"
    completed = "completed"
    failed = "failed"


def gen_uuid():
    return str(uuid.uuid4())


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    videos = relationship("Video", back_populates="category", lazy="selectin")
    children = relationship("Category", lazy="selectin")


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=gen_uuid)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False, default="")
    thumbnail = Column(Text, nullable=True)
    category_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(VideoStatus), default=VideoStatus.pending, nullable=False)
    progress = Column(Integer, default=0)
    progress_message = Column(Text, default="")
    original_language = Column(String, default="auto")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    stream_url = Column(Text, nullable=True)
    local_video_path = Column(Text, nullable=True)
    subtitle_path = Column(Text, nullable=True)
    duration = Column(Float, nullable=True)
    trim_start = Column(Float, nullable=True)
    trim_end = Column(Float, nullable=True)

    # ── Per-step tracking ──
    source_type = Column(String, nullable=True)
    uploaded_filename = Column(Text, nullable=True)

    import_status = Column(String, default="not_started")
    import_progress = Column(Integer, default=0)
    import_progress_message = Column(Text, default="")
    import_error_message = Column(Text, nullable=True)

    subtitle_status = Column(String, default="not_started")
    subtitle_method = Column(String, nullable=True)
    subtitle_progress = Column(Integer, default=0)
    subtitle_progress_message = Column(Text, default="")
    subtitle_error_message = Column(Text, nullable=True)

    segment_status = Column(String, default="not_started")
    segment_progress = Column(Integer, default=0)
    segment_progress_message = Column(Text, default="")
    segment_error_message = Column(Text, nullable=True)

    translate_status = Column(String, default="not_started")
    translate_progress = Column(Integer, default=0)
    translate_progress_message = Column(Text, default="")
    translate_error_message = Column(Text, nullable=True)

    category = relationship("Category", back_populates="videos")
    sentences = relationship("Sentence", back_populates="video", cascade="all, delete-orphan", lazy="selectin")
    raw_subtitles = relationship("RawSubtitle", back_populates="video", cascade="all, delete-orphan", lazy="selectin")

    def compute_legacy_status(self):
        """Derive legacy monolithic status from per-step states.
        Falls back to the old status column if no per-step state is set (backward compat)."""
        all_steps = (self.import_status, self.subtitle_status, self.segment_status, self.translate_status)
        if all(s in (None, "not_started") for s in all_steps):
            # No per-step state — fall back to legacy status column
            return self.status.value if self.status else "pending"

        if self.import_status == "not_started":
            return "pending"
        if self.import_status == "processing":
            return "fetching"
        if self.import_status == "failed":
            return "failed"
        if self.subtitle_status == "not_started":
            return "fetching"
        if self.subtitle_status == "processing":
            return "subtitle_extracting"
        if self.subtitle_status == "failed":
            return "failed"
        if self.segment_status == "not_started":
            return "subtitle_extracting"
        if self.segment_status == "processing":
            return "segmenting"
        if self.segment_status == "failed":
            return "failed"
        if self.translate_status == "not_started":
            return "segmenting"
        if self.translate_status == "processing":
            return "segmenting"
        if self.translate_status == "failed":
            return "failed"
        return "completed"

    def compute_legacy_progress(self):
        """Weighted overall progress from per-step states.
        Falls back to the old progress column if no per-step state is set."""
        all_steps = (self.import_status, self.subtitle_status, self.segment_status, self.translate_status)
        if all(s in (None, "not_started") for s in all_steps):
            return self.progress or 0

        weights = {
            "import": (0, 25),
            "subtitle": (25, 50),
            "segment": (50, 75),
            "translate": (75, 100),
        }
        steps = [
            ("import", self.import_status, self.import_progress),
            ("subtitle", self.subtitle_status, self.subtitle_progress),
            ("segment", self.segment_status, self.segment_progress),
            ("translate", self.translate_status, self.translate_progress),
        ]
        overall = 0
        for step_name, status, progress in steps:
            lo, hi = weights[step_name]
            if status == "completed":
                overall = hi
            elif status == "processing":
                overall = lo + (hi - lo) * (progress / 100)
                break
            elif status == "failed":
                overall = lo
                break
            elif status == "not_started":
                break
        return int(overall)


class Sentence(Base):
    __tablename__ = "sentences"

    id = Column(String, primary_key=True, default=gen_uuid)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    index = Column(Integer, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=True)
    edited_at = Column(DateTime, nullable=True)

    video = relationship("Video", back_populates="sentences")


class RawSubtitle(Base):
    __tablename__ = "raw_subtitles"

    id = Column(String, primary_key=True, default=gen_uuid)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)

    video = relationship("Video", back_populates="raw_subtitles")


class Settings(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
