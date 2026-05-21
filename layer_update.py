"""
layer_update.py — 記憶層更新 (Gemini 3 Flash Preview)
接收完整 final_report + analyst_draft，更新 L2/L3/L4/KH。
"""

import json
import logging
import re

from config import THESIS_MAX_ACTIVE
from memory_layer import (
    update_layer2, update_layer3, update_layer4,
    update_knowledge_history, fetch_layer3,
)

logger = logging.getLogger(__name__)


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

    # 💡 終極修復：避免在字串中使用連續三個反引號，防止複製貼上時被截斷
    marker = "`" * 3
    pattern = marker + r"(?:json)?\s*(\{.*?\}|\[.*?\])\s*" + marker
    
    json_blocks = re.findall(pattern, analyst_draft, re.DOTALL | re.IGNORECASE)
    
    for block in json_blocks:
        try:
            parsed_data = json.loads(block)
            # AI 可能回傳單一 dict，也可能回傳 list of dicts
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]
                
            for thesis in parsed_data:
                if isinstance(thesis, dict) and "name" in thesis and "statement" in thesis:
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

    type_patterns = [
        r"攻擊類型[*\s]*[：:][*\s]*(\S+)",
        r"regime_misclassification",
        r"second_order_inversion",
        r"reflexivity_break",
        r"omitted_variable_bias",
    ]

    for pattern in type_patterns:
        match = re.search(pattern, analyst_draft, re.IGNORECASE)
        if match:
            attack_type = match.group(1).replace("*", "") if match.lastindex else match.group().replace("*", "")
            break

    content_match = re.search(r"攻擊內容[*\s]*[：:][*\s]*(.+?)(?:\n\n|\n##|$)",
                               analyst_draft, re.DOTALL | re.IGNORECASE)
    if content_match:
        attack_content = content_match.group(1).replace("*", "").strip()[:500]

    return attack_type, attack_content


def extract_term_from_report(final_report: str) -> str:
    """改從 '最終報告' 中提取今日一件事 (因為 Narrator 的格式更穩定)。"""
    # 尋找 "# 今日一件事：名詞" 的格式
    match = re.search(r"今日(?:一件事|術語)[*\s]*[：:][*\s]*([^\n*]+)", final_report)
    if match:
        term = match.group(1).strip()
        # 清理刮號內的解釋，只保留純名詞
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

        active = [t for t in existing if t.get("status") == "active"]

        for new_t in new_theses[:2]:  # 每日最多新增 2 個
            new_t["date"] = today_date
            active.append(new_t)

        if len(active) > THESIS_MAX_ACTIVE:
            active.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            active = active[:THESIS_MAX_ACTIVE]

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
        else:
            logger.info("L4 skip: 沒有偵測到攻擊內容。")
    except Exception as e:
        logger.error(f"L4 update failed: {e}")

    # 4. KH 術語歷史
    try:
        term = extract_term_from_report(final_report)
        if term:
            update_knowledge_history(term, today_date)
            logger.info(f"KH updated: {term}")
        else:
            logger.warning("KH skip: 在 final_report 中找不到今日一件事的名詞。")
    except Exception as e:
        logger.error(f"KH update failed: {e}")

    logger.info("Layer Update complete")
