"""
memory_layer.py — 記憶層 (L1-L4, KH) via Notion REST API
直接用 httpx 呼叫 Notion API，不依賴 notion-client SDK 版本。
"""

import datetime
import json
import re
import logging
from typing import Optional

import httpx

from config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_PAGES

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


# ─────────────────────────────────────────────────────────────────────
# Notion REST API 工具函數
# ─────────────────────────────────────────────────────────────────────

def _find_page_by_title(title: str) -> Optional[str]:
    """在 database 中找到指定 title 的 page，返回 page_id。"""
    try:
        resp = httpx.post(
            f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "title",
                    "title": {"equals": title}
                }
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"]
    except Exception as e:
        logger.error(f"Notion query error for '{title}': {e}")
    return None


def _get_page_content(page_id: str) -> str:
    """取得 page 的純文字內容。"""
    try:
        resp = httpx.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        blocks = resp.json().get("results", [])

        text_parts = []
        for block in blocks:
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


def _split_to_blocks(content: str, max_chars: int = 1800) -> list[dict]:
    """將內容切成多個 block，每個不超過 max_chars。"""
    chunks = []
    while content:
        chunk = content[:max_chars]
        content = content[max_chars:]
        chunks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": chunk}}]
            }
        })
    return chunks if chunks else [{"object": "block", "type": "paragraph",
                                    "paragraph": {"rich_text": [{"text": {"content": ""}}]}}]


def _create_page(title: str, content: str) -> Optional[str]:
    """在 database 中建立新 page。"""
    try:
        children = _split_to_blocks(content)
        resp = httpx.post(
            f"{NOTION_API}/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": title}}]
                    }
                },
                "children": children
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception as e:
        logger.error(f"Notion create page error: {e}")
        return None


def _update_page_content(page_id: str, content: str):
    """更新 page 內容（刪除舊 blocks，寫入新 block）。"""
    try:
        resp = httpx.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        old_blocks = resp.json().get("results", [])

        for block in old_blocks:
            try:
                httpx.delete(
                    f"{NOTION_API}/blocks/{block['id']}",
                    headers=NOTION_HEADERS,
                    timeout=15,
                )
            except Exception:
                pass

        children = _split_to_blocks(content)
        httpx.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": children},
            timeout=30,
        )
    except Exception as e:
        logger.error(f"Notion update error: {e}")


# ─────────────────────────────────────────────────────────────────────
# L1: 昨日報告（動態提取）
# ─────────────────────────────────────────────────────────────────────

def strip_report_formatting(text: str, max_chars: int = 2000) -> str:
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
            break
        lines.append(s)
    content = "\n".join(lines)
    return content[:max_chars] + "…" if len(content) > max_chars else content


def fetch_layer1(yesterday_report: Optional[str] = None) -> dict:
    result = {
        "yesterday_headline": "",
        "yesterday_term": "",
        "yesterday_action": "",
    }

    if not yesterday_report:
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        title = f"DIB_{yesterday.isoformat()}"
        page_id = _find_page_by_title(title)
        if page_id:
            yesterday_report = _get_page_content(page_id)

    if not yesterday_report:
        return result

    lines = yesterday_report.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if "今天的世界" in s and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and not next_line.startswith("#"):
                result["yesterday_headline"] = next_line[:200]
        if "今日一件事" in s and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line:
                match = re.search(r"\*\*(.+?)\*\*", next_line)
                if match:
                    result["yesterday_term"] = match.group(1)
                else:
                    result["yesterday_term"] = next_line[:50]
        if "需要做什麼" in s:
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith("#"):
                    result["yesterday_action"] = next_line[:200]
                    break

    return result


# ─────────────────────────────────────────────────────────────────────
# L2-L4, KH
# ─────────────────────────────────────────────────────────────────────

def fetch_layer2() -> str:
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    if page_id:
        return _get_page_content(page_id)
    return ""


def update_layer2(date: str, regime: str, driver: str,
                  policy: str, fragility: str):
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    existing = ""
    if page_id:
        existing = _get_page_content(page_id)

    new_entry = f"{date}\nregime: {regime}\ndriver: {driver}\npolicy: {policy}\nfragility: {fragility}"
    entries = existing.strip().split("\n\n") if existing.strip() else []
    entries.append(new_entry)
    if len(entries) > 7:
        entries = entries[-7:]
    content = "\n\n".join(entries)

    if page_id:
        _update_page_content(page_id, content)
    else:
        _create_page(NOTION_PAGES["L2"], content)


def fetch_layer3() -> list[dict]:
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
    page_id = _find_page_by_title(NOTION_PAGES["L3"])
    content = json.dumps(theses, ensure_ascii=False, indent=2)
    if page_id:
        _update_page_content(page_id, content)
    else:
        _create_page(NOTION_PAGES["L3"], content)


def fetch_layer4() -> str:
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    if page_id:
        return _get_page_content(page_id)
    return ""


def update_layer4(date: str, attack_type: str, content: str):
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    existing = ""
    if page_id:
        existing = _get_page_content(page_id)

    new_entry = json.dumps({
        "date": date, "type": attack_type, "content": content
    }, ensure_ascii=False)
    entries = existing.strip().split("\n") if existing.strip() else []
    entries.append(new_entry)
    if len(entries) > 14:
        entries = entries[-14:]
    content_str = "\n".join(entries)

    if page_id:
        _update_page_content(page_id, content_str)
    else:
        _create_page(NOTION_PAGES["L4"], content_str)


def fetch_knowledge_history() -> list[dict]:
    page_id = _find_page_by_title(NOTION_PAGES["KH"])
    if not page_id:
        return []
    content = _get_page_content(page_id)
    if not content:
        return []
    try:
        history = json.loads(content)
        if isinstance(history, list):
            return history[-20:]
        return []
    except json.JSONDecodeError:
        return []


def update_knowledge_history(term: str, date: str):
    history = fetch_knowledge_history()
    history.append({"term": term, "date": date})
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
    title = f"DIB_{date}"
    page_id = _find_page_by_title(title)
    if page_id:
        _update_page_content(page_id, report)
    else:
        _create_page(title, report)
    logger.info(f"Report saved to Notion: {title}")
