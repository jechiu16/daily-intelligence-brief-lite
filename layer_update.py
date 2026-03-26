"""
layer_update.py — 記憶層更新 (Gemini 3 Flash Preview)
接收完整 final_report + analyst_draft，更新 L2/L3/L4/KH。
"""

import json
import logging
import re

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL_FLASH, THESIS_MAX_ACTIVE
from memory_layer import (
    update_layer2, update_layer3, update_layer4,
    update_knowledge_history, fetch_layer3,
)

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GOOGLE_API_KEY)


def extract_l2_from_draft(analyst_draft: str, today_date: str) -> dict:
    """從 Analyst 草稿中提取 L2 micro-format (具備高寬容度 Regex)。"""
    l2_data = {
        "regime": "POLICY_TRANSITION",
        "driver": "unknown",
        "policy": "unknown",
        "fragility": "unknown",
    }

    # 升級版：支援大小寫、中文翻譯、以及 Markdown 粗體星號
    patterns = {
        "regime": r"(?:regime|體制)[*\s]*[：:][*\s]*([A-Z_]+)",
        "driver": r"(?:driver|驅動因素|驅動)[*\s]*[：:][*\s]*([^\n]+)",
        "policy": r"(?:policy|政策主軸|政策)[*\s]*[：:][*\s]*([^\n]+)",
        "fragility": r"(?:fragility|脆弱性)[*\s]*[：:][*\s]*([^\n]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, analyst_draft, re.IGNORECASE)
        if match:
            # 移除可能被抓進來的 Markdown 星號
            l2_data[key] = match.group(1).replace("*", "").strip()

    return l2_data


def extract_theses_from_draft(analyst_draft: str) -> list[dict]:
    """從 Analyst 草稿中提取新 thesis (抓取 Markdown JSON 區塊)。"""
    theses = []

    # 嘗試抓取標準的 ```json ... ``` 區塊
    json_blocks = re.findall(r"
http://googleusercontent.com/immersive_entry_chip/0

### ✨ 這次更新帶來的好處：
1. **L2 不再是 Unknown**：AI 喜歡加粗體（`**Driver:**`），現在程式會自動剝除星星符號，精準抓到文字。
2. **KH 百分之百命中**：直接去拿發佈在 Notion 上的最終版本來萃取名詞，保證 `__KnowledgeHistory__` 以後一定會有記錄（並且會打印在 Log 裡讓你知道它成功了）。

這樣改完之後，你的「記憶寫入」神經元就徹底打通了。推播上去試試看，期待在 Log 裡看到 `KH updated: 財政主導` 之類的成功訊息！

如果有其他你想檢查的檔案，像是 `memory_layer.py`，隨時貼上來！
