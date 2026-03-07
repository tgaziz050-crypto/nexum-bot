"""
NEXUM — Генерация медиа (изображения, музыка с вокалом, видео).
Множество провайдеров с автоматическим fallback.
"""
import asyncio
import aiohttp
import os
import logging
import random
import re
import subprocess
import tempfile
from typing import Optional, Tuple
from urllib.parse import quote as uq

log = logging.getLogger("NEXUM.media")

HF_KEY = os.getenv("HF_API_KEY", "")
REPLICATE_KEY = os.getenv("REPLICATE_API_KEY", "")

HF_HEADERS = {"Authorization": f"Bearer {HF_KEY}"} if HF_KEY else {}


# ═══════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ═══════════════════════════════════════════════════════════

def is_img(d: bytes) -> bool:
    return len(d) > 8 and (d[:3] == b'\xff\xd8\xff' or d[:4] == b'\x89PNG' or d[:4] == b'RIFF')


def is_audio(d: bytes) -> bool:
    if len(d) < 8:
        return False
    # MP3, FLAC, WAV, OGG
    return (d[:3] == b'ID3' or d[:2] == b'\xff\xfb' or d[:4] == b'fLaC'
            or d[:4] == b'RIFF' or d[:4] == b'OggS' or d[:2] == b'\xff\xf3'
            or d[:2] == b'\xff\xf2')


def is_video(d: bytes) -> bool:
    if len(d) < 12:
        return False
    return (d[4:8] in (b'ftyp', b'moov', b'mdat') or d[:4] == b'\x1aE\xdf\xa3'
            or b'ftyp' in d[:20])


FFMPEG = __import__("shutil").which("ffmpeg")


# ═══════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
# ═══════════════════════════════════════════════════════════

IMG_STYLES = {
    "📸 Реализм":    "photorealistic, 8k uhd, professional DSLR photo, ultra detailed, sharp focus",
    "🎌 Аниме":      "anime style, vibrant colors, studio ghibli quality, manga illustration",
    "🌐 3D":         "3D render, octane render, cinema 4d, volumetric lighting, ultra detailed",
    "🎨 Масло":      "oil painting, classical art, old masters technique, rich textures, museum quality",
    "💧 Акварель":   "watercolor painting, soft colors, artistic brushwork, dreamy atmosphere",
    "🌃 Киберпанк":  "cyberpunk art, neon lights, futuristic city, dark atmosphere, blade runner",
    "🐉 Фэнтези":    "fantasy art, epic scene, magical illustration, artstation quality, D&D",
    "✏️ Эскиз":      "detailed pencil sketch, graphite drawing, professional illustration",
    "🟦 Пиксель":    "pixel art, 16-bit retro game style, clean crisp pixels",
    "📷 Портрет":    "portrait photography, studio lighting, 85mm lens, beautiful bokeh background",
    "🎭 Арт-деко":   "art deco style, geometric patterns, gold and black, elegant illustration",
    "🌸 Японский":   "ukiyo-e japanese woodblock print style, traditional art",
    "⚡ Авто":       "ultra detailed, high quality, professional, stunning masterpiece",
}

IMG_MODELS_POLLINATIONS = {
    "📸 Реализм": "flux-realism",
    "🎌 Аниме": "flux-anime",
    "🌐 3D": "flux-3d",
    "📷 Портрет": "flux-realism",
    "⚡ Авто": "flux",
}


async def _translate_to_en(text: str) -> str:
    """Translate prompt to English using AI if needed."""
    if not re.search(r'[а-яёА-ЯЁ\u0400-\u04FF]', text):
        return text
    try:
        # Simple translation using Pollinations text (free)
        async with aiohttp.ClientSession() as s:
            msg = f"Translate to English for AI image generation, return only translation: {text}"
            enc = uq(msg, safe='')
            async with s.get(
                f"https://text.pollinations.ai/{enc}",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    result = (await r.text()).strip()
                    if result and len(result) < 500:
                        return result
    except Exception as e:
        log.debug(f"Translate: {e}")
    return text


async def gen_img_pollinations(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """Pollinations AI — flux models, free."""
    try:
        en = await _translate_to_en(prompt)
        suffix = IMG_STYLES.get(style, IMG_STYLES["⚡ Авто"])
        # Enhance prompt
        final = f"{en}, {suffix}"[:700]
        seed = random.randint(1, 999999)
        enc = uq(final, safe='')
        model = IMG_MODELS_POLLINATIONS.get(style, "flux")

        urls = [
            f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model={model}&enhance=true",
            f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
            f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}&model=flux",
        ]
        conn = aiohttp.TCPConnector(ssl=False)
        for url in urls:
            try:
                async with aiohttp.ClientSession(connector=conn) as s:
                    async with s.get(url,
                        timeout=aiohttp.ClientTimeout(total=90),
                        headers={"User-Agent": "Mozilla/5.0"},
                        allow_redirects=True) as r:
                        if r.status == 200:
                            d = await r.read()
                            if is_img(d):
                                log.info("Image: Pollinations OK")
                                return d
            except Exception as e:
                log.debug(f"Pollinations url: {e}")
    except Exception as e:
        log.warning(f"Pollinations: {e}")
    return None


async def gen_img_prodia(prompt: str, style: str = "") -> Optional[bytes]:
    """Prodia — Stable Diffusion models, free."""
    try:
        en = await _translate_to_en(prompt)
        suffix = IMG_STYLES.get(style, "")
        final_prompt = f"{en}, {suffix}"[:500] if suffix else en[:500]
        neg_prompt = "blurry, bad quality, deformed, ugly, watermark, text, nsfw"

        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get(
                "https://api.prodia.com/generate",
                params={
                    "new": "true",
                    "prompt": final_prompt,
                    "negative_prompt": neg_prompt,
                    "model": "dreamshaper_8.safetensors",
                    "steps": "25",
                    "cfg_scale": "7",
                    "width": "1024",
                    "height": "1024",
                    "sampler": "DPM++ 2M Karras",
                    "seed": str(random.randint(1, 999999)),
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    job = await r.json()
                    job_id = job.get("job")
                    if not job_id:
                        return None

            # Poll for result
            for _ in range(40):
                await asyncio.sleep(2)
                async with s.get(
                    f"https://api.prodia.com/job/{job_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("status") == "succeeded":
                            img_url = data.get("imageUrl")
                            if img_url:
                                async with s.get(img_url, timeout=aiohttp.ClientTimeout(total=20)) as ir:
                                    if ir.status == 200:
                                        d = await ir.read()
                                        if is_img(d):
                                            log.info("Image: Prodia OK")
                                            return d
                            return None
    except Exception as e:
        log.debug(f"Prodia: {e}")
    return None


async def gen_img_replicate(prompt: str, style: str = "") -> Optional[bytes]:
    """Replicate — Flux Schnell, fast and high quality."""
    if not REPLICATE_KEY:
        return None
    try:
        en = await _translate_to_en(prompt)
        suffix = IMG_STYLES.get(style, "")
        final_prompt = f"{en}, {suffix}"[:600] if suffix else en[:600]

        async with aiohttp.ClientSession() as s:
            # Start prediction
            async with s.post(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                headers={
                    "Authorization": f"Token {REPLICATE_KEY}",
                    "Content-Type": "application/json",
                },
                json={"input": {"prompt": final_prompt, "num_outputs": 1}},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status not in (200, 201):
                    return None
                pred = await r.json()
                pred_id = pred.get("id")
                if not pred_id:
                    return None

            # Poll for result
            for _ in range(30):
                await asyncio.sleep(2)
                async with s.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Token {REPLICATE_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        status = data.get("status")
                        if status == "succeeded":
                            urls = data.get("output", [])
                            if urls:
                                async with s.get(urls[0], timeout=aiohttp.ClientTimeout(total=20)) as ir:
                                    if ir.status == 200:
                                        d = await ir.read()
                                        if is_img(d):
                                            log.info("Image: Replicate OK")
                                            return d
                            return None
                        elif status == "failed":
                            return None
    except Exception as e:
        log.debug(f"Replicate image: {e}")
    return None


async def gen_img(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """
    Главная функция генерации изображений.
    Параллельно пробует несколько провайдеров, возвращает первый успешный.
    """
    tasks = [
        gen_img_pollinations(prompt, style),
        gen_img_prodia(prompt, style),
    ]
    if REPLICATE_KEY:
        tasks.append(gen_img_replicate(prompt, style))

    # Запускаем все одновременно, берём первый успешный
    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            if result and is_img(result):
                return result
        except Exception as e:
            log.debug(f"gen_img task: {e}")
    return None


# ═══════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ МУЗЫКИ (реальное аудио + вокал)
# ═══════════════════════════════════════════════════════════

MUSIC_STYLES = {
    "🎸 Рок":       "energetic rock music, electric guitar riff, powerful drums, distortion effects",
    "🎹 Поп":       "modern pop song, catchy melody, synthesizer, upbeat, radio-ready",
    "🎷 Джаз":      "smooth jazz, saxophone solo, piano, double bass, relaxed swing",
    "🔥 Хип-хоп":   "hip hop beat, 808 bass, trap hi-hats, modern rap instrumental",
    "🎻 Классика":  "classical symphony, piano concerto, strings, orchestral, beethoven style",
    "🌊 Электро":   "electronic dance music, synthesizer leads, EDM drop, techno beat",
    "😌 Релакс":    "ambient music, soft piano, nature sounds, meditation, peaceful",
    "🎶 Лирика":    "emotional folk ballad, acoustic guitar, heartfelt vocals, storytelling",
    "💃 Латин":     "latin salsa rhythm, percussion, brass section, energetic dance music",
    "🌙 Лоу-фай":   "lofi hip hop, relaxing beats, vinyl crackle, chill study music",
    "🎺 Блюз":      "blues guitar, soulful vocals, 12-bar blues progression, emotional",
    "⚡ Авто":      "professional instrumental music, melodic, high quality studio recording",
}


async def gen_music_hf_musicgen(prompt: str, style: str) -> Optional[bytes]:
    """HuggingFace MusicGen — инструментальная музыка."""
    en = await _translate_to_en(prompt)
    style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["⚡ Авто"])
    full_prompt = f"{style_desc}, {en}"

    for model_url in [
        "https://api-inference.huggingface.co/models/facebook/musicgen-medium",
        "https://api-inference.huggingface.co/models/facebook/musicgen-small",
        "https://api-inference.huggingface.co/models/facebook/musicgen-stereo-medium",
    ]:
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        model_url,
                        headers=HF_HEADERS,
                        json={"inputs": full_prompt[:300], "parameters": {"duration": 25}},
                        timeout=aiohttp.ClientTimeout(total=150)
                    ) as r:
                        log.debug(f"MusicGen {model_url}: status {r.status}")
                        if r.status == 200:
                            ct = r.headers.get("content-type", "")
                            if any(x in ct for x in ["audio", "octet-stream", "flac", "wav"]):
                                d = await r.read()
                                if len(d) > 5000:
                                    log.info(f"Music: MusicGen OK ({len(d)} bytes)")
                                    return d
                        elif r.status == 503 and attempt == 0:
                            log.info("MusicGen: loading model, waiting 30s...")
                            await asyncio.sleep(30)
                        else:
                            break
            except Exception as e:
                log.debug(f"MusicGen: {e}")
                break
    return None


async def gen_music_bark_vocals(lyrics: str, voice: str = "v2/ru_speaker_3") -> Optional[bytes]:
    """
    Bark (Suno open-source) — генерация вокала из текста песни.
    Может звучать как пение если текст написан в нужном формате.
    """
    try:
        # Форматируем текст для Bark (специальные маркеры для пения)
        bark_text = lyrics[:200]  # Bark работает с короткими отрезками

        # Пробуем через HuggingFace
        for bark_model in [
            "https://api-inference.huggingface.co/models/suno/bark",
            "https://api-inference.huggingface.co/models/suno/bark-small",
        ]:
            for attempt in range(2):
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(
                            bark_model,
                            headers=HF_HEADERS,
                            json={
                                "inputs": bark_text,
                                "parameters": {"voice_preset": voice}
                            },
                            timeout=aiohttp.ClientTimeout(total=120)
                        ) as r:
                            if r.status == 200:
                                ct = r.headers.get("content-type", "")
                                if any(x in ct for x in ["audio", "octet-stream", "wav", "mpeg"]):
                                    d = await r.read()
                                    if len(d) > 1000:
                                        log.info(f"Music: Bark vocals OK ({len(d)} bytes)")
                                        return d
                            elif r.status == 503 and attempt == 0:
                                await asyncio.sleep(25)
                            else:
                                break
                except Exception as e:
                    log.debug(f"Bark: {e}")
                    break
    except Exception as e:
        log.warning(f"Bark: {e}")
    return None


async def gen_music_replicate(prompt: str, style: str) -> Optional[bytes]:
    """Replicate — MusicGen или MusicLM через API."""
    if not REPLICATE_KEY:
        return None
    try:
        en = await _translate_to_en(prompt)
        style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["⚡ Авто"])
        full_prompt = f"{style_desc}, {en}"

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.replicate.com/v1/models/meta/musicgen/predictions",
                headers={"Authorization": f"Token {REPLICATE_KEY}", "Content-Type": "application/json"},
                json={"input": {
                    "prompt": full_prompt[:400],
                    "duration": 25,
                    "output_format": "mp3",
                    "model_version": "stereo-large",
                }},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status not in (200, 201):
                    return None
                pred = await r.json()
                pred_id = pred.get("id")
                if not pred_id:
                    return None

            for _ in range(40):
                await asyncio.sleep(3)
                async with s.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Token {REPLICATE_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("status") == "succeeded":
                            output = data.get("output")
                            url = output if isinstance(output, str) else (output[0] if output else None)
                            if url:
                                async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as ar:
                                    if ar.status == 200:
                                        d = await ar.read()
                                        if is_audio(d) or len(d) > 10000:
                                            log.info("Music: Replicate OK")
                                            return d
                            return None
                        elif data.get("status") == "failed":
                            return None
    except Exception as e:
        log.debug(f"Replicate music: {e}")
    return None


async def gen_music_pollinations(prompt: str, style: str) -> Optional[bytes]:
    """Pollinations Audio — fallback."""
    try:
        en = await _translate_to_en(prompt)
        style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["⚡ Авто"])
        full_prompt = f"{style_desc}, {en}"
        enc = uq(full_prompt[:200], safe='')
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get(
                f"https://audio.pollinations.ai/{enc}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as r:
                if r.status == 200:
                    ct = r.headers.get("content-type", "")
                    if any(x in ct for x in ["audio", "mpeg", "wav", "ogg"]):
                        d = await r.read()
                        if len(d) > 5000:
                            log.info("Music: Pollinations OK")
                            return d
    except Exception as e:
        log.debug(f"Pollinations audio: {e}")
    return None


async def gen_music(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """
    Главная функция генерации музыки.
    Пробует несколько провайдеров параллельно.
    """
    tasks = [
        gen_music_hf_musicgen(prompt, style),
        gen_music_pollinations(prompt, style),
    ]
    if REPLICATE_KEY:
        tasks.append(gen_music_replicate(prompt, style))

    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            if result and (is_audio(result) or len(result) > 5000):
                return result
        except Exception as e:
            log.debug(f"gen_music task: {e}")
    return None


async def gen_song_with_vocals(prompt: str, style: str, ai_ask_func) -> Tuple[Optional[bytes], str]:
    """
    Генерация песни с вокалом:
    1. AI генерирует текст песни
    2. Bark генерирует вокал
    3. MusicGen генерирует инструментал
    4. ffmpeg смешивает (если доступен)
    Возвращает (audio_bytes, lyrics_text)
    """
    style_name = " ".join(style.split()[1:]) if style else "любой"

    # 1. Генерация текста песни
    lyrics_prompt = (
        f"Напиши текст песни в стиле {style_name} на тему: {prompt}\n\n"
        f"Структура: [Куплет 1], [Припев], [Куплет 2], [Припев]\n"
        f"Требования: ритмично, эмоционально, 80-120 слов. Только текст."
    )
    lyrics = await ai_ask_func(
        [{"role": "user", "content": lyrics_prompt}],
        max_t=500, task="creative"
    )

    # 2. Пробуем сгенерировать вокал через Bark
    vocals = None
    if lyrics:
        # Выбираем голос по языку
        if re.search(r'[а-яё]', lyrics, re.I):
            voice = "v2/ru_speaker_3"
        else:
            voice = "v2/en_speaker_6"
        vocals = await gen_bark_vocals(lyrics[:200], voice)

    # 3. Генерируем инструментал
    instrumental = await gen_music(prompt, style)

    # 4. Если есть оба — пробуем смешать через ffmpeg
    if vocals and instrumental and FFMPEG:
        mixed = await _mix_vocals_instrumental(vocals, instrumental)
        if mixed:
            log.info("Song: mixed vocals+instrumental")
            return mixed, lyrics or ""

    # Возвращаем что есть
    if instrumental:
        return instrumental, lyrics or ""
    if vocals:
        return vocals, lyrics or ""

    return None, lyrics or ""


async def gen_bark_vocals(text: str, voice: str = "v2/ru_speaker_3") -> Optional[bytes]:
    """Generat vocals using Bark."""
    return await gen_music_bark_vocals(text, voice)


async def _mix_vocals_instrumental(vocals: bytes, instrumental: bytes) -> Optional[bytes]:
    """Смешать вокал и инструментал через ffmpeg."""
    if not FFMPEG:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as vf:
            vf.write(vocals)
            v_path = vf.name
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as if_:
            if_.write(instrumental)
            i_path = if_.name
        out_path = v_path + "_mixed.mp3"

        cmd = [
            FFMPEG, "-y",
            "-i", v_path,
            "-i", i_path,
            "-filter_complex", "[0:a]volume=1.5[v];[1:a]volume=0.7[i];[v][i]amix=inputs=2:duration=longest",
            "-acodec", "libmp3lame", "-ab", "192k",
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(out_path):
            with open(out_path, "rb") as f:
                mixed = f.read()
            for p in [v_path, i_path, out_path]:
                try:
                    os.unlink(p)
                except:
                    pass
            if len(mixed) > 5000:
                return mixed
    except Exception as e:
        log.debug(f"Mix: {e}")
    return None


# ═══════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ ВИДЕО
# ═══════════════════════════════════════════════════════════

async def gen_video_zeroscope(prompt: str) -> Optional[bytes]:
    """ZeroScope v2 — text-to-video via HuggingFace."""
    en = await _translate_to_en(prompt)
    for model_url in [
        "https://api-inference.huggingface.co/models/cerspense/zeroscope_v2_576w",
        "https://api-inference.huggingface.co/models/cerspense/zeroscope_v2_XL",
    ]:
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        model_url,
                        headers=HF_HEADERS,
                        json={"inputs": en[:200]},
                        timeout=aiohttp.ClientTimeout(total=150)
                    ) as r:
                        if r.status == 200:
                            ct = r.headers.get("content-type", "")
                            d = await r.read()
                            if len(d) > 5000 and (is_video(d) or "video" in ct or "mp4" in ct):
                                log.info(f"Video: ZeroScope OK ({len(d)} bytes)")
                                return d
                        elif r.status == 503 and attempt == 0:
                            await asyncio.sleep(30)
                        else:
                            break
            except Exception as e:
                log.debug(f"ZeroScope: {e}")
                break
    return None


async def gen_video_modelscope(prompt: str) -> Optional[bytes]:
    """ModelScope text-to-video."""
    en = await _translate_to_en(prompt)
    try:
        for attempt in range(2):
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api-inference.huggingface.co/models/damo-vilab/text-to-video-ms-1.7b",
                    headers=HF_HEADERS,
                    json={"inputs": en[:200]},
                    timeout=aiohttp.ClientTimeout(total=150)
                ) as r:
                    if r.status == 200:
                        d = await r.read()
                        if len(d) > 5000:
                            log.info(f"Video: ModelScope OK ({len(d)} bytes)")
                            return d
                    elif r.status == 503 and attempt == 0:
                        await asyncio.sleep(35)
                    else:
                        break
    except Exception as e:
        log.debug(f"ModelScope: {e}")
    return None


async def gen_video_pollinations(prompt: str) -> Optional[bytes]:
    """Pollinations video fallback."""
    try:
        en = await _translate_to_en(prompt)
        enc = uq(en[:300], safe='')
        seed = random.randint(1, 999999)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get(
                f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as r:
                if r.status == 200:
                    d = await r.read()
                    if len(d) > 5000:
                        log.info(f"Video: Pollinations OK ({len(d)} bytes)")
                        return d
    except Exception as e:
        log.debug(f"Pollinations video: {e}")
    return None


async def gen_video_replicate(prompt: str) -> Optional[bytes]:
    """Stable Video Diffusion via Replicate."""
    if not REPLICATE_KEY:
        return None
    try:
        en = await _translate_to_en(prompt)
        async with aiohttp.ClientSession() as s:
            # Use AnimateDiff or similar
            async with s.post(
                "https://api.replicate.com/v1/models/lucataco/animate-diff/predictions",
                headers={"Authorization": f"Token {REPLICATE_KEY}", "Content-Type": "application/json"},
                json={"input": {"prompt": en[:400], "num_frames": 16, "fps": 8}},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status not in (200, 201):
                    return None
                pred = await r.json()
                pred_id = pred.get("id")
                if not pred_id:
                    return None

            for _ in range(40):
                await asyncio.sleep(3)
                async with s.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Token {REPLICATE_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("status") == "succeeded":
                            output = data.get("output")
                            url = output if isinstance(output, str) else (output[0] if output else None)
                            if url:
                                async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as vr:
                                    if vr.status == 200:
                                        d = await vr.read()
                                        if len(d) > 5000:
                                            log.info("Video: Replicate OK")
                                            return d
                            return None
                        elif data.get("status") == "failed":
                            return None
    except Exception as e:
        log.debug(f"Replicate video: {e}")
    return None


async def gen_video(prompt: str) -> Optional[bytes]:
    """
    Главная функция генерации видео.
    Параллельно пробует все провайдеры.
    """
    tasks = [
        gen_video_pollinations(prompt),
        gen_video_zeroscope(prompt),
        gen_video_modelscope(prompt),
    ]
    if REPLICATE_KEY:
        tasks.append(gen_video_replicate(prompt))

    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            if result and len(result) > 5000:
                return result
        except Exception as e:
            log.debug(f"gen_video task: {e}")
    return None
