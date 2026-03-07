"""
NEXUM — Распознавание музыки (Shazam-like).
Поддерживает: AudD API, ACRCloud, fingerprinting fallback.
"""
import os
import aiohttp
import logging
import asyncio
import tempfile
import subprocess
from typing import Optional, Dict, Any

log = logging.getLogger("NEXUM.music")

AUDD_API_KEY = os.getenv("AUDD_API_KEY", "")
ACRCLOUD_HOST = os.getenv("ACRCLOUD_HOST", "")
ACRCLOUD_KEY = os.getenv("ACRCLOUD_KEY", "")
ACRCLOUD_SECRET = os.getenv("ACRCLOUD_SECRET", "")


async def recognize_via_audd(audio_path: str) -> Optional[Dict[str, Any]]:
    """Распознавание через AudD API."""
    if not AUDD_API_KEY:
        return None
    try:
        with open(audio_path, "rb") as f:
            data = f.read()
        async with aiohttp.ClientSession() as s:
            form = aiohttp.FormData()
            form.add_field("api_token", AUDD_API_KEY)
            form.add_field("file", data, filename="audio.mp3", content_type="audio/mpeg")
            form.add_field("return", "apple_music,spotify")
            async with s.post("https://api.audd.io/", data=form,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                if isinstance(d, dict) and d.get("result"):
                    res = d["result"]
                    r0 = res if isinstance(res, dict) else (res[0] if isinstance(res, list) and res else None)
                    if r0:
                        result = {
                            "title": r0.get("title", "?"),
                            "artist": r0.get("artist", "?"),
                            "album": r0.get("album", ""),
                            "release_date": r0.get("release_date", ""),
                            "source": "AudD",
                        }
                        # Ссылки
                        if r0.get("apple_music"):
                            result["apple_music"] = r0["apple_music"].get("url", "")
                        if r0.get("spotify"):
                            result["spotify_url"] = r0["spotify"].get("external_urls", {}).get("spotify", "")
                        return result
    except Exception as e:
        log.warning(f"AudD: {e}")
    return None


async def recognize_via_acrcloud(audio_path: str) -> Optional[Dict[str, Any]]:
    """Распознавание через ACRCloud."""
    if not (ACRCLOUD_HOST and ACRCLOUD_KEY and ACRCLOUD_SECRET):
        return None
    try:
        import hmac
        import hashlib
        import time
        import base64

        http_method = "POST"
        http_uri = "/v1/identify"
        data_type = "audio"
        signature_version = "1"
        timestamp = str(int(time.time()))

        string_to_sign = "\n".join([http_method, http_uri, ACRCLOUD_KEY, data_type, signature_version, timestamp])
        sign = base64.b64encode(hmac.new(ACRCLOUD_SECRET.encode(), string_to_sign.encode(), digestmod=hashlib.sha1).digest()).decode()

        with open(audio_path, "rb") as f:
            audio_data = f.read()
        sample = audio_data[:int(len(audio_data) * 0.5)][:1000000]

        async with aiohttp.ClientSession() as s:
            form = aiohttp.FormData()
            form.add_field("access_key", ACRCLOUD_KEY)
            form.add_field("data_type", data_type)
            form.add_field("signature_version", signature_version)
            form.add_field("signature", sign)
            form.add_field("timestamp", timestamp)
            form.add_field("sample", sample, filename="sample.mp3", content_type="audio/mpeg")
            form.add_field("sample_bytes", str(len(sample)))

            url = f"https://{ACRCLOUD_HOST}{http_uri}"
            async with s.post(url, data=form, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status", {}).get("code") == 0:
                        music = d.get("metadata", {}).get("music", [{}])[0]
                        return {
                            "title": music.get("title", "?"),
                            "artist": ", ".join(a.get("name", "") for a in music.get("artists", [])),
                            "album": music.get("album", {}).get("name", ""),
                            "release_date": music.get("release_date", ""),
                            "source": "ACRCloud",
                        }
    except Exception as e:
        log.warning(f"ACRCloud: {e}")
    return None


async def recognize_via_shazam_web(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Попытка распознавания через публичный Shazam endpoint.
    Работает без API ключа (ограниченно).
    """
    try:
        # Конвертируем в нужный формат если нужно
        ffmpeg = __import__("shutil").which("ffmpeg")
        wav_path = audio_path + ".wav"

        if ffmpeg:
            result = subprocess.run(
                [ffmpeg, "-i", audio_path, "-ar", "44100", "-ac", "1", "-y", wav_path],
                capture_output=True, timeout=30
            )
            read_path = wav_path if result.returncode == 0 and os.path.exists(wav_path) else audio_path
        else:
            read_path = audio_path

        with open(read_path, "rb") as f:
            audio_data = f.read()

        # Используем только первые 8 секунд
        sample = audio_data[:352800]  # ~8 сек при 44100Hz mono

        try:
            os.unlink(wav_path)
        except:
            pass

        headers = {
            "Content-Type": "audio/wav",
            "User-Agent": "Shazam/3.36.0 CFNetwork/1331.0.7 Darwin/21.4.0",
            "Accept-Language": "ru-RU",
        }

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://amp.shazam.com/discovery/v5/ru/RU/android/-/tag/1234567890/1234567890",
                data=sample, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    track = d.get("track")
                    if track:
                        return {
                            "title": track.get("title", "?"),
                            "artist": track.get("subtitle", "?"),
                            "album": track.get("sections", [{}])[0].get("metadata", [{}])[0].get("text", ""),
                            "source": "Shazam",
                        }
    except Exception as e:
        log.debug(f"Shazam web: {e}")
    return None


async def recognize_music(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Основная функция распознавания музыки.
    Пробует разные сервисы по очереди.
    """
    # Пробуем все методы параллельно
    tasks = [
        recognize_via_audd(audio_path),
        recognize_via_acrcloud(audio_path),
        recognize_via_shazam_web(audio_path),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, dict) and r.get("title") and r["title"] != "?":
            return r

    return None


def format_music_info(info: Dict[str, Any]) -> str:
    """Форматировать информацию о треке."""
    if not info:
        return "Трек не распознан"

    parts = []
    if info.get("title"):
        parts.append(f"🎵 {info['title']}")
    if info.get("artist"):
        parts.append(f"👤 {info['artist']}")
    if info.get("album"):
        parts.append(f"💿 {info['album']}")
    if info.get("release_date"):
        parts.append(f"📅 {info['release_date']}")

    links = []
    if info.get("apple_music"):
        links.append(f"Apple Music: {info['apple_music']}")
    if info.get("spotify_url"):
        links.append(f"Spotify: {info['spotify_url']}")

    result = "\n".join(parts)
    if links:
        result += "\n\n" + "\n".join(links)

    source = info.get("source", "")
    if source:
        result += f"\n\nИсточник: {source}"

    return result or "Трек не распознан"
