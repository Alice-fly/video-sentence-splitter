import json
import logging
import re
from collections.abc import Awaitable
from typing import Callable, Optional
import httpx
from openai import AsyncOpenAI
from models.schemas import SubtitleEntry, SentenceSegment
from prompts.segmentation import get_system_prompt, get_user_prompt
from prompts.translation import get_translate_system_prompt, get_translate_user_prompt
from utils.token_counter import (
    estimate_tokens, CONTEXT_LIMIT, SAFETY_RATIO, MIN_OUTPUT_RESERVE,
    MAX_CONTEXT_LIMIT, MAX_TOKENS, DEFAULT_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


# ── JSON parsing ──────────────────────────────────────────────────────

def _extract_json_array(raw: str) -> list:
    """Extract JSON array from LLM response, fixing common formatting issues."""

    # Strip markdown code fences
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    # Find JSON array boundaries
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fix 1: Remove trailing comma before closing bracket
    fixed = re.sub(r",\s*\]", "]", raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Fix 2: Truncated response — trim to last complete object, close array
    if not raw.rstrip().endswith("]"):
        last_brace = raw.rfind("}")
        if last_brace != -1:
            trimmed = raw[:last_brace + 1].rstrip()
            if trimmed.endswith(","):
                trimmed = trimmed[:-1].rstrip()
            fixed = trimmed + "\n]"
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        # Fallback: count brackets properly and close
        obj_depth = 0
        arr_depth = 0
        in_string = False
        escape = False
        for ch in raw:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                obj_depth += 1
            elif ch == '}':
                obj_depth = max(0, obj_depth - 1)
            elif ch == '[':
                arr_depth += 1
            elif ch == ']':
                arr_depth = max(0, arr_depth - 1)
        if obj_depth > 0 or arr_depth > 0:
            fixed = raw + "}" * obj_depth + "]" * arr_depth
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # Fix 3: Extract balanced {}-objects (handles multi-line JSON)
    objects = []
    i = 0
    while i < len(raw):
        if raw[i] == '{':
            obj_start = i
            depth = 0
            in_str = False
            esc = False
            j = i
            while j < len(raw):
                c = raw[j]
                if esc:
                    esc = False
                    j += 1
                    continue
                if c == '\\':
                    esc = True
                    j += 1
                    continue
                if c == '"':
                    in_str = not in_str
                    j += 1
                    continue
                if in_str:
                    j += 1
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            objects.append(json.loads(raw[obj_start:j + 1]))
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
                j += 1
            else:
                i += 1  # unbalanced, skip past this {
        else:
            i += 1

    if objects:
        return objects

    # Fix 4: Split on "},{", rebuild valid objects
    parts = re.split(r'\}\s*,\s*\{', raw)
    valid_parts = []
    for k, part in enumerate(parts):
        if k == 0 and not part.strip().startswith('{'):
            part = '{' + part
        if k == len(parts) - 1 and not part.strip().endswith('}'):
            part = part + '}'
        try:
            json.loads(part)
            valid_parts.append(part)
        except json.JSONDecodeError:
            continue
    if valid_parts:
        rebuilt = '[' + ','.join(valid_parts) + ']'
        try:
            return json.loads(rebuilt)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法解析 LLM 返回的 JSON。原始响应前 500 字符:\n{raw[:500]}")


# ── Text similarity ───────────────────────────────────────────────────

def _text_similarity(a: str, b: str) -> float:
    """Jaccard similarity via character bigrams. 0.0–1.0."""
    def bigrams(s: str) -> set:
        s = s.strip().lower()
        if len(s) < 2:
            return {s}
        return {s[i:i + 2] for i in range(len(s) - 1)}
    set_a = bigrams(a)
    set_b = bigrams(b)
    set_a.discard("")
    set_b.discard("")
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ── Chunking ──────────────────────────────────────────────────────────

def _split_into_chunks(
    entries: list[SubtitleEntry],
    system_prompt: str,
    user_prompt_template: str,
    context_limit: int = CONTEXT_LIMIT,
    overlap: int = 3,
) -> list[list[SubtitleEntry]]:
    """Split entries into overlapping chunks sized to fit context window."""
    if not entries:
        return [[]]

    prompt_overhead_tokens = estimate_tokens(system_prompt + user_prompt_template)
    available_input_tokens = int(context_limit * SAFETY_RATIO) - prompt_overhead_tokens - MIN_OUTPUT_RESERVE
    available_input_chars = int(available_input_tokens / 0.5)

    # Estimate avg chars per entry from first 20
    sample = entries[:20]
    sample_json = json.dumps(
        [{"index": e.index, "start": e.start, "end": e.end, "text": e.text}
         for e in sample],
        ensure_ascii=False,
    )
    avg_entry_chars = len(sample_json) / len(sample)

    target_chars_per_chunk = int(available_input_chars * 0.85)
    entries_per_chunk = max(10, int(target_chars_per_chunk / avg_entry_chars))

    if entries_per_chunk >= len(entries):
        return [entries]

    effective_overlap = min(overlap, entries_per_chunk - 1)

    chunks = []
    start = 0
    while start < len(entries):
        end = min(start + entries_per_chunk, len(entries))
        chunks.append(entries[start:end])
        if end >= len(entries):
            break
        start = end - effective_overlap

    return chunks


def _merge_chunked_results(
    all_segments: list[SentenceSegment],
    overlap_seconds: float = 1.0,
    similarity_threshold: float = 0.7,
) -> list[SentenceSegment]:
    """Merge segments from multiple chunks, deduplicating overlaps."""
    if not all_segments:
        return []

    sorted_segs = sorted(all_segments, key=lambda s: (s.start_time, s.end_time))

    merged: list[SentenceSegment] = []
    for seg in sorted_segs:
        if not merged:
            merged.append(seg)
            continue

        prev = merged[-1]
        if abs(seg.start_time - prev.start_time) < overlap_seconds:
            sim = _text_similarity(seg.original_text, prev.original_text)
            if sim > similarity_threshold:
                if len(seg.original_text) > len(prev.original_text):
                    merged[-1] = seg
                continue

        merged.append(seg)

    for i, seg in enumerate(merged):
        seg.index = i + 1

    return merged


# ── Segment step ──────────────────────────────────────────────────────

async def _segment_one_chunk(
    client: AsyncOpenAI,
    model: str,
    system_prompt: str,
    entries_chunk: list[SubtitleEntry],
    max_tokens: int = 65536,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> tuple[list[SentenceSegment], dict]:
    """Send one chunk to the LLM for segmentation only (no translation)."""
    entries_json = json.dumps(
        [{"index": e.index, "start": e.start, "end": e.end, "text": e.text}
         for e in entries_chunk],
        ensure_ascii=False,
    )
    user_prompt = get_user_prompt(entries_json)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )

    raw = response.choices[0].message.content or ""
    finish = response.choices[0].finish_reason or "unknown"

    diag = {
        "finish_reason": finish,
        "raw_length": len(raw),
        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
        "completion_tokens": response.usage.completion_tokens if response.usage else None,
    }

    prefix = f"[Segment Chunk {chunk_index + 1}/{total_chunks}] " if total_chunks > 1 else "[Segment] "
    logger.info(
        "%sLLM call: model=%s, finish_reason=%s, raw_length=%d chars, "
        "prompt_tokens=%s, completion_tokens=%s",
        prefix, model, finish, len(raw),
        diag["prompt_tokens"], diag["completion_tokens"],
    )

    data = _extract_json_array(raw)
    logger.info(
        "%sParsed %d items from response (%d input entries)",
        prefix, len(data), len(entries_chunk),
    )

    results: list[SentenceSegment] = []
    for item in data:
        try:
            results.append(SentenceSegment(
                index=item["index"],
                original_text=item["original_text"],
                translated_text="",
                start_time=item["start_time"],
                end_time=item["end_time"],
            ))
        except (KeyError, TypeError):
            continue

    logger.info(
        "%sValid segments: %d (skipped %d invalid)",
        prefix, len(results), len(data) - len(results),
    )

    if finish == "length":
        logger.warning(
            "%sfinish_reason='length' — response may be truncated. "
            "Got %d segments from %d entries. "
            "completion_tokens=%s vs max_tokens=%d",
            prefix, len(results), len(entries_chunk), diag["completion_tokens"], max_tokens,
        )

    return results, diag


# ── Translate step ────────────────────────────────────────────────────

async def _translate_one_chunk(
    client: AsyncOpenAI,
    model: str,
    target_language: str,
    sentences: list[SentenceSegment],
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> tuple[dict[int, str], dict]:
    """Send one chunk to the LLM for translation only.

    Returns (index->translated_text mapping, diagnostics_dict).
    """
    system_prompt = get_translate_system_prompt(target_language)
    sentences_json = json.dumps(
        [{"index": s.index, "original_text": s.original_text} for s in sentences],
        ensure_ascii=False,
    )
    user_prompt = get_translate_user_prompt(sentences_json, target_language)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=65536,
    )

    raw = response.choices[0].message.content or ""
    finish = response.choices[0].finish_reason or "unknown"

    diag = {
        "finish_reason": finish,
        "raw_length": len(raw),
        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
        "completion_tokens": response.usage.completion_tokens if response.usage else None,
    }

    prefix = f"[Translate Chunk {chunk_index + 1}/{total_chunks}] " if total_chunks > 1 else "[Translate] "
    logger.info(
        "%sLLM call: model=%s, finish_reason=%s, raw_length=%d chars, "
        "prompt_tokens=%s, completion_tokens=%s",
        prefix, model, finish, len(raw),
        diag["prompt_tokens"], diag["completion_tokens"],
    )

    data = _extract_json_array(raw)
    mapping: dict[int, str] = {}
    for item in data:
        try:
            idx = int(item["index"])
            mapping[idx] = item["translated_text"]
        except (KeyError, TypeError, ValueError):
            continue

    logger.info(
        "%sTranslated %d sentences (skipped %d invalid)",
        prefix, len(mapping), len(data) - len(mapping),
    )

    return mapping, diag


# ── Public API ────────────────────────────────────────────────────────

async def segment(
    entries: list[SubtitleEntry],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "",
    source_language: str = "auto",
    max_mode: bool = False,
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> list[SentenceSegment]:
    """Segment subtitle entries into semantic sentences via LLM (no translation).

    Long videos are automatically split into overlapping chunks to stay
    within the model's context window. Results are merged and deduplicated.
    """
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=httpx.AsyncClient())
    system_prompt = get_system_prompt(source_language=source_language)

    effective_context = MAX_CONTEXT_LIMIT if max_mode else CONTEXT_LIMIT
    effective_max_tokens = MAX_TOKENS if max_mode else DEFAULT_MAX_TOKENS

    logger.info(
        "Segment: max_mode=%s, context_limit=%d, max_tokens=%d, entries=%d",
        max_mode, effective_context, effective_max_tokens, len(entries),
    )

    entries_json = json.dumps(
        [{"index": e.index, "start": e.start, "end": e.end, "text": e.text}
         for e in entries],
        ensure_ascii=False,
    )
    user_prompt_template = get_user_prompt("")

    estimated_input_tokens = (
        estimate_tokens(system_prompt)
        + estimate_tokens(user_prompt_template)
        + estimate_tokens(entries_json)
    )
    safe_input_limit = int(effective_context * SAFETY_RATIO) - MIN_OUTPUT_RESERVE

    logger.info(
        "Token estimate: input=%d, safe_limit=%d, entries=%d, context=%d",
        estimated_input_tokens, safe_input_limit, len(entries), effective_context,
    )

    if estimated_input_tokens > safe_input_limit:
        chunks = _split_into_chunks(
            entries, system_prompt, user_prompt_template,
            context_limit=effective_context,
        )
        logger.info(
            "Chunking: %d entries → %d chunks (~%d entries/chunk)",
            len(entries), len(chunks), len(chunks[0]) if chunks else 0,
        )

        all_segments: list[SentenceSegment] = []
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            if progress_callback:
                await progress_callback(i, total_chunks)
            segments, _diag = await _segment_one_chunk(
                client, model, system_prompt, chunk,
                max_tokens=effective_max_tokens,
                chunk_index=i, total_chunks=total_chunks,
            )
            all_segments.extend(segments)

        results = _merge_chunked_results(all_segments)
        logger.info(
            "Merged %d raw segments → %d after dedup",
            len(all_segments), len(results),
        )
    else:
        if progress_callback:
            await progress_callback(0, 1)
        results, _diag = await _segment_one_chunk(
            client, model, system_prompt, entries,
            max_tokens=effective_max_tokens,
        )

    if not results:
        raise ValueError(
            f"LLM 未能生成任何有效句子。共 {len(entries)} 条字幕输入。"
            f"请检查 API Key、模型可用性或源语言设置。"
        )

    logger.info("Segment: %d sentences from %d subtitle entries", len(results), len(entries))
    return results


async def translate(
    sentences: list[SentenceSegment],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "",
    target_language: str = "中文",
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> list[SentenceSegment]:
    """Translate segmented sentences to the target language via LLM.

    Each sentence's translated_text field is populated. Sentences can be
    processed in chunks if there are many of them.
    """
    if not sentences:
        return sentences

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=httpx.AsyncClient())
    logger.info("Translate: %d sentences → %s", len(sentences), target_language)

    # Translate in batches of up to 100 sentences to keep response manageable
    CHUNK_SIZE = 100
    if len(sentences) <= CHUNK_SIZE:
        mapping, _diag = await _translate_one_chunk(
            client, model, target_language, sentences,
        )
        for s in sentences:
            s.translated_text = mapping.get(s.index, "")
    else:
        total_chunks = (len(sentences) + CHUNK_SIZE - 1) // CHUNK_SIZE
        for i in range(0, len(sentences), CHUNK_SIZE):
            chunk = sentences[i:i + CHUNK_SIZE]
            chunk_idx = i // CHUNK_SIZE
            if progress_callback:
                await progress_callback(chunk_idx, total_chunks)
            mapping, _diag = await _translate_one_chunk(
                client, model, target_language, chunk,
                chunk_index=chunk_idx, total_chunks=total_chunks,
            )
            for s in chunk:
                s.translated_text = mapping.get(s.index, "")

    missing = sum(1 for s in sentences if not s.translated_text)
    if missing:
        logger.warning("Translate: %d sentences have empty translation", missing)

    logger.info("Translate: completed %d sentences", len(sentences))
    return sentences
