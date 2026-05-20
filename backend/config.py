import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Application root: <exe_dir>/ for PyInstaller, or parent of backend/ for dev
if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(BASE_DIR)

SUBTITLES_DIR = os.path.join(ROOT_DIR, "subtitles")
OUTPUTS_DIR = os.path.join(ROOT_DIR, "outputs")
DATA_DIR = os.path.join(ROOT_DIR, "data")
VIDEOS_DIR = os.path.join(DATA_DIR, "videos")

WHISPER_MODELS_DIR = os.path.join(DATA_DIR, "whisper_models")

for d in [SUBTITLES_DIR, OUTPUTS_DIR, DATA_DIR, VIDEOS_DIR, WHISPER_MODELS_DIR]:
    os.makedirs(d, exist_ok=True)


def _find_ffmpeg() -> str:
    """Find ffmpeg: bundled copy first, then PATH, then common install locations."""
    bundled = os.path.join(ROOT_DIR, "bin", "ffmpeg.exe")
    if os.path.exists(bundled):
        return bundled

    exe = shutil.which("ffmpeg")
    if exe:
        return exe

    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%ProgramData%\chocolatey\bin\ffmpeg.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\shims\ffmpeg.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.realpath(path)
    return "ffmpeg"


FFMPEG = _find_ffmpeg()


def _find_node() -> str:
    """Find node.exe: bundled copy first, then PATH, then common install locations."""
    bundled = os.path.join(ROOT_DIR, "bin", "node", "node.exe")
    if os.path.exists(bundled):
        return bundled

    exe = shutil.which("node")
    if exe:
        return exe

    candidates = [
        os.path.expandvars(r"%ProgramFiles%\nodejs\node.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\nodejs\node.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\node.exe"),
        os.path.expandvars(r"%ProgramData%\chocolatey\bin\node.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\shims\node.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.realpath(path)
    return "node"


NODE = _find_node()

# Prepend bundled node directory to PATH so yt-dlp can spawn node as a subprocess
_node_dir = os.path.dirname(NODE)
if os.path.isdir(_node_dir) and _node_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _node_dir + os.pathsep + os.environ.get("PATH", "")
