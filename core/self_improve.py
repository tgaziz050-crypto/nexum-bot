import os, json, hashlib, aiohttp, logging
from datetime import datetime
from config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

PATCH_DIR = "patches"
os.makedirs(PATCH_DIR, exist_ok=True)

async def create_patch_suggestion(target_file:str, new_content:str, explanation:str):
    # сохраняем в patches/ уникальный файл
    digest = hashlib.sha1((target_file + new_content).encode()).hexdigest()[:8]
    fname = f"{PATCH_DIR}/{os.path.basename(target_file)}.{digest}.patch"
    content = f"# suggestion for {target_file}\n# explanation: {explanation}\n\n--- original: {target_file}\n+++ suggested: {target_file}\n\n{new_content}\n"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Patch suggestion written: %s", fname)
    return fname

async def create_github_pr(repo_full_name:str, branch_name:str, patch_file_path:str, title:str, body:str):
    """Опционально: создаёт PR используя GITHUB_TOKEN. ТОЛЬКО если GITHUB_TOKEN задан."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not configured")
    # Загружаем патч и создаём PR через GitHub API — реализация зависит от ветки и политики.
    # Здесь мы просто демонстрируем интерфейс: реальную логику применяй осторожно и вручную.
    raise NotImplementedError("Github PR creation is intentionally not implemented automatically. Use the patch file and create PR manually.")
