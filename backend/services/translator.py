"""Alternative translation backends: Microsoft Translator, Google Translate.

Each function accepts a list of {index, original_text} dicts and returns
a list of {index, translated_text} dicts. Chunking is handled internally
to respect per-request character limits.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Common helpers ──

def _chunk_sentences(sentences: list[dict], max_chars: int) -> list[list[dict]]:
    """Split sentences into chunks where each chunk's total text ≤ max_chars."""
    chunks = []
    current: list[dict] = []
    current_len = 0
    for s in sentences:
        text = s.get("original_text", "")
        if current and current_len + len(text) > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(s)
        current_len += len(text)
    if current:
        chunks.append(current)
    return chunks


def _lang_to_ms(lang: str) -> str:
    """Map user-facing language to Microsoft Translator language code."""
    mapping = {
        "中文": "zh-Hans", "chinese": "zh-Hans", "zh": "zh-Hans",
        "日语": "ja", "japanese": "ja", "ja": "ja",
        "英语": "en", "english": "en", "en": "en",
        "韩语": "ko", "korean": "ko", "ko": "ko",
        "法语": "fr", "french": "fr", "fr": "fr",
        "德语": "de", "german": "de", "de": "de",
        "西班牙语": "es", "spanish": "es", "es": "es",
    }
    return mapping.get(lang, lang)


def _lang_to_google(lang: str) -> str:
    """Map user-facing language to Google Translate language code."""
    mapping = {
        "中文": "zh-CN", "chinese": "zh-CN", "zh": "zh-CN",
        "日语": "ja", "japanese": "ja", "ja": "ja",
        "英语": "en", "english": "en", "en": "en",
        "韩语": "ko", "korean": "ko", "ko": "ko",
        "法语": "fr", "french": "fr", "fr": "fr",
        "德语": "de", "german": "de", "de": "de",
        "西班牙语": "es", "spanish": "es", "es": "es",
    }
    return mapping.get(lang, lang)


# ── Microsoft Translator ──

_MICROSOFT_MAX_CHARS = 4500  # Safety margin under the 5000 limit
_MICROSOFT_ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0"


def _translate_ms_sync(sentences: list[dict], api_key: str, region: str,
                       target_lang: str) -> list[dict]:
    """Synchronous Microsoft Translator call (run in thread)."""
    import httpx

    to_lang = _lang_to_ms(target_lang)

    chunks = _chunk_sentences(sentences, _MICROSOFT_MAX_CHARS)
    results: list[dict] = []

    for chunk in chunks:
        body = [{"text": s["original_text"]} for s in chunk]
        url = f"{_MICROSOFT_ENDPOINT}&to={to_lang}"
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Ocp-Apim-Subscription-Region": region,
            "Content-Type": "application/json",
        }

        resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Microsoft Translator error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        for i, item in enumerate(data):
            translated = item["translations"][0]["text"]
            results.append({
                "index": chunk[i]["index"],
                "translated_text": translated,
            })

    return results


async def translate_microsoft(sentences: list[dict], api_key: str, region: str,
                              target_lang: str) -> list[dict]:
    """Translate via Microsoft Translator (Azure Cognitive Services)."""
    return await asyncio.to_thread(_translate_ms_sync, sentences, api_key, region, target_lang)


# ── Google Translate (free web API via deep-translator) ──

_GOOGLE_MAX_CHARS = 4500


def _translate_google_sync(sentences: list[dict], target_lang: str) -> list[dict]:
    """Synchronous Google Translate call (run in thread)."""
    from deep_translator import GoogleTranslator

    to_lang = _lang_to_google(target_lang)

    chunks = _chunk_sentences(sentences, _GOOGLE_MAX_CHARS)
    results: list[dict] = []

    for chunk in chunks:
        texts = [s["original_text"] for s in chunk]
        try:
            translated = GoogleTranslator(source="auto", target=to_lang).translate_batch(texts)
        except Exception as e:
            # Fall back to individual translation if batch fails
            logger.warning("Google batch translate failed, trying individually: %s", e)
            translated = []
            for text in texts:
                try:
                    t = GoogleTranslator(source="auto", target=to_lang).translate(text)
                    translated.append(t)
                except Exception as e2:
                    logger.error("Google translate failed for text: %s", e2)
                    translated.append(text)  # Keep original on failure

        for i, text in enumerate(translated):
            results.append({
                "index": chunk[i]["index"],
                "translated_text": text,
            })

    return results


async def translate_google(sentences: list[dict], target_lang: str) -> list[dict]:
    """Translate via Google Translate (free web API)."""
    return await asyncio.to_thread(_translate_google_sync, sentences, target_lang)
