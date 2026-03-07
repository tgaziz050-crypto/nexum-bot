"""
NEXUM — Интеграция с Notion API.
Создание страниц, блоков, поиск.
"""
import os
import logging
from typing import Optional, Dict, Any, List

log = logging.getLogger("NEXUM.notion")

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

def is_configured() -> bool:
    return bool(NOTION_API_KEY.strip())


async def create_page(title: str, content: str, database_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Создаёт страницу в указанной базе Notion."""
    if not NOTION_API_KEY:
        return None
    db_id = (database_id or NOTION_DATABASE_ID).strip()
    if not db_id:
        log.warning("NOTION_DATABASE_ID not set")
        return None

    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed")
        return None

    blocks = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]}
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:][:2000]}}]}
            })
        elif line.startswith("- "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]}
            })
        else:
            chunks = [line[i:i+2000] for i in range(0, len(line), 2000)]
            for chunk in chunks:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]}
                })

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                },
                json={
                    "parent": {"database_id": db_id},
                    "properties": {
                        "title": {
                            "title": [{"type": "text", "text": {"content": title[:2000]}}]
                        }
                    },
                    "children": blocks[:100],
                },
            )
            if r.status_code in (200, 201):
                return r.json()
            log.warning(f"Notion API: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.error(f"Notion: {e}")
    return None


async def search_pages(query: str = "") -> List[Dict[str, Any]]:
    """Поиск страниц в Notion."""
    if not NOTION_API_KEY:
        return []
    try:
        import httpx
    except ImportError:
        return []

    body = {}
    if query:
        body["query"] = query

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.notion.com/v1/search",
                headers={
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                },
                json=body or {"page_size": 10},
            )
            if r.status_code == 200:
                d = r.json()
                return d.get("results", [])[:10]
    except Exception as e:
        log.error(f"Notion search: {e}")
    return []
