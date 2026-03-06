"""
NEXUM — Распознавание музыки (Shazam-like). AudD API.
"""
import os
import aiohttp
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("NEXUM.music")
AUDD_API_KEY = os.getenv("AUDD_API_KEY", "")

async def recognize_music(audio_path: str) -> Optional[Dict[str, Any]]:
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
                    r0 = res if isinstance(res, dict) else (res[0] if isinstance(res, list) and res else None)
                    if r0:
                        return {
                            "title": r0.get("title", "?"),
                            "artist": r0.get("artist", "?"),
                            "album": r0.get("album", ""),
                            "release_date": r0.get("release_date", ""),
                        }
    except Exception as e:
        log.warning(f"Music: {e}")
    return None

def format_music_info(info: Dict[str, Any]) -> str:
    parts = []
    if info.get("title"): parts.append(f"🎵 {info['title']}")
    if info.get("artist"): parts.append(f"👤 {info['artist']}")
    if info.get("album"): parts.append(f"💿 {info['album']}")
    return "\n".join(parts) if parts else "Не распознано"
