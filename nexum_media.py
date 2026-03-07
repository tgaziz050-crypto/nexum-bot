"""
NEXUM — Media Generation
Image, Music (instrumental), Song (with vocals), Video generation.
Uses free providers with fallback chain.
"""
import asyncio, aiohttp, os, logging, tempfile, subprocess, random
from typing import Optional, Tuple
from urllib.parse import quote as uq

log = logging.getLogger("NEXUM.media")
HF_TOKEN = os.getenv("HF_TOKEN", "")
REPLICATE_KEY = os.getenv("REPLICATE_KEY", "")
FFMPEG = __import__("shutil").which("ffmpeg")

def _hf_headers():
    h = {"Content-Type": "application/json"}
    if HF_TOKEN: h["Authorization"] = f"Bearer {HF_TOKEN}"
    return h

def _is_img(d: bytes) -> bool:
    return len(d) > 8 and (d[:3] == b'\xff\xd8\xff' or d[:4] == b'\x89PNG')

def _is_audio(d: bytes) -> bool:
    return len(d) > 1000 and (
        d[:4] in (b'fLaC', b'RIFF', b'ID3\x03', b'ID3\x02', b'ID3\x04') or
        d[:2] == b'\xff\xfb' or d[:2] == b'\xff\xf3' or b'WAVE' in d[:12]
    )

def _is_video(d: bytes) -> bool:
    return len(d) > 5000 and (
        d[:4] in (b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c') or
        b'ftyp' in d[4:12] or b'moov' in d[:20]
    )

IMG_STYLES = {
    "авто":       "ultra detailed, high quality, professional, 8k",
    "реализм":    "photorealistic, 8k uhd, professional photo, ultra detailed, sharp focus, studio lighting",
    "аниме":      "anime style, vibrant colors, studio ghibli inspired, detailed illustration",
    "3d":         "3D render, octane render, cinema 4d, volumetric lighting, ultra realistic",
    "масло":      "oil painting, classical art, old masters technique, rich textures, museum quality",
    "акварель":   "watercolor painting, soft colors, artistic brushwork, dreamy atmosphere",
    "киберпанк":  "cyberpunk art, neon lights, futuristic city, dark atmosphere, blade runner aesthetic",
    "фэнтези":    "epic fantasy art, magical illustration, detailed, artstation trending",
    "эскиз":      "detailed pencil sketch, graphite drawing, professional illustration, clean lines",
    "пиксель":    "pixel art, 16-bit style, retro game aesthetic, clean pixels",
    "портрет":    "professional portrait photography, studio lighting, 85mm lens, bokeh background",
    "минимализм": "minimalist design, clean, simple, elegant, white background",
}

MUSIC_STYLES = {
    "рок":        "energetic rock music, electric guitar riffs, powerful drums, distortion",
    "поп":        "catchy pop song, upbeat melody, modern synthesizer, radio-friendly",
    "джаз":       "smooth jazz, saxophone solo, piano chords, double bass, relaxed atmosphere",
    "хип-хоп":    "hip hop instrumental, 808 bass, trap beat, modern rap production",
    "классика":   "classical orchestra, symphonic, piano concerto, strings section",
    "электро":    "electronic dance music, synthesizer, EDM drop, techno beats",
    "релакс":     "ambient relaxing music, soft piano, nature sounds, meditation, lo-fi",
    "r&b":        "smooth r&b, soulful melody, groove bass, modern production",
    "метал":      "heavy metal, distorted guitar, double kick drums, powerful riffs",
    "кантри":     "country music, acoustic guitar, fiddle, storytelling melody",
    "авто":       "instrumental music, melodic, professional recording, high quality",
}


# ═══════════════════════════════════════════════════════════
#  IMAGE GENERATION
# ═══════════════════════════════════════════════════════════
async def _gen_img_pollinations(prompt: str, style_key: str) -> Optional[bytes]:
    suffix = IMG_STYLES.get(style_key, IMG_STYLES["авто"])
    final = f"{prompt}, {suffix}"[:600]
    seed = random.randint(1, 999999)
    enc = uq(final, safe='')
    mdl_map = {"реализм": "flux-realism", "аниме": "flux-anime",
               "3d": "flux-3d", "портрет": "flux-realism"}
    mdl = mdl_map.get(style_key, "flux")
    urls = [
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model={mdl}",
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
        f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}",
    ]
    conn = aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True) as r:
                    if r.status == 200:
                        d = await r.read()
                        if _is_img(d): return d
        except: pass
    return None

async def _gen_img_prodia(prompt: str, style_key: str) -> Optional[bytes]:
    """Prodia Stable Diffusion API — free."""
    model_map = {
        "аниме": "anything-v4.5-pruned.ckpt [65745d25]",
        "реализм": "Realistic_Vision_V5.0.safetensors [614d1063]",
        "фэнтези": "dreamshaper_8.safetensors [9d40847d]",
    }
    body = {
        "prompt": f"{prompt}, {IMG_STYLES.get(style_key, '')}",
        "negative_prompt": "blurry, low quality, watermark, nsfw",
        "model": model_map.get(style_key, "v1-5-pruned-emaonly.safetensors [d7049739]"),
        "steps": 25, "cfg_scale": 7, "seed": random.randint(1, 999999),
        "width": 512, "height": 512, "sampler": "DPM++ 2M Karras",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.prodia.com/v1/sd/generate",
                headers={"X-Prodia-Key": "fast", "Content-Type": "application/json"},
                json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    job = await r.json()
                    job_id = job.get("job")
                    if not job_id: return None
                    for _ in range(20):
                        await asyncio.sleep(3)
                        async with s.get(f"https://api.prodia.com/v1/job/{job_id}",
                            headers={"X-Prodia-Key": "fast"}) as jr:
                            if jr.status == 200:
                                jdata = await jr.json()
                                if jdata.get("status") == "succeeded":
                                    img_url = jdata.get("imageUrl")
                                    if img_url:
                                        async with s.get(img_url, timeout=aiohttp.ClientTimeout(total=30)) as ir:
                                            if ir.status == 200:
                                                d = await ir.read()
                                                if _is_img(d): return d
    except Exception as e:
        log.debug(f"Prodia: {e}")
    return None

async def gen_img(prompt: str, style: str = "авто") -> Optional[bytes]:
    """Generate image. Tries multiple providers in parallel."""
    style_key = style.lower().strip()
    tasks = [
        _gen_img_pollinations(prompt, style_key),
        _gen_img_prodia(prompt, style_key),
    ]
    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            if result: return result
        except: pass
    return None


# ═══════════════════════════════════════════════════════════
#  MUSIC GENERATION (instrumental)
# ═══════════════════════════════════════════════════════════
async def _gen_music_hf(prompt: str, style_key: str,
                         model: str = "facebook/musicgen-small") -> Optional[bytes]:
    full_prompt = f"{MUSIC_STYLES.get(style_key, MUSIC_STYLES['авто'])}, {prompt}"
    body = {"inputs": full_prompt[:300], "parameters": {"duration": 20}}
    url = f"https://api-inference.huggingface.co/models/{model}"
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, headers=_hf_headers(), json=body,
                    timeout=aiohttp.ClientTimeout(total=150)) as r:
                    log.info(f"HF MusicGen {model}: {r.status}")
                    if r.status == 200:
                        ct = r.headers.get("content-type", "")
                        if any(x in ct for x in ["audio", "octet-stream", "flac", "wav"]):
                            d = await r.read()
                            if len(d) > 3000:
                                log.info(f"HF music OK: {len(d)} bytes")
                                return d
                    elif r.status == 503:
                        wait_time = 30 if attempt == 0 else 60
                        log.info(f"HF model loading, wait {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        txt = await r.text()
                        log.warning(f"HF music: {r.status} — {txt[:100]}")
                        break
        except Exception as e:
            log.warning(f"HF music error: {e}")
            if attempt < 2: await asyncio.sleep(5)
    return None

async def _gen_music_pollinations(prompt: str, style_key: str) -> Optional[bytes]:
    full = f"{MUSIC_STYLES.get(style_key, '')} {prompt}"
    enc = uq(full[:300], safe='')
    urls = [
        f"https://audio.pollinations.ai/{enc}",
        f"https://audio.pollinations.ai/prompt/{enc}",
    ]
    conn = aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"},
                    timeout=aiohttp.ClientTimeout(total=90)) as r:
                    if r.status == 200:
                        ct = r.headers.get("content-type", "")
                        if any(x in ct for x in ["audio", "mpeg", "wav", "octet"]):
                            d = await r.read()
                            if len(d) > 3000: return d
        except: pass
    return None

async def _gen_music_replicate(prompt: str, style_key: str) -> Optional[bytes]:
    if not REPLICATE_KEY: return None
    full = f"{MUSIC_STYLES.get(style_key, '')} {prompt}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.replicate.com/v1/predictions",
                headers={"Authorization": f"Token {REPLICATE_KEY}", "Content-Type": "application/json"},
                json={"version": "b05b1dff1d8c6dc63d14b0cdb42135378dcb87f6b90b65",
                      "input": {"prompt": full[:300], "duration": 20, "model_version": "stereo-large"}},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status in (200, 201):
                    pred = await r.json()
                    pred_id = pred.get("id")
                    if not pred_id: return None
                    for _ in range(30):
                        await asyncio.sleep(5)
                        async with s.get(f"https://api.replicate.com/v1/predictions/{pred_id}",
                            headers={"Authorization": f"Token {REPLICATE_KEY}"}) as pr:
                            if pr.status == 200:
                                pdata = await pr.json()
                                if pdata.get("status") == "succeeded":
                                    out = pdata.get("output", [])
                                    url = out[0] if isinstance(out, list) and out else out
                                    if url:
                                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as ar:
                                            if ar.status == 200:
                                                d = await ar.read()
                                                if len(d) > 3000: return d
                                elif pdata.get("status") == "failed":
                                    break
    except Exception as e:
        log.warning(f"Replicate music: {e}")
    return None

async def gen_music(prompt: str, style: str = "авто") -> Optional[bytes]:
    """Generate instrumental music. Tries multiple providers."""
    style_key = style.lower().strip()
    # Try HF models in sequence (parallel can overload free tier)
    for model in ["facebook/musicgen-small", "facebook/musicgen-medium"]:
        result = await _gen_music_hf(prompt, style_key, model)
        if result: return result
    # Fallback providers
    for coro in [_gen_music_pollinations(prompt, style_key),
                 _gen_music_replicate(prompt, style_key)]:
        try:
            result = await coro
            if result: return result
        except: pass
    return None


# ═══════════════════════════════════════════════════════════
#  SONG WITH VOCALS
# ═══════════════════════════════════════════════════════════
async def _gen_vocals_hf(lyrics: str) -> Optional[bytes]:
    """Generate voice/vocals via Bark TTS or similar."""
    models = [
        "suno/bark-small",
        "facebook/mms-tts-rus",
    ]
    for model in models:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers=_hf_headers(),
                    json={"inputs": lyrics[:500]},
                    timeout=aiohttp.ClientTimeout(total=120)) as r:
                    if r.status == 200:
                        ct = r.headers.get("content-type", "")
                        if any(x in ct for x in ["audio", "octet", "wav", "mpeg"]):
                            d = await r.read()
                            if len(d) > 1000: return d
                    elif r.status == 503:
                        await asyncio.sleep(30)
        except: pass
    return None

async def gen_song_with_vocals(prompt: str, style: str = "авто",
                                lyrics_text: str = "") -> Tuple[Optional[bytes], str]:
    """Generate song: AI lyrics → vocals (Bark) + instrumental (MusicGen) → mix."""
    style_key = style.lower().strip()

    # Generate lyrics if not provided
    if not lyrics_text:
        from nexum_config import GEMINI_KEYS, GROQ_KEYS
        lyrics_text = ""  # will be filled by caller

    # Get vocals and instrumental in parallel
    vocals_task = asyncio.create_task(_gen_vocals_hf(lyrics_text[:500]))
    music_task = asyncio.create_task(_gen_music_hf(f"{prompt} {style_key}", style_key))

    vocals = await vocals_task
    music = await music_task

    # Mix with ffmpeg if both available
    if vocals and music and FFMPEG:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as vf:
                vf.write(vocals); vp = vf.name
            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as mf:
                mf.write(music); mp = mf.name
            out = tempfile.mktemp(suffix=".mp3")
            r = subprocess.run([
                FFMPEG, "-y",
                "-i", vp, "-i", mp,
                "-filter_complex",
                "[0:a]volume=1.0[v];[1:a]volume=0.4[m];[v][m]amix=inputs=2:duration=longest[out]",
                "-map", "[out]", "-codec:a", "libmp3lame", "-q:a", "2", out
            ], capture_output=True, timeout=60)
            for f in (vp, mp):
                try: os.unlink(f)
                except: pass
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
                with open(out, "rb") as f: mixed = f.read()
                try: os.unlink(out)
                except: pass
                return mixed, lyrics_text
        except Exception as e:
            log.error(f"FFmpeg mix: {e}")

    # Return just vocals or just music
    if vocals: return vocals, lyrics_text
    if music: return music, lyrics_text
    return None, lyrics_text


# ═══════════════════════════════════════════════════════════
#  VIDEO GENERATION
# ═══════════════════════════════════════════════════════════
async def _gen_video_pollinations(prompt: str) -> Optional[bytes]:
    enc = uq(prompt[:300], safe='')
    seed = random.randint(1, 999999)
    urls = [
        f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
        f"https://video.pollinations.ai/{enc}?seed={seed}",
    ]
    conn = aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=aiohttp.ClientTimeout(total=150), allow_redirects=True) as r:
                    log.info(f"Pollinations video: {r.status}, content-type: {r.headers.get('content-type','')}")
                    if r.status == 200:
                        ct = r.headers.get("content-type", "")
                        if any(x in ct for x in ["video", "mp4", "octet"]):
                            d = await r.read()
                            log.info(f"Video bytes: {len(d)}")
                            if len(d) > 5000: return d
                        else:
                            # Still try to read — might be video despite wrong CT
                            d = await r.read()
                            if _is_video(d): return d
        except asyncio.TimeoutError:
            log.warning(f"Pollinations video timeout: {url}")
        except Exception as e:
            log.warning(f"Pollinations video error: {e}")
    return None

async def _gen_video_hf_zeroscope(prompt: str) -> Optional[bytes]:
    """ZeroScope v2 via HuggingFace Inference API."""
    url = "https://api-inference.huggingface.co/models/cerspense/zeroscope_v2_576w"
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, headers=_hf_headers(),
                    json={"inputs": prompt[:200]},
                    timeout=aiohttp.ClientTimeout(total=180)) as r:
                    log.info(f"ZeroScope: {r.status}")
                    if r.status == 200:
                        ct = r.headers.get("content-type", "")
                        d = await r.read()
                        log.info(f"ZeroScope bytes: {len(d)}, ct: {ct}")
                        if len(d) > 5000 and (
                            _is_video(d) or "video" in ct or "octet" in ct
                        ):
                            return d
                    elif r.status == 503:
                        log.info("ZeroScope loading, wait 45s...")
                        await asyncio.sleep(45)
                    else:
                        txt = await r.text()
                        log.warning(f"ZeroScope: {r.status} — {txt[:100]}")
                        break
        except Exception as e:
            log.warning(f"ZeroScope: {e}")
    return None

async def _gen_video_hf_modelscope(prompt: str) -> Optional[bytes]:
    """ModelScope text-to-video via HuggingFace."""
    url = "https://api-inference.huggingface.co/models/damo-vilab/text-to-video-ms-1.7b"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=_hf_headers(),
                json={"inputs": prompt[:200]},
                timeout=aiohttp.ClientTimeout(total=180)) as r:
                log.info(f"ModelScope: {r.status}")
                if r.status == 200:
                    d = await r.read()
                    if len(d) > 5000: return d
                elif r.status == 503:
                    await asyncio.sleep(60)
                    async with s.post(url, headers=_hf_headers(),
                        json={"inputs": prompt[:200]},
                        timeout=aiohttp.ClientTimeout(total=180)) as r2:
                        if r2.status == 200:
                            d = await r2.read()
                            if len(d) > 5000: return d
    except Exception as e:
        log.warning(f"ModelScope: {e}")
    return None

async def _gen_video_replicate(prompt: str) -> Optional[bytes]:
    if not REPLICATE_KEY: return None
    # Using AnimateDiff or similar
    models = [
        ("lucataco/animate-diff", {"prompt": prompt[:200], "num_frames": 16}),
    ]
    async with aiohttp.ClientSession() as s:
        for model_id, inp in models:
            try:
                # Get latest version
                async with s.get(f"https://api.replicate.com/v1/models/{model_id}",
                    headers={"Authorization": f"Token {REPLICATE_KEY}"}) as mr:
                    if mr.status != 200: continue
                    mdata = await mr.json()
                    version = mdata.get("latest_version", {}).get("id")
                    if not version: continue

                async with s.post("https://api.replicate.com/v1/predictions",
                    headers={"Authorization": f"Token {REPLICATE_KEY}", "Content-Type": "application/json"},
                    json={"version": version, "input": inp},
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status not in (200, 201): continue
                    pred = await r.json()
                    pred_id = pred.get("id")
                    if not pred_id: continue

                for _ in range(40):
                    await asyncio.sleep(5)
                    async with s.get(f"https://api.replicate.com/v1/predictions/{pred_id}",
                        headers={"Authorization": f"Token {REPLICATE_KEY}"}) as pr:
                        if pr.status != 200: break
                        pdata = await pr.json()
                        status = pdata.get("status")
                        if status == "succeeded":
                            out = pdata.get("output", [])
                            url = out[0] if isinstance(out, list) and out else out
                            if url:
                                async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as vr:
                                    if vr.status == 200:
                                        d = await vr.read()
                                        if len(d) > 5000: return d
                            break
                        elif status == "failed":
                            break
            except Exception as e:
                log.warning(f"Replicate video {model_id}: {e}")
    return None

async def gen_video(prompt: str) -> Optional[bytes]:
    """Generate video. Tries multiple providers."""
    log.info(f"Generating video: {prompt[:50]}")
    # Try sequentially to avoid rate limits
    result = await _gen_video_pollinations(prompt)
    if result: return result
    result = await _gen_video_hf_zeroscope(prompt)
    if result: return result
    result = await _gen_video_hf_modelscope(prompt)
    if result: return result
    result = await _gen_video_replicate(prompt)
    return result


# ═══════════════════════════════════════════════════════════
#  TRANSLATION HELPER
# ═══════════════════════════════════════════════════════════
async def translate_to_en(text: str) -> str:
    import re
    if not re.search(r'[а-яёА-ЯЁ]', text): return text
    from nexum_config import GEMINI_KEYS
    if not GEMINI_KEYS: return text
    try:
        async with aiohttp.ClientSession() as s:
            body = {
                "contents": [{"role": "user", "parts": [{"text": f"Translate to English for AI generation. Only translation, no explanation:\n{text}"}]}],
                "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1},
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEYS[0]}"
            async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["candidates"][0]["content"]["parts"][0]["text"].strip()
    except: pass
    return text
