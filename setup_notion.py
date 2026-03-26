"""
setup_notion.py — 初始化 Notion 記憶層頁面
第一次部署時執行一次即可。
"""

import json
import logging
import sys

from notion_client import Client

from config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_PAGES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup():
    """在 Notion database 中建立所有記憶層頁面。"""
    notion = Client(auth=NOTION_TOKEN)

    for layer_name, page_title in NOTION_PAGES.items():
        logger.info(f"Checking {layer_name}: {page_title}")

        # 檢查是否已存在
        results = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "property": "title",
                "title": {"equals": page_title}
            }
        )

        if results["results"]:
            logger.info(f"  ✅ Already exists: {page_title}")
            continue

        # 建立頁面
        initial_content = {
            "__WeeklyCompressed__": "",
            "__LongTermTracker__": "[]",
            "__DevilsAdvocateLog__": "",
            "__KnowledgeHistory__": "[]",
        }

        content = initial_content.get(page_title, "")

        page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "title": {
                    "title": [{"text": {"content": page_title}}]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"text": {"content": content}}],
                        "language": "json"
                    }
                }
            ]
        )

        logger.info(f"  ✅ Created: {page_title} (ID: {page['id']})")

    logger.info("Notion setup complete!")


if __name__ == "__main__":
    setup()
