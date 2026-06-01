import os
import re
import tempfile
from config import SUBTITLES_DIR, VIDEOS_DIR, FFMPEG


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:120]


def _is_netscape_format(text: str) -> bool:
    """Check if the text looks like Netscape-format cookies (tab-separated lines)."""
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line and len(line.split("\t")) >= 7:
            return True
    return False


def _detect_cookie_domain(url: str) -> str:
    """Detect the cookie domain from a video URL."""
    if "youtube.com" in url or "youtu.be" in url:
        return ".youtube.com"
    if "bilibili.com" in url:
        return ".bilibili.com"
    return ""


def _detect_platform(url: str) -> str:
    """Detect platform from a video URL. Returns 'youtube', 'bilibili', or ''."""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "bilibili.com" in url:
        return "bilibili"
    return ""


def _get_cookie_test_url(platform: str) -> str:
    """Return a known public video URL for cookie validation."""
    if platform == "youtube":
        return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    if platform == "bilibili":
        return "https://www.bilibili.com/video/BV1GJ411x7h7"
    return ""


def _apply_cookie_options(
    ydl_opts: dict,
    cookies_text: str = "",
    cookies_from_browser: str = "",
    platform: str = "",
) -> str | None:
    """Apply cookie options to ydl_opts. Returns temp file path if created, or None."""
    if cookies_text:
        if not _is_netscape_format(cookies_text):
            cookies_text = _convert_raw_to_netscape(cookies_text, platform)
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        temp_file.write(cookies_text)
        temp_file.close()
        ydl_opts["cookiefile"] = temp_file.name
        return temp_file.name
    elif cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return None


def _convert_raw_to_netscape(text: str, platform: str = "") -> str:
    """Convert raw cookie text to Netscape format.

    Supports multiple input formats:
    - Cookie request header:  key1=val1; key2=val2
    - One per line:           key1=val1  (newline)  key2=val2
    - Raw cookie string:      any mix of semicolons and newlines
    """
    lines = ["# Netscape HTTP Cookie File"]

    # Split by both semicolons and newlines
    pairs = []
    for segment in text.strip().replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        for part in segment.split(";"):
            part = part.strip()
            if part and "=" in part:
                pairs.append(part)

    # Deduplicate by cookie name
    seen: set[str] = set()
    domain = _guess_domain(text, platform)

    for pair in pairs:
        name, _, value = pair.partition("=")
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())

        if name.lower().startswith("cookie: "):
            # Accidentally included header prefix
            name = name[8:]
        if name.startswith("Cookie: "):
            name = name[8:]

        if domain:
            lines.append(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
        else:
            lines.append(f"TRUE\t/\tFALSE\t0\t{name}\t{value}")

    return "\n".join(lines)


def _guess_domain(text: str, platform: str = "") -> str:
    """Guess the cookie domain from cookie names or platform hint."""
    text_lower = text.lower()
    if "bili_jct" in text_lower or "sessdata" in text_lower or "dedeuserid" in text_lower:
        return ".bilibili.com"
    if "sapisid" in text_lower or "hsid" in text_lower or "visitor_info" in text_lower:
        return ".youtube.com"
    if platform == "bilibili":
        return ".bilibili.com"
    if platform == "youtube":
        return ".youtube.com"
    return ""


async def fetch_video_info(
    url: str,
    video_id: str,
    quality: str = "720p",
    cookies_from_browser: str = "",
    cookies_text: str = "",
    trim_start: float | None = None,
    trim_end: float | None = None,
):
    """
    Download video to local cache, merge audio+video, extract subtitles.
    Returns (local_video_path, subtitle_path, title, thumbnail, duration).
    """
    import yt_dlp

    safe_title = sanitize_filename(video_id)
    sub_output_path = os.path.join(SUBTITLES_DIR, f"{safe_title}")
    video_output_path = os.path.join(VIDEOS_DIR, f"{video_id}.mp4")

    height_limit = int(quality.rstrip("p")) if quality.rstrip("p").isdigit() else 720

    ydl_opts = {
        # Download to local fixed path
        "outtmpl": video_output_path,
        # Merge best video + best audio into mp4 container
        "format": f"bestvideo[height<={height_limit}]+bestaudio/best",
        "merge_output_format": "mp4",
        # Move moov atom to front for seeking support
        "postprocessor_args": {
            "ffmpeg": ["-movflags", "+faststart"],
        },
        # Subtitles
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ja", "en", "zh-Hans", "zh-Hant", "ko"],
        "ignoreerrors": True,
        "subtitlesformat": "vtt",
        "outtmpl_subtitles": sub_output_path,
        "quiet": False,
        "no_warnings": False,
        "ffmpeg_location": os.path.dirname(FFMPEG),
        # Required by yt-dlp ≥2026 for YouTube: JS runtime + challenge solver
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }

    # Apply video trimming (download_ranges) if both start and end are specified
    if trim_start is not None and trim_end is not None:
        ydl_opts["download_ranges"] = lambda info, ydl: [
            {"start_time": trim_start, "end_time": trim_end}
        ]

    _temp_cookie_file = _apply_cookie_options(ydl_opts, cookies_text, cookies_from_browser, _detect_platform(url))

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info is None:
                raise RuntimeError(
                    f"yt-dlp 无法提取视频信息，请检查链接是否有效或 Cookies 是否过期。"
                    f" 链接: {url}"
                )

            title = info.get("title", "Untitled")
            thumbnail_url = info.get("thumbnail", "") or ""
            # Bilibili thumbnails are http:// — upgrade to https://
            if thumbnail_url.startswith("http://"):
                thumbnail_url = thumbnail_url.replace("http://", "https://", 1)

            # Download thumbnail to local storage
            thumbnail_local = ""
            if thumbnail_url:
                import httpx
                thumb_path = os.path.join(VIDEOS_DIR, f"{video_id}_thumb.jpg")
                try:
                    resp = httpx.get(thumbnail_url, timeout=30.0, follow_redirects=True)
                    if resp.status_code == 200 and len(resp.content) > 0:
                        with open(thumb_path, "wb") as f:
                            f.write(resp.content)
                        thumbnail_local = thumb_path
                except Exception:
                    pass  # Thumbnail is non-critical; keep URL if download fails

            thumbnail = thumbnail_local or thumbnail_url
            duration = float(info.get("duration", 0))

            # Verify downloaded file exists
            if not os.path.exists(video_output_path):
                raise RuntimeError(f"视频下载失败，文件未生成: {video_output_path}")

            # Find downloaded subtitle file — yt-dlp ≥2026 may write subs alongside the video
            subtitle_path = ""
            for search_dir in (SUBTITLES_DIR, VIDEOS_DIR):
                try:
                    for f in os.listdir(search_dir):
                        if f.startswith(safe_title) and (f.endswith(".vtt") or f.endswith(".srt")):
                            subtitle_path = os.path.join(search_dir, f)
                            break
                except FileNotFoundError:
                    continue
                if subtitle_path:
                    break

        return video_output_path, subtitle_path, title, thumbnail, duration
    finally:
        if _temp_cookie_file:
            os.unlink(_temp_cookie_file)


async def validate_cookies(
    platform: str,
    browser: str | None = None,
    cookies_text: str | None = None,
) -> dict:
    """Test whether cookies can access a known video page on the given platform."""
    import yt_dlp

    test_url = _get_cookie_test_url(platform)
    if not test_url:
        return {"success": False, "message": f"不支持的平台: {platform}"}

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }

    temp_file = _apply_cookie_options(
        ydl_opts,
        cookies_text or "",
        browser or "",
        platform,
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            if info is None:
                return {"success": False, "message": "无法访问视频页面，Cookies 可能已失效"}
            title = info.get("title", "Unknown")
            return {
                "success": True,
                "message": "Cookies 有效",
                "details": f"成功获取视频信息: {title}",
            }
    except Exception as e:
        msg = str(e)
        if "cookie" in msg.lower() or "login" in msg.lower() or "sign in" in msg.lower():
            return {"success": False, "message": "Cookies 已失效或未登录，请重新获取"}
        return {"success": False, "message": f"验证失败: {msg[:200]}"}
    finally:
        if temp_file:
            os.unlink(temp_file)


async def extract_cookies_from_browser(browser: str, platform: str) -> dict:
    """Extract cookies from browser for the given platform and return Netscape text."""
    import yt_dlp

    test_url = _get_cookie_test_url(platform)
    if not test_url:
        return {"success": False, "message": f"不支持的平台: {platform}"}

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiesfrombrowser": (browser,),
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(test_url, download=False)
            cookiejar = ydl.cookiejar

        # Serialize to Netscape format
        netscape_lines = ["# Netscape HTTP Cookie File"]
        cookie_count = 0
        domains: set[str] = set()
        for cookie in cookiejar:
            domain = cookie.domain or ""
            if domain:
                domains.add(domain.lstrip("."))
            line = "\t".join([
                domain if domain else "",
                "TRUE" if domain.startswith(".") else "FALSE",
                cookie.path or "/",
                "TRUE" if cookie.secure else "FALSE",
                str(cookie.expires) if cookie.expires else "0",
                cookie.name or "",
                cookie.value or "",
            ])
            netscape_lines.append(line)
            cookie_count += 1

        if cookie_count == 0:
            return {
                "success": False,
                "message": f"未能从 {browser} 浏览器中读取到 {platform} 相关 cookies，请确认浏览器已登录对应网站",
            }

        return {
            "success": True,
            "message": f"成功从 {browser} 提取 {cookie_count} 个 cookie，覆盖 {len(domains)} 个域名",
            "cookies_text": "\n".join(netscape_lines),
            "cookie_count": cookie_count,
            "domains": sorted(domains),
        }
    except Exception as e:
        msg = str(e)
        if browser.lower() in ("chrome", "edge"):
            hint = f"{browser} 基于 Chromium 内核，cookie 存储经过系统级加密，yt-dlp 无法解密。请手动粘贴 cookies 文本，或使用 Firefox 等非 Chromium 浏览器。"
        else:
            hint = f"请确认 {browser} 浏览器已安装且未运行（部分浏览器运行时会锁定 cookie 文件）。"
        return {"success": False, "message": f"提取失败: {msg[:200]}\n{hint}"}
