"""
setup_notion.py — 初始化 Notion 記憶層頁面
第一次部署時執行一次即可。
用 httpx 直接呼叫 Notion REST API。
"""

import logging
import sys

import httpx

from config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_PAGES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def setup():
    """在 Notion database 中建立所有記憶層頁面。"""

    for layer_name, page_title in NOTION_PAGES.items():
        logger.info(f"Checking {layer_name}: {page_title}")

        # 檢查是否已存在
        try:
            resp = httpx.post(
                f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query",
                headers=NOTION_HEADERS,
                json={
                    "filter": {
                        "property": "title",
                        "title": {"equals": page_title}
                    }
                },
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            if results:
                logger.info(f"  ✅ Already exists: {page_title}")
                continue
        except Exception as e:
            logger.error(f"  ❌ Query failed: {e}")
            continue

        # 建立頁面
        initial_content = {
            "__WeeklyCompressed__": "",
            "__LongTermTracker__": "[]",
            "__DevilsAdvocateLog__": "",
            "__KnowledgeHistory__": "[]",
        }
        content = initial_content.get(page_title, "")

        try:
            resp = httpx.post(
                f"{NOTION_API}/pages",
                headers=NOTION_HEADERS,
                json={
                    "parent": {"database_id": NOTION_DATABASE_ID},
                    "properties": {
                        "title": {
                            "title": [{"text": {"content": page_title}}]
                        }
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "code",
                            "code": {
                                "rich_text": [{"text": {"content": content}}],
                                "language": "json"
                            }
                        }
                    ]
                },
                timeout=30,
            )
            resp.raise_for_status()
            page_id = resp.json()["id"]
            logger.info(f"  ✅ Created: {page_title} (ID: {page_id})")
        except Exception as e:
            logger.error(f"  ❌ Create failed: {e}")
            # 印出完整錯誤方便除錯
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"     Response: {e.response.text}")

    logger.info("Notion setup complete!")


if __name__ == "__main__":
    setup()
