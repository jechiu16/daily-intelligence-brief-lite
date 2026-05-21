"""
knowledge_terms.py — 今日一件事候選池

這不是百科全書，而是日報的品味底盤：優先提供有世界感、
可用日常比喻說清楚、且不只侷限於金融的小知識詞彙。
"""

from __future__ import annotations


KNOWLEDGE_TERMS: list[dict[str, object]] = [
    {
        "term": "咽喉點",
        "category": "geography_shipping",
        "keywords": ["red sea", "malacca", "panama", "hormuz", "shipping", "canal", "strait", "gulf"],
        "description": "海上交通或能源運輸中，一旦受阻就會影響整條路線的狹窄通道。",
    },
    {
        "term": "事實國家",
        "category": "politics",
        "keywords": ["somaliland", "transnistria", "recognition", "separatism", "autonomy"],
        "description": "實際運作像國家，但未被多數國家正式承認的政治實體。",
    },
    {
        "term": "內陸走廊",
        "category": "geography_shipping",
        "keywords": ["corridor", "railway", "landlocked", "lobito", "cpec", "zangezur", "syunik"],
        "description": "把內陸礦區、農業區或國家接到港口與外部市場的交通路線。",
    },
    {
        "term": "轉運港",
        "category": "geography_shipping",
        "keywords": ["port", "berbera", "djibouti", "duqm", "gwadar", "shipment", "logistics"],
        "description": "貨物不一定在當地消費，而是在港口重新分流到下一段航線的節點。",
    },
    {
        "term": "海底電纜",
        "category": "infrastructure",
        "keywords": ["subsea cable", "cable", "pacific", "islands", "internet"],
        "description": "跨國網路與金融通訊仰賴的海底基礎設施。",
    },
    {
        "term": "戰略縱深",
        "category": "geopolitics",
        "keywords": ["border", "buffer", "valley", "security", "depth"],
        "description": "一個國家在核心區外保留緩衝空間，以降低外部衝擊直達核心的風險。",
    },
    {
        "term": "緩衝地帶",
        "category": "geopolitics",
        "keywords": ["buffer", "border", "green line", "valley", "demilitarized"],
        "description": "夾在兩個勢力之間、降低直接碰撞機率的空間。",
    },
    {
        "term": "飛地",
        "category": "geography",
        "keywords": ["enclave", "exclave", "border", "sinjar", "transnistria"],
        "description": "被其他政治或地理空間包圍、和本體不完全相連的區域。",
    },
    {
        "term": "凍結衝突",
        "category": "geopolitics",
        "keywords": ["frozen conflict", "transnistria", "kosovo", "armenia", "azerbaijan", "cyprus"],
        "description": "沒有正式和平，但大規模戰鬥暫停、政治問題長期懸而未決的衝突。",
    },
    {
        "term": "灰色地帶衝突",
        "category": "geopolitics",
        "keywords": ["militia", "proxy", "maritime", "hybrid", "border", "cyber"],
        "description": "介於和平與戰爭之間，利用民兵、資訊、法律或海上行動施壓的衝突。",
    },
    {
        "term": "代理人戰爭",
        "category": "geopolitics",
        "keywords": ["proxy", "militia", "iran", "houthi", "pkk", "hezbollah"],
        "description": "大國或區域強權透過在地武裝或盟友間接競爭。",
    },
    {
        "term": "治理真空",
        "category": "politics",
        "keywords": ["warlord", "militia", "insurgency", "ungoverned", "fragile"],
        "description": "政府無法有效提供安全、司法與公共服務時留下的權力空白。",
    },
    {
        "term": "國家能力",
        "category": "politics",
        "keywords": ["governance", "state capacity", "tax", "security", "public services"],
        "description": "政府把政策變成現實的能力，包括收稅、治安、基礎建設與危機處理。",
    },
    {
        "term": "民兵政治",
        "category": "politics",
        "keywords": ["militia", "rsf", "saf", "hezbollah", "pkk", "armed group"],
        "description": "武裝團體不只是打仗，也參與治理、分配資源與地方政治。",
    },
    {
        "term": "IMF 條件性",
        "category": "political_economy",
        "keywords": ["imf", "pakistan", "debt", "bailout", "conditionality"],
        "description": "國家取得 IMF 支援時，通常要承諾財政、匯率或補貼改革。",
    },
    {
        "term": "雙重匯率",
        "category": "political_economy",
        "keywords": ["currency", "black market", "parallel rate", "devaluation", "fx"],
        "description": "官方匯率和市場實際交易匯率並存，反映資本管制或外匯短缺。",
    },
    {
        "term": "黑市匯率",
        "category": "political_economy",
        "keywords": ["black market", "currency", "parallel", "naira", "devaluation"],
        "description": "當官方匯率無法反映供需時，民間形成的實際交易價格。",
    },
    {
        "term": "僑匯",
        "category": "society",
        "keywords": ["remittance", "migration", "diaspora", "labor"],
        "description": "海外工作者寄回家鄉的錢，常是許多國家家庭收入與外匯的重要來源。",
    },
    {
        "term": "非正式經濟",
        "category": "society",
        "keywords": ["informal economy", "street", "cash", "labor"],
        "description": "沒有完整登記、課稅或社會保障，但支撐大量日常生活的經濟活動。",
    },
    {
        "term": "人口紅利",
        "category": "society",
        "keywords": ["demographics", "youth", "population", "labor"],
        "description": "勞動人口占比高時，若教育與就業跟上，可能帶來成長窗口。",
    },
    {
        "term": "青年失業",
        "category": "society",
        "keywords": ["youth unemployment", "jobs", "protests", "demographics"],
        "description": "年輕人找不到工作時，經濟問題容易轉化為政治與社會壓力。",
    },
    {
        "term": "移民走廊",
        "category": "society",
        "keywords": ["migration", "darien", "border", "refugee", "route"],
        "description": "人口因戰爭、氣候或經濟壓力固定流動的跨境路線。",
    },
    {
        "term": "難民營經濟",
        "category": "society",
        "keywords": ["refugee", "camp", "displacement", "humanitarian"],
        "description": "長期難民營中形成的市場、服務、工作與援助依賴網絡。",
    },
    {
        "term": "關鍵礦物",
        "category": "energy_mining",
        "keywords": ["copper", "cobalt", "lithium", "nickel", "rare earth", "uranium", "mining"],
        "description": "對能源轉型、軍工或高科技供應鏈不可或缺，但供給集中或難以替代的原料。",
    },
    {
        "term": "銅鈷礦帶",
        "category": "energy_mining",
        "keywords": ["katanga", "copperbelt", "drc", "zambia", "cobalt", "copper"],
        "description": "剛果與尚比亞一帶的礦業帶，是全球銅與鈷供應的重要來源。",
    },
    {
        "term": "鋰鹽湖",
        "category": "energy_mining",
        "keywords": ["lithium", "salt flats", "brine", "bolivia", "argentina", "chile"],
        "description": "從高鹽地下水中提取鋰的礦區，常與水資源和地方政治糾纏。",
    },
    {
        "term": "稀土",
        "category": "energy_mining",
        "keywords": ["rare earth", "kachin", "magnet", "mining"],
        "description": "一組用於磁鐵、電動車、風機和軍工的金屬元素，開採與加工高度集中。",
    },
    {
        "term": "鈾燃料循環",
        "category": "energy_mining",
        "keywords": ["uranium", "nuclear", "kazakhstan", "fuel cycle"],
        "description": "鈾從開採、轉化、濃縮到核燃料製造的一整條核能供應鏈。",
    },
    {
        "term": "LNG 液化",
        "category": "energy",
        "keywords": ["lng", "gas", "mozambique", "greater sunrise", "duqm"],
        "description": "把天然氣降溫變成液態，方便用船跨海運輸的過程。",
    },
    {
        "term": "油氣特許權",
        "category": "energy",
        "keywords": ["offshore oil", "concession", "license", "guyana", "suriname"],
        "description": "政府授權企業在特定區域探勘與開採油氣的權利安排。",
    },
    {
        "term": "資源民族主義",
        "category": "energy_mining",
        "keywords": ["resource nationalism", "mining", "lithium", "copper", "oil"],
        "description": "政府希望提高本國對礦產、能源收益與控制權的政策傾向。",
    },
    {
        "term": "電網瓶頸",
        "category": "energy",
        "keywords": ["power", "grid", "electricity", "shortage", "mining"],
        "description": "能源不是沒有，而是輸電、配電或接入能力不足，限制經濟活動。",
    },
    {
        "term": "能源安全",
        "category": "energy",
        "keywords": ["energy security", "oil", "gas", "lng", "shipping", "pipeline"],
        "description": "一個國家能否穩定、可負擔地取得能源，不被外部中斷牽制。",
    },
    {
        "term": "糧食走廊",
        "category": "food_climate",
        "keywords": ["grain", "wheat", "food", "black sea", "corridor", "shipping"],
        "description": "讓糧食從產區通往港口、市場或受援地區的運輸路線。",
    },
    {
        "term": "雨養農業",
        "category": "food_climate",
        "keywords": ["rainfed", "drought", "agriculture", "sahel", "madagascar"],
        "description": "主要依靠降雨而非灌溉的農業，對氣候變化特別敏感。",
    },
    {
        "term": "鹽化",
        "category": "food_climate",
        "keywords": ["salinity", "mekong", "delta", "rice", "water"],
        "description": "海水或鹽分進入土壤與淡水，使農作物和飲用水受影響。",
    },
    {
        "term": "水壓力",
        "category": "food_climate",
        "keywords": ["water stress", "drought", "river", "dam", "canal"],
        "description": "用水需求接近或超過可用水量時，農業、工業與民生都會受壓。",
    },
    {
        "term": "水壩外交",
        "category": "food_climate",
        "keywords": ["dam", "mekong", "laos", "water", "downstream"],
        "description": "上游水壩如何影響下游國家的水、電、糧食與外交關係。",
    },
    {
        "term": "氣候遷徙",
        "category": "food_climate",
        "keywords": ["climate migration", "drought", "flood", "darien", "displacement"],
        "description": "氣候壓力使人離開原本居住地，常和經濟與安全問題交織。",
    },
    {
        "term": "久期",
        "category": "markets",
        "keywords": ["duration", "bond", "yield", "treasury", "rate"],
        "description": "衡量債券或資產價格對利率變化有多敏感的概念。",
    },
    {
        "term": "實質利率",
        "category": "markets",
        "keywords": ["real yield", "real rate", "inflation", "t10yie"],
        "description": "扣掉通膨後的利率，影響資金願意承擔風險的程度。",
    },
    {
        "term": "信用利差",
        "category": "markets",
        "keywords": ["credit spread", "hy", "ig", "baml", "stress"],
        "description": "企業或高風險借款人相對安全政府債多付的利率補償。",
    },
    {
        "term": "風險溢酬",
        "category": "markets",
        "keywords": ["risk premium", "equity", "spread", "uncertainty"],
        "description": "投資人承擔不確定性時，要求多拿到的補償。",
    },
    {
        "term": "美元流動性",
        "category": "markets",
        "keywords": ["dollar liquidity", "dxy", "funding", "offshore dollar"],
        "description": "全球金融系統中美元資金是否容易取得，會影響資產與新興市場壓力。",
    },
    {
        "term": "離岸美元",
        "category": "markets",
        "keywords": ["offshore dollar", "eurodollar", "funding", "dollar"],
        "description": "美國境外銀行與市場創造、借貸和流通的美元資金。",
    },
    {
        "term": "通膨預期",
        "category": "markets",
        "keywords": ["inflation expectation", "breakeven", "5y5y", "t5yifr"],
        "description": "市場或民眾對未來物價上漲速度的預期。",
    },
    {
        "term": "財政主導",
        "category": "markets",
        "keywords": ["fiscal dominance", "debt", "deficit", "treasury"],
        "description": "當財政壓力大到限制央行選擇時，貨幣政策會被債務問題牽著走。",
    },
    {
        "term": "金融條件",
        "category": "markets",
        "keywords": ["financial conditions", "yield", "dollar", "credit", "spx"],
        "description": "利率、匯率、信用與股市共同決定資金是寬鬆還是緊縮。",
    },
]


def _normalize_used_terms(used_terms: list[dict] | list[str] | None) -> set[str]:
    if not used_terms:
        return set()
    normalized = set()
    for item in used_terms:
        if isinstance(item, dict):
            term = item.get("term")
        else:
            term = item
        if term:
            normalized.add(str(term).strip())
    return normalized


def select_knowledge_candidates(
    context: str,
    used_terms: list[dict] | list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Pick a compact candidate list for the LLM to choose from."""
    used = _normalize_used_terms(used_terms)
    context_l = context.lower()
    scored: list[tuple[int, int, dict[str, object]]] = []

    for idx, item in enumerate(KNOWLEDGE_TERMS):
        term = str(item["term"])
        if term in used:
            continue

        keywords = [str(k).lower() for k in item.get("keywords", [])]
        score = sum(1 for keyword in keywords if keyword and keyword in context_l)

        # Keep some high-quality variety even when the context is sparse.
        if score > 0 or len(scored) < limit * 2:
            scored.append((score, -idx, item))

    scored.sort(reverse=True)
    candidates = []
    for _, _, item in scored[:limit]:
        candidates.append({
            "term": str(item["term"]),
            "category": str(item["category"]),
            "description": str(item["description"]),
        })
    return candidates


def format_knowledge_candidates(candidates: list[dict[str, str]]) -> str:
    if not candidates:
        return "（無候選詞；請自產一個符合規則的小知識詞彙）"
    return "\n".join(
        f"- {item['term']}｜{item['category']}｜{item['description']}"
        for item in candidates
    )
