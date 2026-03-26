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
    """從 Analyst 草稿中提取 L2 micro-format。"""
    # 嘗試直接解析草稿中的 L2 部分
    l2_data = {
        "regime": "POLICY_TRANSITION",
        "driver": "unknown",
        "policy": "unknown",
        "fragility": "unknown",
    }

    # 用 regex 嘗試提取
    patterns = {
        "regime": r"regime:\s*(\S+)",
        "driver": r"driver:\s*(.+?)(?:\n|$)",
        "policy": r"policy:\s*(.+?)(?:\n|$)",
        "fragility": r"fragility:\s*(.+?)(?:\n|$)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, analyst_draft, re.IGNORECASE)
        if match:
            l2_data[key] = match.group(1).strip()

    return l2_data


def extract_theses_from_draft(analyst_draft: str) -> list[dict]:
    """從 Analyst 草稿中提取新 thesis。"""
    theses = []

    # 嘗試找到 JSON 格式的 thesis
    json_pattern = r'\{[^{}]*"name"[^{}]*"statement"[^{}]*\}'
    matches = re.finditer(json_pattern, analyst_draft, re.DOTALL)

    for match in matches:
        try:
            thesis = json.loads(match.group())
            # 驗證必要欄位
            if all(k in thesis for k in ("name", "statement")):
                thesis.setdefault("status", "active")
                thesis.setdefault("confidence", 0.5)
                thesis.setdefault("assets", [])
                thesis.setdefault("invalidators", [])
                thesis.setdefault("time_horizon", "2w")
                theses.append(thesis)
        except json.JSONDecodeError:
            continue

    return theses


def extract_attack_from_draft(analyst_draft: str) -> tuple[str, str]:
    """從 Analyst 草稿中提取攻擊記錄。"""
    attack_type = "unknown"
    attack_content = ""

    # 尋找攻擊類型
    type_patterns = [
        r"攻擊類型[：:]\s*(\S+)",
        r"regime_misclassification",
        r"second_order_inversion",
        r"reflexivity_break",
        r"omitted_variable_bias",
    ]

    for pattern in type_patterns:
        match = re.search(pattern, analyst_draft)
        if match:
            attack_type = match.group(1) if match.lastindex else match.group()
            break

    # 尋找攻擊內容
    content_match = re.search(r"攻擊內容[：:]\s*(.+?)(?:\n\n|\n##|$)",
                               analyst_draft, re.DOTALL)
    if content_match:
        attack_content = content_match.group(1).strip()[:500]

    return attack_type, attack_content


def extract_term_from_draft(analyst_draft: str) -> str:
    """從 Analyst 草稿中提取今日術語建議。"""
    # 嘗試在「今日術語建議」段落找術語名稱
    match = re.search(r"今日術語.+?[：:]\s*(.+?)(?:\n|$)", analyst_draft)
    if match:
        term = match.group(1).strip()
        # 清理
        term = re.sub(r"[（(].*?[）)]", "", term).strip()
        term = term.split("，")[0].split(",")[0].strip()
        return term[:50]
    return ""


def run_layer_update(
    analyst_draft: str,
    final_report: str,
    hard_truths: dict,
    today_date: str,
):
    """執行所有記憶層更新。"""
    logger.info("Running Layer Update...")

    # 1. L2 更新
    try:
        l2_data = extract_l2_from_draft(analyst_draft, today_date)
        update_layer2(
            date=today_date,
            regime=l2_data["regime"],
            driver=l2_data["driver"],
            policy=l2_data["policy"],
            fragility=l2_data["fragility"],
        )
        logger.info(f"L2 updated: {l2_data}")
    except Exception as e:
        logger.error(f"L2 update failed: {e}")

    # 2. L3 Thesis 更新
    try:
        existing = fetch_layer3()
        new_theses = extract_theses_from_draft(analyst_draft)

        # 合併：先保留現有 active，再加入新的
        active = [t for t in existing if t.get("status") == "active"]

        for new_t in new_theses[:2]:  # 每日最多新增 2 個
            new_t["date"] = today_date
            active.append(new_t)

        # 上限 5 個 active
        if len(active) > THESIS_MAX_ACTIVE:
            # 按 confidence 排序，保留前 5
            active.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            active = active[:THESIS_MAX_ACTIVE]

        # 加入非 active 的保留
        inactive = [t for t in existing if t.get("status") != "active"]
        all_theses = active + inactive[-10:]  # 保留最近 10 個非 active

        update_layer3(all_theses)
        logger.info(f"L3 updated: {len(active)} active, {len(inactive)} inactive")
    except Exception as e:
        logger.error(f"L3 update failed: {e}")

    # 3. L4 攻擊記錄
    try:
        attack_type, attack_content = extract_attack_from_draft(analyst_draft)
        if attack_content:
            update_layer4(today_date, attack_type, attack_content)
            logger.info(f"L4 updated: {attack_type}")
    except Exception as e:
        logger.error(f"L4 update failed: {e}")

    # 4. KH 術語歷史
    try:
        term = extract_term_from_draft(analyst_draft)
        if term:
            update_knowledge_history(term, today_date)
            logger.info(f"KH updated: {term}")
    except Exception as e:
        logger.error(f"KH update failed: {e}")

    logger.info("Layer Update complete")
