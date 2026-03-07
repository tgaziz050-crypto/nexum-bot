"""
NEXUM — Расширенные веб-инструменты.
Поиск, чтение страниц, работа с сайтами.
"""
import asyncio
import aiohttp
import logging
import re
from typing import Optional, List, Dict, Any
from urllib.parse import quote as uq, urlencode

log = logging.getLogger("NEXUM.web")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


async def search_searx(q: str, instance: str = "https://searx.be") -> List[Dict]:
    """Поиск через SearX."""
    try:
        url = f"{instance}/search?q={uq(q)}&format=json&language=ru"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return data.get("results", [])[:5]
    except Exception as e:
        log.debug(f"SearX {instance}: {e}")
    return []


async def search_duckduckgo(q: str) -> List[Dict]:
    """Поиск через DuckDuckGo instant answers."""
    try:
        url = f"https://api.duckduckgo.com/?q={uq(q)}&format=json&no_html=1&skip_disambig=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    results = []
                    if d.get("AbstractText"):
                        results.append({
                            "title": d.get("Heading", q),
                            "content": d["AbstractText"],
                            "url": d.get("AbstractURL", ""),
                        })
                    for topic in d.get("RelatedTopics", [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append({
                                "title": topic.get("Text", "")[:80],
                                "content": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                            })
                    return results
    except Exception as e:
        log.debug(f"DuckDuckGo: {e}")
    return []


async def search_brave(q: str) -> List[Dict]:
    """Поиск через Brave Search (без API ключа - scraping)."""
    try:
        url = f"https://search.brave.com/search?q={uq(q)}&source=web"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    html = await r.text(errors="ignore")
                    # Извлекаем результаты из HTML
                    titles = re.findall(r'<div class="url-header"[^>]*>([^<]+)</div>', html)
                    snippets = re.findall(r'<p class="snippet-description"[^>]*>([^<]+)</p>', html)
                    results = []
                    for i, (t, s) in enumerate(zip(titles[:5], snippets[:5])):
                        results.append({"title": t.strip(), "content": s.strip(), "url": ""})
                    return results
    except Exception as e:
        log.debug(f"Brave: {e}")
    return []


async def web_search(q: str) -> Optional[str]:
    """
    Комплексный веб-поиск через несколько движков.
    Возвращает объединённые результаты.
    """
    # Параллельный поиск
    searx_instances = [
        "https://searx.be",
        "https://priv.au",
        "https://search.sapti.me",
    ]

    tasks = [search_searx(q, inst) for inst in searx_instances]
    tasks.append(search_duckduckgo(q))
    tasks.append(search_brave(q))

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    combined = []
    seen_content = set()

    for results in all_results:
        if isinstance(results, list):
            for r in results:
                content = r.get("content", "").strip()
                if content and content[:50] not in seen_content and len(content) > 20:
                    seen_content.add(content[:50])
                    combined.append(r)

    if not combined:
        return None

    parts = []
    for r in combined[:6]:
        title = r.get("title", "").strip()
        content = r.get("content", "").strip()
        url = r.get("url", "").strip()
        if content:
            part = f"{title}\n{content}"
            if url:
                part += f"\n{url}"
            parts.append(part)

    return "\n\n".join(parts) if parts else None


async def read_page(url: str, max_chars: int = 8000) -> Optional[str]:
    """
    Читать содержимое веб-страницы.
    Поддерживает большинство сайтов.
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=25),
                allow_redirects=True,
                max_redirects=5,
            ) as r:
                if r.status != 200:
                    return None
                content_type = r.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    return f"[Бинарный файл: {content_type}]"

                html = await r.text(errors="ignore")
                return extract_text_from_html(html, max_chars)
    except asyncio.TimeoutError:
        log.warning(f"Timeout reading: {url}")
        return None
    except Exception as e:
        log.warning(f"read_page({url}): {e}")
        return None


def extract_text_from_html(html: str, max_chars: int = 8000) -> str:
    """Извлечь чистый текст из HTML."""
    # Удаляем скрипты, стили и прочее мусор
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.I)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.I)
    text = re.sub(r'<nav[^>]*>.*?</nav>', ' ', text, flags=re.DOTALL | re.I)
    text = re.sub(r'<footer[^>]*>.*?</footer>', ' ', text, flags=re.DOTALL | re.I)
    text = re.sub(r'<header[^>]*>.*?</header>', ' ', text, flags=re.DOTALL | re.I)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)

    # Заменяем блочные теги на переносы строк
    for tag in ['p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr']:
        text = re.sub(rf'</?{tag}[^>]*>', '\n', text, flags=re.I)

    # Удаляем все оставшиеся теги
    text = re.sub(r'<[^>]+>', '', text)

    # Декодируем HTML entities
    entities = {
        '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
        '&quot;': '"', '&apos;': "'", '&#39;': "'", '&mdash;': '—',
        '&ndash;': '–', '&hellip;': '…', '&laquo;': '«', '&raquo;': '»',
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)

    # Нормализуем пробелы
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text[:max_chars]


async def weather(loc: str) -> Optional[str]:
    """Получить погоду для города."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://wttr.in/{uq(loc)}?format=j1&lang=ru",
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    cur = (await r.json()).get("current_condition", [{}])[0]
                    desc = cur.get("lang_ru", [{}])[0].get("value", "")
                    w3 = []
                    try:
                        weather_data = await r.json()
                        for day in weather_data.get("weather", [])[:3]:
                            date = day.get("date", "")
                            max_c = day.get("maxtempC", "?")
                            min_c = day.get("mintempC", "?")
                            w3.append(f"{date}: {min_c}..{max_c}°C")
                    except:
                        pass
                    result = (
                        f"🌡 {cur.get('temp_C', '?')}°C"
                        f" (ощущается {cur.get('FeelsLikeC', '?')}°C)\n"
                        f"☁️ {desc}\n"
                        f"💧 Влажность: {cur.get('humidity', '?')}%\n"
                        f"💨 Ветер: {cur.get('windspeedKmph', '?')} км/ч"
                    )
                    if w3:
                        result += "\n\nПрогноз:\n" + "\n".join(w3)
                    return result
    except Exception as e:
        log.warning(f"Weather: {e}")
    return None


async def exchange(fr: str, to: str) -> Optional[str]:
    """Курс обмена валют."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://open.er-api.com/v6/latest/{fr.upper()}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    rates = data.get("rates", {})
                    to_upper = to.upper()
                    if to_upper in rates:
                        rate = rates[to_upper]
                        return (
                            f"💱 1 {fr.upper()} = {rate:.4f} {to_upper}\n"
                            f"💱 1 {to_upper} = {1/rate:.4f} {fr.upper()}"
                        )
    except Exception as e:
        log.warning(f"Exchange: {e}")
    return None


async def get_youtube_info(url: str) -> Optional[Dict]:
    """Получить информацию о YouTube видео."""
    try:
        # Извлекаем video ID
        vid_id = None
        patterns = [
            r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'embed/([a-zA-Z0-9_-]{11})',
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                vid_id = m.group(1)
                break

        if not vid_id:
            return None

        # Используем noembed для метаданных
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={vid_id}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return {
                        "title": d.get("title", ""),
                        "author": d.get("author_name", ""),
                        "thumbnail": d.get("thumbnail_url", ""),
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                    }
    except Exception as e:
        log.debug(f"YouTube info: {e}")
    return None
