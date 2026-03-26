"""
memory_layer.py — 記憶層 (L1-L4, KH) via Notion
"""

import datetime
import json
import re
import logging
from typing import Optional

from notion_client import Client

from config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_PAGES

logger = logging.getLogger(__name__)

notion = Client(auth=NOTION_TOKEN)


# ─────────────────────────────────────────────────────────────────────
# Notion 工具函數
# ─────────────────────────────────────────────────────────────────────

def _find_page_by_title(title: str) -> Optional[str]:
    """在 database 中找到指定 title 的 page，返回 page_id。"""
    try:
        results = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "property": "title",
                "title": {"equals": title}
            }
        )
        if results["results"]:
            return results["results"][0]["id"]
    except Exception as e:
        logger.error(f"Notion query error for '{title}': {e}")
    return None


def _get_page_content(page_id: str) -> str:
    """取得 page 的純文字內容。"""
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
        text_parts = []
        for block in blocks["results"]:
            block_type = block["type"]
            if block_type in ("paragraph", "heading_1", "heading_2", "heading_3",
                             "bulleted_list_item", "numbered_list_item"):
                rich_texts = block[block_type].get("rich_text", [])
                text = "".join(rt["plain_text"] for rt in rich_texts)
                text_parts.append(text)
            elif block_type == "code":
                rich_texts = block["code"].get("rich_text", [])
                text = "".join(rt["plain_text"] for rt in rich_texts)
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Notion get content error: {e}")
        return ""


def _create_page(title: str, content: str) -> Optional[str]:
    """在 database 中建立新 page。"""
    try:
        page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "title": {
                    "title": [{"text": {"content": title}}]
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
        return page["id"]
    except Exception as e:
        logger.error(f"Notion create page error: {e}")
        return None


def _update_page_content(page_id: str, content: str):
    """更新 page 內容（刪除舊 blocks，寫入新 block）。"""
    try:
        # 刪除所有舊 blocks
        old_blocks = notion.blocks.children.list(block_id=page_id)
        for block in old_blocks["results"]:
            try:
                notion.blocks.delete(block_id=block["id"])
            except Exception:
                pass

        # 寫入新內容
        notion.blocks.children.append(
            block_id=page_id,
            children=[
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"text": {"content": content[:2000]}}],
                        "language": "json"
                    }
                }
            ]
        )
    except Exception as e:
        logger.error(f"Notion update error: {e}")


# ─────────────────────────────────────────────────────────────────────
# L1: 昨日報告（動態提取）
# ─────────────────────────────────────────────────────────────────────

def strip_report_formatting(text: str, max_chars: int = 2000) -> str:
    """L1 fallback 用。過濾格式噪音，只保留段落文字。"""
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if re.match(r"^-{3,}$", s):
            continue
        if re.match(r"^\*\*\d{4}年", s):
            continue
        if s.startswith("📋"):
            break  # 停在固定結尾前
        lines.append(s)
    content = "\n".join(lines)
    return content[:max_chars] + "…" if len(content) > max_chars else content


def fetch_layer1(yesterday_report: Optional[str] = None) -> dict:
    """
    L1 提取三件事：
    1. 昨日「今天的世界」一句話
    2. 昨日「今日一件事」的術語名稱
    3. 昨日「今天我需要做什麼嗎？」的結論
    """
    result = {
        "yesterday_headline": "",
        "yesterday_term": "",
        "yesterday_action": "",
    }

    if not yesterday_report:
        # 嘗試從 Notion 取得昨天的報告
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        title = f"DIB_{yesterday.isoformat()}"
        page_id = _find_page_by_title(title)
        if page_id:
            yesterday_report = _get_page_content(page_id)

    if not yesterday_report:
        return result

    # 簡易提取（不用 LLM 的 fallback 版）
    lines = yesterday_report.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        # 今天的世界
        if "今天的世界" in s and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and not next_line.startswith("#"):
                result["yesterday_headline"] = next_line[:200]

        # 今日一件事
        if "今日一件事" in s and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line:
                # 提取術語名稱（通常是 **粗體** 或第一個詞）
                match = re.search(r"\*\*(.+?)\*\*", next_line)
                if match:
                    result["yesterday_term"] = match.group(1)
                else:
                    result["yesterday_term"] = next_line[:50]

        # 今天我需要做什麼嗎？
        if "需要做什麼" in s:
            # 取下一行非空行
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith("#"):
                    result["yesterday_action"] = next_line[:200]
                    break

    return result


# ─────────────────────────────────────────────────────────────────────
# L2: 週壓縮
# ─────────────────────────────────────────────────────────────────────

def fetch_layer2() -> str:
    """取得 L2 週壓縮資料。"""
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    if page_id:
        return _get_page_content(page_id)
    return ""


def update_layer2(date: str, regime: str, driver: str,
                  policy: str, fragility: str):
    """追加一條 L2 micro-format 記錄。保留最近 7 天。"""
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    existing = ""
    if page_id:
        existing = _get_page_content(page_id)

    new_entry = f"{date}\nregime: {regime}\ndriver: {driver}\npolicy: {policy}\nfragility: {fragility}"

    # 解析現有條目，保留最近 7 天
    entries = existing.strip().split("\n\n") if existing.strip() else []
    entries.append(new_entry)

    # 只保留最近 7 條
    if len(entries) > 7:
        entries = entries[-7:]

    content = "\n\n".join(entries)

    if page_id:
        _update_page_content(page_id, content)
    else:
        _create_page(NOTION_PAGES["L2"], content)


# ─────────────────────────────────────────────────────────────────────
# L3: Thesis 追蹤
# ─────────────────────────────────────────────────────────────────────

def fetch_layer3() -> list[dict]:
    """取得所有 active thesis。"""
    page_id = _find_page_by_title(NOTION_PAGES["L3"])
    if not page_id:
        return []

    content = _get_page_content(page_id)
    if not content:
        return []

    try:
        theses = json.loads(content)
        if isinstance(theses, list):
            return [t for t in theses if t.get("status") == "active"]
        return []
    except json.JSONDecodeError:
        return []


def update_layer3(theses: list[dict]):
    """更新 thesis 列表。"""
    page_id = _find_page_by_title(NOTION_PAGES["L3"])
    content = json.dumps(theses, ensure_ascii=False, indent=2)

    if page_id:
        _update_page_content(page_id, content)
    else:
        _create_page(NOTION_PAGES["L3"], content)


# ─────────────────────────────────────────────────────────────────────
# L4: Devil's Advocate Log
# ─────────────────────────────────────────────────────────────────────

def fetch_layer4() -> str:
    """取得攻擊記錄。"""
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    if page_id:
        return _get_page_content(page_id)
    return ""


def update_layer4(date: str, attack_type: str, content: str):
    """追加攻擊記錄。保留 14 天。"""
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    existing = ""
    if page_id:
        existing = _get_page_content(page_id)

    new_entry = json.dumps({
        "date": date,
        "type": attack_type,
        "content": content
    }, ensure_ascii=False)

    entries = existing.strip().split("\n") if existing.strip() else []
    entries.append(new_entry)

    # 保留最近 14 條
    if len(entries) > 14:
        entries = entries[-14:]

    content_str = "\n".join(entries)

    if page_id:
        _update_page_content(page_id, content_str)
    else:
        _create_page(NOTION_PAGES["L4"], content_str)


# ─────────────────────────────────────────────────────────────────────
# KH: Knowledge History（術語歷史）
# ─────────────────────────────────────────────────────────────────────

def fetch_knowledge_history() -> list[dict]:
    """取得已解釋過的術語列表。"""
    page_id = _find_page_by_title(NOTION_PAGES["KH"])
    if not page_id:
        return []

    content = _get_page_content(page_id)
    if not content:
        return []

    try:
        history = json.loads(content)
        if isinstance(history, list):
            return history[-20:]  # 只保留最近 20 筆
        return []
    except json.JSONDecodeError:
        return []


def update_knowledge_history(term: str, date: str):
    """追加一個術語到 KH。"""
    history = fetch_knowledge_history()
    history.append({"term": term, "date": date})

    # 只保留最近 20 筆
    if len(history) > 20:
        history = history[-20:]

    page_id = _find_page_by_title(NOTION_PAGES["KH"])
    content = json.dumps(history, ensure_ascii=False, indent=2)

    if page_id:
        _update_page_content(page_id, content)
    else:
        _create_page(NOTION_PAGES["KH"], content)


# ─────────────────────────────────────────────────────────────────────
# 儲存今日報告
# ─────────────────────────────────────────────────────────────────────

def save_daily_report(date: str, report: str):
    """將今日報告存到 Notion。"""
    title = f"DIB_{date}"
    page_id = _find_page_by_title(title)

    if page_id:
        _update_page_content(page_id, report)
    else:
        _create_page(title, report)

    logger.info(f"Report saved to Notion: {title}")
