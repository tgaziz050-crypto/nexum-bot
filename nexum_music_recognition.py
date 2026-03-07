"""
NEXUM — Распознавание музыки (Shazam-like).
Использует AudD API (бесплатный tier) и ACRCloud (опционально).
"""
import os
import aiohttp
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("NEXUM.music")

AUDD_API_KEY = os.getenv("AUDD_API_KEY", "")

async def recognize_music(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Распознаёт музыку по аудиофайлу.
    Возвращает: {"title": ..., "artist": ..., "album": ..., "release_date": ...}
    """
    if not AUDD_API_KEY:
        return None
    try:
        with open(audio_path, "rb") as f:
            data = f.read()
        async with aiohttp.ClientSession() as s:
            form = aiohttp.FormData()
            form.add_field("api_token", AUDD_API_KEY)
            form.add_field("file", data, filename="audio.mp3", content_type="audio/mpeg")
            async with s.post("https://api.audd.io/", data=form,
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                if isinstance(d, dict) and d.get("result"):
                    res = d["result"]
                    if isinstance(res, dict):
                        return {
                            "title": res.get("title", "?"),
                            "artist": res.get("artist", "?"),
                            "album": res.get("album", ""),
                            "release_date": res.get("release_date", ""),
                            "label": res.get("label", ""),
                        }
                    elif isinstance(res, list) and res:
                        r0 = res[0]
                        return {
                            "title": r0.get("title", "?"),
                            "artist": r0.get("artist", "?"),
                            "album": r0.get("album", ""),
                            "release_date": r0.get("release_date", ""),
                            "label": r0.get("label", ""),
                        }
    except Exception as e:
        log.warning(f"Music recognition: {e}")
    return None

def format_music_info(info: Dict[str, Any]) -> str:
    """Форматирует результат для ответа."""
    parts = []
    if info.get("title"): parts.append(f"🎵 {info['title']}")
    if info.get("artist"): parts.append(f"👤 {info['artist']}")
    if info.get("album"): parts.append(f"💿 {info['album']}")
    if info.get("release_date"): parts.append(f"📅 {info['release_date']}")
    return "\n".join(parts) if parts else "Не удалось распознать"
