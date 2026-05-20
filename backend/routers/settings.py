import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.orm import Settings as SettingsORM
from models.schemas import (
    SettingsOut, SettingsUpdate,
    CookieValidateRequest, CookieValidateResponse,
    CookieFetchRequest, CookieFetchResponse,
    WhisperPreloadRequest, WhisperPreloadResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "",
    "deepseek_max_mode": "false",
    "target_language": "中文",
    "video_quality": "720p",
    "cookies_from_browser_youtube": "",
    "cookies_text_youtube": "",
    "cookies_from_browser_bilibili": "",
    "cookies_text_bilibili": "",
    "subtitle_method": "whisper",
    "whisper_model_size": "small",
    "whisper_device": "auto",
    "whisper_compute_type": "auto",
    "whisper_beam_size": "5",
    "whisper_vad_filter": "true",
    "translate_method": "deepseek",
    "microsoft_translator_key": "",
    "microsoft_translator_region": "eastasia",
}


async def _get_merged_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(SettingsORM))
    rows = result.scalars().all()
    data = {r.key: r.value for r in rows}
    merged = {**DEFAULT_SETTINGS, **data}
    # Convert bool-typed keys from stored strings
    if "deepseek_max_mode" in merged:
        merged["deepseek_max_mode"] = merged["deepseek_max_mode"] in ("true", "True", "1")
    if "whisper_vad_filter" in merged:
        merged["whisper_vad_filter"] = merged["whisper_vad_filter"] in ("true", "True", "1")
    if "whisper_beam_size" in merged:
        try:
            merged["whisper_beam_size"] = int(merged["whisper_beam_size"])
        except (ValueError, TypeError):
            merged["whisper_beam_size"] = 5
    return merged


@router.get("", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    merged = await _get_merged_settings(db)
    return SettingsOut(**merged)


@router.put("", response_model=SettingsOut)
async def update_settings(body: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    # Convert bool/int fields to string for KV storage
    if "deepseek_max_mode" in updates:
        updates["deepseek_max_mode"] = "true" if updates["deepseek_max_mode"] else "false"
    if "whisper_vad_filter" in updates:
        updates["whisper_vad_filter"] = "true" if updates["whisper_vad_filter"] else "false"
    if "whisper_beam_size" in updates:
        updates["whisper_beam_size"] = str(updates["whisper_beam_size"])
    for key, value in updates.items():
        result = await db.execute(select(SettingsORM).where(SettingsORM.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(SettingsORM(key=key, value=value))
    await db.commit()

    merged = await _get_merged_settings(db)
    return SettingsOut(**merged)


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)):
    """Fetch available models from the configured API (OpenAI-compatible)."""
    merged = await _get_merged_settings(db)
    api_key = merged.get("deepseek_api_key", "")
    base_url = merged.get("deepseek_base_url", "https://api.deepseek.com")

    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key")

    url = f"{base_url.rstrip('/')}/models"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"模型列表获取失败 (HTTP {resp.status_code})")

        data = resp.json()

    models = [m["id"] for m in data.get("data", [])]
    models.sort()
    return {"models": models}


@router.post("/validate-cookies", response_model=CookieValidateResponse)
async def validate_cookies(body: CookieValidateRequest):
    """Test whether configured cookies can access the target platform."""
    from services.fetcher import validate_cookies as _validate

    result = await _validate(
        platform=body.platform,
        browser=body.browser,
        cookies_text=body.cookies_text,
    )
    return CookieValidateResponse(**result)


@router.post("/fetch-cookies", response_model=CookieFetchResponse)
async def fetch_cookies(body: CookieFetchRequest):
    """Extract cookies from browser for the target platform."""
    from services.fetcher import extract_cookies_from_browser as _extract

    result = await _extract(
        browser=body.browser,
        platform=body.platform,
    )
    return CookieFetchResponse(**result)


@router.post("/preload-whisper-model", response_model=WhisperPreloadResponse)
async def preload_whisper_model_endpoint(body: WhisperPreloadRequest):
    """Pre-download and validate a Whisper model so it's ready before processing."""
    from services.whisper import preload_whisper_model
    try:
        result = await preload_whisper_model(
            model_size=body.model_size,
            device=body.device,
            compute_type=body.compute_type,
        )
        return WhisperPreloadResponse(**result)
    except Exception as e:
        return WhisperPreloadResponse(success=False, message=str(e))


@router.get("/check-gpu")
async def check_gpu():
    """Check whether CUDA GPU is available for Whisper (faster-whisper/ctranslate2)."""
    from services.whisper import _find_cuda_bin_dir, _CTRANSLATE2_CUDA_VER
    import os

    # Check for the exact version ctranslate2 needs
    cuda_dir = _find_cuda_bin_dir(_CTRANSLATE2_CUDA_VER)
    cublas_ok = cuda_dir is not None
    can_use_cuda = cublas_ok and "CT2_FORCE_CPU" not in os.environ

    # Also check what CUDA versions are actually installed
    installed_versions = []
    for ver in range(10, 15):
        if _find_cuda_bin_dir(ver) is not None:
            installed_versions.append(ver)

    detail = ""
    if not cublas_ok:
        if installed_versions:
            detail = (
                f"检测到 CUDA {installed_versions}，但 ctranslate2 需要 CUDA {_CTRANSLATE2_CUDA_VER}.x "
                f"(cublas64_{_CTRANSLATE2_CUDA_VER}.dll)。"
                f"请安装 CUDA {_CTRANSLATE2_CUDA_VER} Toolkit 运行时。"
            )
        else:
            detail = (
                "未检测到 CUDA 运行时 (cublas64_*.dll)。"
                "如需 GPU 加速，请安装 NVIDIA CUDA Toolkit 并确保 bin/x64 目录在 PATH 中。"
            )
    elif "CT2_FORCE_CPU" in os.environ:
        detail = "已设置 CT2_FORCE_CPU 环境变量，强制使用 CPU。"
        can_use_cuda = False
    else:
        loc = cuda_dir or "PATH"
        detail = f"CUDA {_CTRANSLATE2_CUDA_VER}.x 运行时已检测到 (位置: {loc})，Whisper 可使用 GPU 加速。"

    return {
        "cuda_available": cublas_ok,
        "can_use_cuda": can_use_cuda,
        "cuda_detail": detail,
        "required_cuda_ver": _CTRANSLATE2_CUDA_VER,
        "installed_versions": installed_versions,
        "recommendation": "cuda" if can_use_cuda else "cpu",
    }


@router.post("/install-cuda-runtime")
async def install_cuda_runtime():
    """Install nvidia-cublas-cu12 into the program's python/Lib/site-packages."""
    import subprocess
    import sys
    import os
    from config import ROOT_DIR

    target = os.path.join(ROOT_DIR, "python", "Lib", "site-packages")
    os.makedirs(target, exist_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target=" + target, "nvidia-cublas-cu12"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return {"success": True, "message": f"CUDA 运行库已安装到 {target}"}
        else:
            return {"success": False, "message": result.stderr[-500:] or result.stdout[-500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "安装超时，请检查网络后重试"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/whisper-cached-models")
async def get_cached_whisper_models():
    """List Whisper models that are already downloaded in the project directory."""
    import os
    import glob
    from config import WHISPER_MODELS_DIR

    cached = {}
    pattern = os.path.join(WHISPER_MODELS_DIR, "models--Systran--faster-whisper-*")
    for path in glob.glob(pattern):
        dirname = os.path.basename(path)
        # Extract model size from "models--Systran--faster-whisper-{size}"
        prefix = "models--Systran--faster-whisper-"
        if dirname.startswith(prefix):
            size = dirname[len(prefix):]
            # Get the snapshot dir to verify model files exist
            snapshots_dir = os.path.join(path, "snapshots")
            has_files = False
            if os.path.isdir(snapshots_dir):
                for item in os.listdir(snapshots_dir):
                    item_path = os.path.join(snapshots_dir, item)
                    if os.path.isdir(item_path) and os.listdir(item_path):
                        has_files = True
                        break
            cached[size] = {
                "path": path,
                "has_files": has_files,
            }

    return {"cached": cached, "models_dir": WHISPER_MODELS_DIR}
