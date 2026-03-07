"""
NEXUM — Notion Integration
Full Notion API: create pages, databases, todos, notes, search.
"""
import aiohttp, asyncio, logging, re
from typing import Optional, Dict, List, Any
from datetime import datetime

log = logging.getLogger("NEXUM.notion")
NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"

class NotionClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def _req(self, method: str, path: str, **kwargs) -> Optional[dict]:
        url = f"{BASE}{path}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.request(method, url, headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=20), **kwargs) as r:
                    if r.status in (200, 201):
                        return await r.json()
                    else:
                        text = await r.text()
                        log.error(f"Notion {method} {path}: {r.status} — {text[:200]}")
                        return None
        except Exception as e:
            log.error(f"Notion request error: {e}")
            return None

    async def search(self, query: str, limit=5) -> List[dict]:
        data = {"query": query, "page_size": limit}
        r = await self._req("POST", "/search", json=data)
        return r.get("results", []) if r else []

    async def get_page(self, page_id: str) -> Optional[dict]:
        return await self._req("GET", f"/pages/{page_id}")

    async def get_page_content(self, page_id: str) -> str:
        r = await self._req("GET", f"/blocks/{page_id}/children")
        if not r: return ""
        texts = []
        for block in r.get("results", []):
            bt = block.get("type","")
            rich = block.get(bt, {}).get("rich_text", [])
            for rt in rich:
                texts.append(rt.get("plain_text",""))
        return "\n".join(texts)

    async def create_page(self, parent_id: str, title: str, content: str = "",
                          is_database: bool = False) -> Optional[dict]:
        """Create a page under a parent page or database."""
        if is_database:
            parent = {"database_id": parent_id}
            props = {"Name": {"title": [{"text": {"content": title}}]}}
        else:
            parent = {"page_id": parent_id}
            props = {"title": [{"text": {"content": title}}]}

        children = _md_to_blocks(content) if content else []
        body = {"parent": parent, "properties": props}
        if children: body["children"] = children
        return await self._req("POST", "/pages", json=body)

    async def append_to_page(self, page_id: str, content: str) -> Optional[dict]:
        blocks = _md_to_blocks(content)
        if not blocks: return None
        return await self._req("PATCH", f"/blocks/{page_id}/children",
            json={"children": blocks})

    async def create_database(self, parent_id: str, title: str,
                               properties: Dict = None) -> Optional[dict]:
        default_props = {
            "Name": {"title": {}},
            "Status": {"select": {"options": [
                {"name": "Todo", "color": "red"},
                {"name": "In Progress", "color": "yellow"},
                {"name": "Done", "color": "green"},
            ]}},
            "Date": {"date": {}},
            "Tags": {"multi_select": {}},
        }
        body = {
            "parent": {"page_id": parent_id},
            "title": [{"text": {"content": title}}],
            "properties": properties or default_props,
        }
        return await self._req("POST", "/databases", json=body)

    async def add_db_item(self, database_id: str, title: str,
                           status: str = "Todo", tags: List[str] = None,
                           content: str = "") -> Optional[dict]:
        props = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"select": {"name": status}},
            "Date": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
        }
        if tags:
            props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
        children = _md_to_blocks(content) if content else []
        body = {"parent": {"database_id": database_id}, "properties": props}
        if children: body["children"] = children
        return await self._req("POST", "/pages", json=body)

    async def query_database(self, database_id: str, filter_status: str = None,
                              limit: int = 10) -> List[dict]:
        body: Dict[str, Any] = {"page_size": limit}
        if filter_status:
            body["filter"] = {"property": "Status", "select": {"equals": filter_status}}
        r = await self._req("POST", f"/databases/{database_id}/query", json=body)
        return r.get("results", []) if r else []

    async def get_users(self) -> List[dict]:
        r = await self._req("GET", "/users")
        return r.get("results", []) if r else []

    async def format_page_info(self, page: dict) -> str:
        """Format page info for display."""
        title = _get_page_title(page)
        url = page.get("url", "")
        edited = page.get("last_edited_time", "")[:10]
        return f"📄 {title}\n🔗 {url}\n📅 {edited}"

    async def format_db_results(self, items: List[dict]) -> str:
        """Format database query results."""
        if not items: return "Нет записей."
        lines = []
        for item in items:
            title = _get_page_title(item)
            props = item.get("properties", {})
            status = props.get("Status", {}).get("select", {})
            status_name = status.get("name", "") if status else ""
            icon = {"Todo": "🔴", "In Progress": "🟡", "Done": "✅"}.get(status_name, "•")
            lines.append(f"{icon} {title}" + (f" [{status_name}]" if status_name else ""))
        return "\n".join(lines)


def _get_page_title(page: dict) -> str:
    props = page.get("properties", {})
    for key in ("Name", "Title", "title"):
        v = props.get(key, {})
        if "title" in v and v["title"]:
            return v["title"][0].get("plain_text", "Без названия")
        if "name" in v and v["name"]:
            return v["name"][0].get("plain_text", "Без названия")
    title_obj = page.get("title", [])
    if title_obj:
        return title_obj[0].get("plain_text", "Без названия")
    return "Без названия"


def _text_block(type_: str, content: str) -> dict:
    return {
        "object": "block",
        "type": type_,
        type_: {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }

def _md_to_blocks(text: str) -> list:
    """Convert simple markdown/text to Notion blocks."""
    blocks = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(_text_block("heading_1", line[2:]))
        elif line.startswith("## "):
            blocks.append(_text_block("heading_2", line[3:]))
        elif line.startswith("### "):
            blocks.append(_text_block("heading_3", line[4:]))
        elif re.match(r'^[-*•]\s', line):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text",
                    "text": {"content": re.sub(r'^[-*•]\s', '', line)[:2000]}}]},
            })
        elif re.match(r'^\d+\.\s', line):
            blocks.append({
                "object": "block", "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"type": "text",
                    "text": {"content": re.sub(r'^\d+\.\s', '', line)[:2000]}}]},
            })
        elif line.startswith("```") or line.startswith("    "):
            blocks.append({
                "object": "block", "type": "code",
                "code": {"rich_text": [{"type": "text", "text": {"content": line.strip("`").strip()[:2000]}}],
                         "language": "plain text"},
            })
        elif line.startswith("---") or line.startswith("==="):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif line.startswith("> "):
            blocks.append({
                "object": "block", "type": "quote",
                "quote": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]},
            })
        else:
            blocks.append(_text_block("paragraph", line))
    return blocks[:100]  # Notion max 100 blocks per request


# ── Intent parsing helpers for Notion ─────────────────────
def parse_notion_intent(text: str, action: str) -> dict:
    """Extract title and content from user message for Notion."""
    text = text.strip()
    # Remove common prefixes
    for prefix in ["создай в notion", "создай notion", "notion создай", "добавь в notion",
                   "запиши в notion", "сохрани в notion", "create in notion", "notion:"]:
        text = re.sub(re.escape(prefix), "", text, flags=re.I).strip()

    # Try to detect title vs content
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        title = lines[0][:100]
        content = "\n".join(lines[1:]) if len(lines) > 1 else ""
    else:
        title = text[:80] if text else "Новая запись"
        content = ""

    return {"title": title, "content": content}
