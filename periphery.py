"""
periphery.py — 邊陲訊號系統
32 個地區池，每天根據日期 hash 選一個。
"""

import datetime
import hashlib

PERIPHERY_POOL: list[tuple[str, str]] = [
    ("薩赫勒 + 西非",      "Sahel West Africa security governance"),
    ("高加索",             "Caucasus Armenia Azerbaijan Georgia conflict"),
    ("緬甸內戰",           "Myanmar civil war junta resistance"),
    ("葉門",               "Yemen Houthi Red Sea conflict ceasefire"),
    ("伊拉克 + 敘利亞",    "Iraq Syria border militia Iran proxy"),
    ("黎巴嫩重建",         "Lebanon reconstruction Hezbollah economy"),
    ("利比亞",             "Libya fragmentation warlords oil"),
    ("蘇丹內戰",           "Sudan civil war RSF SAF humanitarian"),
    ("索馬利亞",           "Somalia Horn of Africa al-Shabaab"),
    ("越南",               "Vietnam manufacturing FDI supply chain"),
    ("孟加拉",             "Bangladesh garment political transition"),
    ("衣索比亞",           "Ethiopia economy reconstruction growth"),
    ("哈薩克",             "Kazakhstan energy China Russia"),
    ("墨西哥",             "Mexico nearshoring manufacturing US trade"),
    ("印尼",               "Indonesia nickel EV supply chain"),
    ("奈及利亞",           "Nigeria oil currency reform economy"),
    ("剛果銅鈷礦帶",       "DRC Congo copper cobalt mining China"),
    ("智利阿根廷鋰三角",   "Chile Argentina lithium EV battery"),
    ("哈薩克烏茲別克鈾礦", "Kazakhstan Uzbekistan uranium nuclear"),
    ("圭亞那",             "Guyana offshore oil ExxonMobil"),
    ("莫三比克 LNG",       "Mozambique LNG insurgency Cabo Delgado"),
    ("麻六甲海峽",         "Malacca Strait shipping chokepoint"),
    ("博斯普魯斯 + 黑海",  "Bosphorus Black Sea Turkey grain Ukraine"),
    ("巴拿馬運河",         "Panama Canal drought water shipping"),
    ("亞丁灣 + 紅海",     "Aden Gulf Red Sea Houthi shipping"),
    ("湄公河",             "Mekong River China dams downstream water"),
    ("東非農業帶",         "East Africa drought food security"),
    ("巴基斯坦",           "Pakistan climate economy IMF"),
    ("泰國政治",           "Thailand politics judiciary military"),
    ("秘魯玻利維亞",       "Peru Bolivia resource nationalism mining"),
    ("塞爾維亞",           "Serbia EU Russia Balkans geopolitics"),
    ("喬治亞",             "Georgia democracy protests EU"),
]


def select_periphery(date: datetime.date | None = None) -> tuple[str, str]:
    """根據日期 hash 選擇今日邊陲地區。"""
    if date is None:
        date = datetime.date.today()
    idx = int(hashlib.md5(str(date).encode()).hexdigest(), 16) % len(PERIPHERY_POOL)
    return PERIPHERY_POOL[idx]
