"""
memory_layer.py — 記憶層 (L1-L4, KH) via Notion REST API
支援 Notion 原生格式（heading, paragraph, bullet）和 database property。
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
# Markdown → Notion Blocks 轉換器
# ─────────────────────────────────────────────────────────────────────

def _markdown_to_rich_text(text: str) -> list:
    """將 markdown inline 格式轉成 Notion rich_text array。
    支援 **粗體** 和普通文字。"""
    parts = []
    pattern = r'\*\*(.+?)\*\*'
    last_end = 0

    for match in re.finditer(pattern, text):
        # 粗體前的普通文字
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                parts.append({"type": "text", "text": {"content": plain}})
        # 粗體文字
        parts.append({
            "type": "text",
            "text": {"content": match.group(1)},
            "annotations": {"bold": True}
        })
        last_end = match.end()

    # 剩餘普通文字
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            parts.append({"type": "text", "text": {"content": remaining}})

    return parts if parts else [{"type": "text", "text": {"content": text}}]


def _markdown_to_blocks(markdown: str) -> list:
    """將 markdown 文字轉成 Notion block array。"""
    blocks = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 空行跳過
        if not stripped:
            i += 1
            continue

        # --- 分隔線
        if re.match(r'^-{3,}$', stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:].strip()
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": _markdown_to_rich_text(text)}
            })
            i += 1
            continue

        # ## H2
        if stripped.startswith("## "):
            text = stripped[3:].strip()
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": _markdown_to_rich_text(text)}
            })
            i += 1
            continue

        # ### H3
        if stripped.startswith("### "):
            text = stripped[4:].strip()
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": _markdown_to_rich_text(text)}
            })
            i += 1
            continue

        # - bullet list 或 * bullet list
        if re.match(r'^[-*]\s+', stripped):
            text = re.sub(r'^[-*]\s+', '', stripped)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _markdown_to_rich_text(text)}
            })
            i += 1
            continue

        # 1. numbered list
        if re.match(r'^\d+\.\s+', stripped):
            text = re.sub(r'^\d+\.\s+', '', stripped)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _markdown_to_rich_text(text)}
            })
            i += 1
            continue

        # > quote / callout
        if stripped.startswith("> "):
            text = stripped[2:].strip()
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": _markdown_to_rich_text(text),
                    "icon": {"type": "emoji", "emoji": "💡"}
                }
            })
            i += 1
            continue

        # 📋 特殊結尾 → callout
        if stripped.startswith("📋"):
            callout_lines = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip():
                callout_lines.append(lines[i].strip())
                i += 1
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": _markdown_to_rich_text("\n".join(callout_lines)),
                    "icon": {"type": "emoji", "emoji": "📋"}
                }
            })
            continue

        # 普通段落 — 收集連續非空行
        para_lines = [stripped]
        i += 1
        while i < len(lines):
            next_stripped = lines[i].strip()
            if (not next_stripped or next_stripped.startswith("#") or
                next_stripped.startswith("- ") or next_stripped.startswith("* ") or
                re.match(r'^\d+\.\s+', next_stripped) or
                next_stripped.startswith("> ") or next_stripped.startswith("📋") or
                re.match(r'^-{3,}$', next_stripped)):
                break
            para_lines.append(next_stripped)
            i += 1

        text = "\n".join(para_lines)
        if len(text) > 1900:
            for chunk_start in range(0, len(text), 1900):
                chunk = text[chunk_start:chunk_start + 1900]
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _markdown_to_rich_text(chunk)}
                })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _markdown_to_rich_text(text)}
            })

    return blocks[:100] if blocks else [
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "text": {"content": ""}}]}}
    ]


# ─────────────────────────────────────────────────────────────────────
# Notion REST API 工具函數
# ─────────────────────────────────────────────────────────────────────

def _find_page_by_title(title: str) -> Optional[str]:
    try:
        resp = httpx.post(
            f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query",
            headers=NOTION_HEADERS,
            json={"filter": {"property": "Name", "title": {"equals": title}}},
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
            rich_text_key = block.get(block_type, {})
            if "rich_text" in rich_text_key:
                text = "".join(rt["plain_text"] for rt in rich_text_key["rich_text"])
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Notion get content error: {e}")
        return ""


def _get_blocks_for_content(content: str, is_code: bool) -> list:
    """根據是否為 code block，自動把長文字切塊並包裝成 Notion Block"""
    chunks = [content[i:i + 1900] for i in range(0, max(len(content), 1), 1900)]
    if is_code:
        return [{
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": c}} for c in chunks],
                "language": "json"
            }
        }]
    else:
        return [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": c}}]}
        } for c in chunks]


def _create_page_simple(title: str, content: str, is_code: bool = False) -> Optional[str]:
    """建立簡單頁面（記憶層用）。可選擇是否建立 Code Block。"""
    try:
        blocks = _get_blocks_for_content(content, is_code)

        resp = httpx.post(
            f"{NOTION_API}/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": title}}]}
                },
                "children": blocks[:100]
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception as e:
        logger.error(f"Notion create page error: {e}")
        raise


def _update_page_content(page_id: str, content: str, is_code: bool = False):
    """更新頁面內容（記憶層用）。可選擇是否替換為 Code Block。"""
    try:
        resp = httpx.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=NOTION_HEADERS, timeout=30,
        )
        resp.raise_for_status()
        for block in resp.json().get("results", []):
            delete_resp = httpx.delete(f"{NOTION_API}/blocks/{block['id']}",
                                       headers=NOTION_HEADERS, timeout=15)
            delete_resp.raise_for_status()

        blocks = _get_blocks_for_content(content, is_code)

        patch_resp = httpx.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": blocks[:100]},
            timeout=30,
        )
        patch_resp.raise_for_status()
    except Exception as e:
        logger.error(f"Notion update error: {e}")
        raise


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
        title = f"Daily Brief | {yesterday.isoformat()}"
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
# L2-L4, KH（記憶層）
# ─────────────────────────────────────────────────────────────────────

def fetch_layer2() -> str:
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    if page_id:
        return _get_page_content(page_id)
    return ""


def update_layer2(date, regime, driver, policy, fragility):
    page_id = _find_page_by_title(NOTION_PAGES["L2"])
    existing = _get_page_content(page_id) if page_id else ""

    new_entry = f"{date}\nregime: {regime}\ndriver: {driver}\npolicy: {policy}\nfragility: {fragility}"
    entries = existing.strip().split("\n\n") if existing.strip() else []
    entries.append(new_entry)
    if len(entries) > 7:
        entries = entries[-7:]
    content = "\n\n".join(entries)

    if page_id:
        _update_page_content(page_id, content, is_code=False)
    else:
        _create_page_simple(NOTION_PAGES["L2"], content, is_code=False)


def fetch_layer3() -> list[dict]:
    page_id = _find_page_by_title(NOTION_PAGES["L3"])
    if not page_id:
        return []
    content = _get_page_content(page_id)
    if not content:
        return []
    try:
        theses = json.loads(content)
        return [t for t in theses if t.get("status") == "active"] if isinstance(theses, list) else []
    except json.JSONDecodeError:
        return []


def update_layer3(theses):
    page_id = _find_page_by_title(NOTION_PAGES["L3"])
    content = json.dumps(theses, ensure_ascii=False, indent=2)
    if page_id:
        _update_page_content(page_id, content, is_code=True)
    else:
        _create_page_simple(NOTION_PAGES["L3"], content, is_code=True)


def fetch_layer4() -> str:
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    return _get_page_content(page_id) if page_id else ""


def update_layer4(date, attack_type, content):
    page_id = _find_page_by_title(NOTION_PAGES["L4"])
    existing = _get_page_content(page_id) if page_id else ""

    new_entry = json.dumps({"date": date, "type": attack_type, "content": content}, ensure_ascii=False)
    entries = existing.strip().split("\n") if existing.strip() else []
    entries.append(new_entry)
    if len(entries) > 14:
        entries = entries[-14:]

    if page_id:
        _update_page_content(page_id, "\n".join(entries), is_code=True)
    else:
        _create_page_simple(NOTION_PAGES["L4"], "\n".join(entries), is_code=True)


def fetch_knowledge_history() -> list[dict]:
    page_id = _find_page_by_title(NOTION_PAGES["KH"])
    if not page_id:
        return []
    content = _get_page_content(page_id)
    if not content:
        return []
    try:
        history = json.loads(content)
        return history[-20:] if isinstance(history, list) else []
    except json.JSONDecodeError:
        return []


def update_knowledge_history(term, date):
    history = fetch_knowledge_history()
    history.append({"term": term, "date": date})
    if len(history) > 20:
        history = history[-20:]

    page_id = _find_page_by_title(NOTION_PAGES["KH"])
    content = json.dumps(history, ensure_ascii=False, indent=2)
    if page_id:
        _update_page_content(page_id, content, is_code=True)
    else:
        _create_page_simple(NOTION_PAGES["KH"], content, is_code=True)


# ─────────────────────────────────────────────────────────────────────
# 儲存今日報告（Markdown → Notion 原生格式 + property 分類）
# ─────────────────────────────────────────────────────────────────────

def save_daily_report(date: str, report: str,
                      regime: str = "", periphery: str = ""):
    title = f"Daily Brief | {date}"
    page_id = _find_page_by_title(title)

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
    }

    try:
        properties["Date"] = {"date": {"start": date}}
    except Exception:
        pass

    if regime:
        properties["Regime"] = {"select": {"name": regime}}
    properties["Type"] = {"select": {"name": "Daily"}}
    if periphery:
        properties["Periphery"] = {"rich_text": [{"text": {"content": periphery}}]}

    children = _markdown_to_blocks(report)

    if page_id:
        try:
            resp = httpx.patch(
                f"{NOTION_API}/pages/{page_id}",
                headers=NOTION_HEADERS,
                json={"properties": properties},
                timeout=30,
            )
            resp.raise_for_status()
            resp = httpx.get(f"{NOTION_API}/blocks/{page_id}/children",
                             headers=NOTION_HEADERS, timeout=30)
            resp.raise_for_status()
            for block in resp.json().get("results", []):
                delete_resp = httpx.delete(f"{NOTION_API}/blocks/{block['id']}",
                                           headers=NOTION_HEADERS, timeout=15)
                delete_resp.raise_for_status()
            resp = httpx.patch(
                f"{NOTION_API}/blocks/{page_id}/children",
                headers=NOTION_HEADERS,
                json={"children": children},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Notion update report error: {e}")
            raise
    else:
        try:
            resp = httpx.post(
                f"{NOTION_API}/pages",
                headers=NOTION_HEADERS,
                json={
                    "parent": {"database_id": NOTION_DATABASE_ID},
                    "properties": properties,
                    "children": children,
                },
                timeout=30,
            )
            resp.raise_for_status()
            logger.info(f"Report created in Notion: {title}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Notion create report error: {e}")
            logger.error(f"Response: {e.response.text}")
            try:
                fallback_props = {
                    "Name": {"title": [{"text": {"content": title}}]}
                }
                resp = httpx.post(
                    f"{NOTION_API}/pages",
                    headers=NOTION_HEADERS,
                    json={
                        "parent": {"database_id": NOTION_DATABASE_ID},
                        "properties": fallback_props,
                        "children": children,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                logger.info(f"Report created (fallback) in Notion: {title}")
            except Exception as e2:
                logger.error(f"Notion fallback create also failed: {e2}")
                raise
        except Exception as e:
            logger.error(f"Notion create report error: {e}")
            raise

    logger.info(f"Report saved to Notion: {title}")
