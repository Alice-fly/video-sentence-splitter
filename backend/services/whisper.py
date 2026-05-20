import os
import gc
import shutil
import asyncio
import concurrent.futures
import logging
from typing import Optional

from models.schemas import SubtitleEntry
from config import OUTPUTS_DIR, FFMPEG, WHISPER_MODELS_DIR
from utils.subprocess import run_cmd

logger = logging.getLogger(__name__)


def _find_cuda_bin_dir(cuda_ver: Optional[int] = None) -> Optional[str]:
    """Search for CUDA runtime DLL directory. Returns path to bin\x64 or None.

    If cuda_ver is specified, only returns a match if that exact CUDA version's
    cublas DLL is found. Otherwise returns the first match for any CUDA version.

    Returns empty string "" if the DLL is already loadable via system PATH.
    """
    import ctypes

    if cuda_ver is not None:
        dll_names = [f"cublas64_{cuda_ver}.dll"]
    else:
        dll_names = [f"cublas64_{v}.dll" for v in range(10, 15)]

    # 0) Check pip-installed nvidia packages (e.g. nvidia-cublas-cu12)
    try:
        import sys as _sys
        for p in _sys.path:
            if "site-packages" in p or "dist-packages" in p:
                nvidia_bin = os.path.join(p, "nvidia", "cublas", "bin")
                if os.path.isdir(nvidia_bin):
                    for name in dll_names:
                        dll_path = os.path.join(nvidia_bin, name)
                        if os.path.exists(dll_path):
                            try:
                                ctypes.CDLL(dll_path)
                                return nvidia_bin
                            except OSError:
                                continue
    except Exception:
        pass

    # 1) Try loading by name (works if CUDA bin is already in PATH)
    for name in dll_names:
        try:
            ctypes.CDLL(name)
            return ""
        except OSError:
            continue

    # 2) Check CUDA_PATH / CUDA_PATH_V* environment variables
    for env_key in sorted(os.environ.keys(), reverse=True):
        if env_key.startswith("CUDA_PATH"):
            candidate = os.path.join(os.environ[env_key], "bin", "x64")
            for name in dll_names:
                try:
                    ctypes.CDLL(os.path.join(candidate, name))
                    return candidate
                except OSError:
                    continue

    # 3) Search common installation roots
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "NVIDIA GPU Computing Toolkit", "CUDA"),
        os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"),
                     "NVIDIA GPU Computing Toolkit", "CUDA"),
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
    ]

    import glob as _glob
    for root in candidates:
        pattern = os.path.join(root, "v*")
        for ver_dir in sorted(_glob.glob(pattern), reverse=True):
            bin_dir = os.path.join(ver_dir, "bin", "x64")
            if os.path.isdir(bin_dir):
                for name in dll_names:
                    if os.path.exists(os.path.join(bin_dir, name)):
                        try:
                            ctypes.CDLL(os.path.join(bin_dir, name))
                            return bin_dir
                        except OSError:
                            continue

    # 4) Targeted search: drive:\*\CUDA\bin\x64 and drive:\*\*\bin\x64
    for drive in ("C:", "D:", "E:", "F:"):
        for pattern in [os.path.join(drive, os.sep, "*", "CUDA", "bin", "x64"),
                        os.path.join(drive, os.sep, "*", "*", "bin", "x64")]:
            for d in _glob.glob(pattern):
                for name in dll_names:
                    dll_path = os.path.join(d, name)
                    if os.path.exists(dll_path):
                        try:
                            ctypes.CDLL(dll_path)
                            return d
                        except OSError:
                            continue

    return None


# CUDA version that the standard ctranslate2 pip wheel is compiled against.
# If you installed a different ctranslate2 wheel, adjust this.
_CTRANSLATE2_CUDA_VER = 12


def _cuda_dll_available() -> bool:
    """Return True if the CUDA DLL that ctranslate2 needs can be loaded."""
    result = _find_cuda_bin_dir(_CTRANSLATE2_CUDA_VER)
    return result is not None


def _build_model(model_size: str, device: str, compute_type: str):
    """Create a WhisperModel with automatic CPU fallback if CUDA libs are missing.

    Checks for CUDA DLL before the first import of ctranslate2 because its
    C extension tries to load CUDA libraries at import time. Once the import
    fails, the extension stays loaded and cannot be retried — so we must
    detect missing CUDA and set CT2_FORCE_CPU=1 *before* touching ctranslate2.
    """
    cuda_dir = None
    if device in ("auto", "cuda") and "CT2_FORCE_CPU" not in os.environ:
        cuda_dir = _find_cuda_bin_dir(_CTRANSLATE2_CUDA_VER)
        if cuda_dir is None:
            # Check if the user has CUDA installed but wrong version
            any_cuda = _find_cuda_bin_dir()
            if any_cuda is not None:
                logger.warning(
                    "检测到 CUDA 但版本不匹配 (需要 CUDA %d.x 的 cublas64_%d.dll)。已回退到 CPU。",
                    _CTRANSLATE2_CUDA_VER, _CTRANSLATE2_CUDA_VER,
                )
            else:
                logger.info("CUDA DLL 不可用，自动回退到 CPU 模式")
            os.environ["CT2_FORCE_CPU"] = "1"
            device = "cpu"
            compute_type = "int8"
        elif cuda_dir:
            logger.info("注册 CUDA DLL 目录: %s", cuda_dir)
            try:
                os.add_dll_directory(cuda_dir)
            except AttributeError:
                pass

    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device=device, compute_type=compute_type,
                        download_root=WHISPER_MODELS_DIR)


def _lang_to_whisper(lang: str) -> Optional[str]:
    """Map user-facing language code to Whisper language code.

    Returns None for 'auto' to let Whisper auto-detect.
    """
    mapping = {
        "ja": "ja",
        "jp": "ja",
        "en": "en",
        "zh": "zh",
        "ch": "zh",
    }
    return mapping.get(lang)


def _run_whisper_sync(audio_path: str, model_size: str, device: str, compute_type: str,
                      language: Optional[str], beam_size: int, vad_filter: bool,
                      progress_callback, loop) -> list[SubtitleEntry]:
    """Run Whisper transcription in a worker thread."""
    model = _build_model(model_size, device, compute_type)

    segments_gen, _info = model.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": 500} if vad_filter else None,
    )

    entries: list[SubtitleEntry] = []
    count = 0
    for segment in segments_gen:
        text = segment.text.strip()
        if not text:
            continue
        count += 1
        entries.append(SubtitleEntry(
            index=count,
            start=round(segment.start, 3),
            end=round(segment.end, 3),
            text=text,
        ))
        if progress_callback and count % 10 == 0:
            asyncio.run_coroutine_threadsafe(
                progress_callback("transcribing", count, 0),
                loop,
            )

    if progress_callback:
        asyncio.run_coroutine_threadsafe(
            progress_callback("transcribing", count, count),
            loop,
        )

    return entries


async def extract_subtitles_whisper(
    video_path: str,
    video_id: str,
    language: str = "auto",
    progress_callback=None,
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    vad_filter: bool = True,
) -> list[SubtitleEntry]:
    """Extract subtitles from video audio using Whisper speech recognition.

    1. ffmpeg extract audio to 16kHz mono WAV
    2. Load WhisperModel via faster-whisper (in thread pool)
    3. Transcribe with word timestamps + VAD filtering
    4. Convert segments to SubtitleEntry list
    """
    audio_dir = os.path.join(OUTPUTS_DIR, video_id, "_whisper_audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, "audio.wav")

    try:
        # ── Step 1: Extract audio from video ──
        if progress_callback:
            await progress_callback("extracting_audio")

        cmd = [
            FFMPEG,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-loglevel", "error",
            audio_path,
        ]
        result = await run_cmd(cmd)

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[:500] if result.stderr else "无错误输出"
            raise RuntimeError(f"ffmpeg 提取音频失败 (exit code {result.returncode}): {stderr_text}")

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise RuntimeError("提取的音频文件为空")

        # ── Step 2: Load model & transcribe (in thread pool) ──
        if progress_callback:
            await progress_callback("loading_model")

        whisper_lang = _lang_to_whisper(language)

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            entries = await loop.run_in_executor(
                executor,
                _run_whisper_sync,
                audio_path,
                model_size,
                device,
                compute_type,
                whisper_lang,
                beam_size,
                vad_filter,
                progress_callback,
                loop,
            )

        return entries

    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)
        gc.collect()


def _run_preload_sync(model_size: str, device: str, compute_type: str) -> str:
    """Download and validate a Whisper model. Returns cache path on success."""
    from huggingface_hub import snapshot_download

    repo_id = f"Systran/faster-whisper-{model_size}"

    logger.info("开始下载 Whisper 模型: %s", repo_id)
    try:
        cache_path = snapshot_download(repo_id, cache_dir=WHISPER_MODELS_DIR, resume_download=True)
    except Exception as e:
        raise RuntimeError(f"下载模型失败 ({repo_id}): {e}") from e

    logger.info("模型下载完成: %s", cache_path)

    # Validate by loading the model from local cache (no network fallback)
    _build_model(model_size, device, compute_type)

    return cache_path


async def preload_whisper_model(
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "auto",
) -> dict:
    """Download and validate a Whisper model in a thread pool.

    Returns {"success": bool, "message": str, "cache_path": str}.
    """
    loop = asyncio.get_event_loop()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            cache_path = await loop.run_in_executor(
                executor,
                _run_preload_sync,
                model_size,
                device,
                compute_type,
            )
        return {
            "success": True,
            "message": f"模型 {model_size} 已就绪",
            "cache_path": cache_path,
        }
    except Exception as e:
        logger.exception("预下载 Whisper 模型失败: %s", model_size)
        return {
            "success": False,
            "message": str(e),
        }
