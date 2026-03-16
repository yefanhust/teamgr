"""TTS (Text-to-Speech) service — shared logic for edge-tts generation and caching."""

import asyncio
import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

_TTS_CACHE_DIR = os.path.join(
    os.environ.get("TEAMGR_DATA_DIR", "/app/data"),
    "scholar-tts-cache",
)
os.makedirs(_TTS_CACHE_DIR, exist_ok=True)

_TTS_VOICE = "zh-CN-YunxiNeural"
_TTS_RATE = "+10%"


def strip_markdown(text: str) -> str:
    """Remove markdown formatting for cleaner TTS output."""
    text = re.sub(
        r'\n(?:Sources|References|参考来源|来源|资料来源)\s*[:：]?\s*\n[\s\S]*$',
        '', text, flags=re.I,
    )
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'\|[^\n]+\|', '', text)
    text = re.sub(r'^[-*]{3,}$', '', text, flags=re.M)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.M)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.M)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_tts_cache_path(text: str) -> str:
    """Return the cache file path for a given text (by content hash)."""
    clean_text = strip_markdown(text)
    text_hash = hashlib.md5(clean_text.encode()).hexdigest()
    return os.path.join(_TTS_CACHE_DIR, f"{text_hash}.mp3")


async def _generate_tts_async(clean_text: str, cache_path: str) -> str:
    """Generate TTS audio file using edge-tts (async). Returns cache_path."""
    import edge_tts

    communicate = edge_tts.Communicate(clean_text, _TTS_VOICE, rate=_TTS_RATE)
    try:
        await communicate.save(cache_path)
    except Exception as e:
        if os.path.exists(cache_path):
            os.remove(cache_path)
        raise e
    return cache_path


async def generate_tts_cache_async(answer: str) -> str | None:
    """Generate and cache TTS for the given answer text (async version).

    Returns the cache path if successful, None otherwise.
    Skips generation if already cached.
    """
    if not answer or not answer.strip():
        return None

    clean_text = strip_markdown(answer)
    text_hash = hashlib.md5(clean_text.encode()).hexdigest()
    cache_path = os.path.join(_TTS_CACHE_DIR, f"{text_hash}.mp3")

    if os.path.exists(cache_path):
        return cache_path

    try:
        await _generate_tts_async(clean_text, cache_path)
        logger.info(f"TTS pre-generated: {cache_path}")
        return cache_path
    except Exception as e:
        logger.error(f"TTS pre-generation failed: {e}")
        return None


def generate_tts_cache_sync(answer: str) -> str | None:
    """Generate and cache TTS for the given answer text (sync version for cron jobs).

    Returns the cache path if successful, None otherwise.
    """
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(generate_tts_cache_async(answer))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"TTS sync generation failed: {e}")
        return None
