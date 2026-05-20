import re
from models.schemas import SubtitleEntry


def parse_vtt(content: str) -> list[SubtitleEntry]:
    """Parse .vtt file content into SubtitleEntry list."""
    entries: list[SubtitleEntry] = []
    blocks = re.split(r"\n\s*\n", content.strip())
    idx = 0

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        # Match timestamp line: 00:00:00.000 --> 00:00:02.500
        time_match = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not time_match:
            continue

        start = _ts_to_seconds(time_match.group(1))
        end = _ts_to_seconds(time_match.group(2))

        # Text is everything after the timestamp line (skip optional cue id line before timestamp)
        text_lines: list[str] = []
        found_timestamp = False
        for line in lines:
            if re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}", line):
                found_timestamp = True
                continue
            if found_timestamp and line.strip():
                # Strip VTT tags like <c> <00:00:01.000>
                clean = re.sub(r"<[^>]+>", "", line)
                text_lines.append(clean.strip())

        text = " ".join(text_lines).strip()
        if not text:
            continue

        idx += 1
        entries.append(SubtitleEntry(index=idx, start=start, end=end, text=text))

    return entries


def parse_srt(content: str) -> list[SubtitleEntry]:
    """Parse .srt file content into SubtitleEntry list."""
    entries: list[SubtitleEntry] = []
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # Line 0: index number (ignore), Line 1: timestamp
        time_match = re.search(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})",
            lines[1],
        )
        if not time_match:
            continue

        start = _ts_to_seconds(time_match.group(1))
        end = _ts_to_seconds(time_match.group(2))

        # Text is lines 2+ (until the block ends); strip SRT tags
        text_lines: list[str] = []
        for line in lines[2:]:
            clean = re.sub(r"<[^>]+>", "", line)
            if clean.strip():
                text_lines.append(clean.strip())

        text = " ".join(text_lines).strip()
        if not text:
            continue

        entries.append(SubtitleEntry(
            index=int(lines[0].strip()),
            start=start,
            end=end,
            text=text,
        ))

    return entries


def _ts_to_seconds(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
