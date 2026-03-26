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
