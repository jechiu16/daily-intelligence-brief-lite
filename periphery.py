"""
periphery.py — 邊陲訊號系統

每天選一個資訊密度較低、主流媒體較少深入處理的地方。
這個欄位的價值不是補充大國新聞，而是讓日報保留世界感。
"""

import datetime
import hashlib

PERIPHERY_SELECTION_RULE = (
    "邊陲必須避開已被主流資訊淹沒的大國與金融中心；優先選邊境地帶、"
    "小國、內陸走廊、港口、礦區、糧食帶、航道、島嶼與治理破碎地區。"
)


PERIPHERY_POOL: list[tuple[str, str]] = [
    ("薩赫勒三角地帶",      "Sahel Mali Niger Burkina Faso security governance"),
    ("查德湖盆地",          "Lake Chad Basin security climate displacement"),
    ("幾內亞灣海盜帶",      "Gulf of Guinea piracy oil shipping security"),
    ("蘇丹達佛與科爾多凡",  "Sudan Darfur Kordofan RSF SAF humanitarian"),
    ("索馬利亞邦特蘭",      "Puntland Somalia piracy Islamic State shipping"),
    ("索馬利蘭",            "Somaliland Berbera port Ethiopia recognition"),
    ("衣索比亞奧羅米亞",    "Ethiopia Oromia conflict economy"),
    ("莫三比克德爾加杜角",  "Cabo Delgado Mozambique LNG insurgency"),
    ("馬達加斯加南部",      "southern Madagascar drought food security"),
    ("葛摩與莫三比克海峽",  "Comoros Mozambique Channel shipping gas geopolitics"),
    ("剛果銅鈷礦帶",        "DRC Katanga copper cobalt mining power shortages"),
    ("尚比亞銅帶",          "Zambia Copperbelt debt power mining"),
    ("安哥拉洛比托走廊",    "Lobito Corridor Angola Zambia DRC railway copper"),
    ("圭亞那內陸與離岸油田","Guyana Essequibo offshore oil Venezuela border"),
    ("蘇利南離岸油氣",      "Suriname offshore oil politics economy"),
    ("秘魯南部礦區",        "southern Peru mining protests copper"),
    ("玻利維亞鋰鹽湖",      "Bolivia lithium salt flats politics extraction"),
    ("巴拉圭大豆邊境",      "Paraguay soybean Brazil border hydropower"),
    ("貝里斯與瓜地馬拉邊境","Belize Guatemala border dispute Caribbean"),
    ("達連隘口",            "Darien Gap migration Panama Colombia"),
    ("瓜地馬拉高地",        "Guatemala highlands migration drought coffee"),
    ("緬甸撣邦與若開",      "Myanmar Shan Rakhine civil war rare earth ports"),
    ("克欽稀土礦區",        "Kachin Myanmar rare earth mining China border"),
    ("孟加拉吉大港丘陵",    "Chittagong Hill Tracts Bangladesh insurgency"),
    ("俾路支走廊",          "Balochistan Gwadar CPEC insurgency"),
    ("吉爾吉斯塔吉克邊境",  "Kyrgyzstan Tajikistan border water conflict"),
    ("費爾干納谷地",        "Fergana Valley water borders Central Asia"),
    ("卡拉卡爾帕克斯坦",    "Karakalpakstan Aral Sea Uzbekistan autonomy"),
    ("亞美尼亞南部走廊",    "Syunik Armenia Zangezur corridor Azerbaijan"),
    ("喬治亞黑海港口",      "Georgia Black Sea Anaklia port EU Russia"),
    ("摩爾多瓦德涅斯特河左岸","Transnistria Moldova energy security"),
    ("波士尼亞塞族共和國",  "Republika Srpska Bosnia secession EU"),
    ("科索沃北部",          "northern Kosovo Serbia tensions municipalities"),
    ("塞浦路斯綠線",        "Cyprus Green Line gas Turkey EU"),
    ("黎巴嫩南部",          "southern Lebanon border economy Hezbollah Israel"),
    ("伊拉克辛賈爾",        "Sinjar Iraq Yazidi militias Turkey PKK"),
    ("敘利亞東北部",        "northeast Syria oil wheat SDF Turkey"),
    ("約旦河谷",            "Jordan Valley water agriculture security"),
    ("葉門塔伊茲與荷台達",  "Yemen Taiz Hodeidah Red Sea humanitarian"),
    ("阿曼杜庫姆港",        "Duqm Oman port Indian Ocean logistics"),
    ("亞丁灣小港口",        "Gulf of Aden ports shipping security"),
    ("紅海西岸港口",        "Eritrea Sudan Red Sea ports shipping"),
    ("吉布地港口群",        "Djibouti ports military bases debt"),
    ("馬爾地夫海上通道",    "Maldives Indian Ocean debt climate China India"),
    ("安達曼尼科巴外海",    "Andaman Nicobar Bay of Bengal shipping chokepoint"),
    ("湄公河下游三角洲",    "Mekong Delta salinity rice climate Vietnam Cambodia"),
    ("寮國水壩走廊",        "Laos Mekong dams debt electricity Thailand"),
    ("東帝汶大日昇氣田",    "Timor-Leste Greater Sunrise gas Australia"),
    ("巴布亞紐幾內亞高地",  "Papua New Guinea highlands LNG tribal conflict"),
    ("索羅門群島",          "Solomon Islands ports China Australia politics"),
    ("新喀里多尼亞鎳礦",    "New Caledonia nickel unrest France"),
    ("斐濟與太平洋海底電纜","Fiji Pacific subsea cables geopolitics"),
]


def select_periphery(date: datetime.date | None = None) -> tuple[str, str]:
    """根據日期 hash 選擇今日邊陲地區。"""
    if date is None:
        date = datetime.date.today()
    idx = int(hashlib.md5(str(date).encode()).hexdigest(), 16) % len(PERIPHERY_POOL)
    return PERIPHERY_POOL[idx]
