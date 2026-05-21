# Daily Intelligence Brief — v9 Lite

每天早上 10-15 分鐘，用一篇高品質日報讀懂世界發生了什麼。

---

## 讀者定位

受過良好教育、關心世界局勢，但不一定有金融、總經或地緣政治背景的一般讀者。
讀完後的感覺：「我知道今天世界的主線是什麼，也順手多認識了一個被主流新聞忽略的角落。」

---

## 架構總覽

```
GitHub Actions (每日 UTC 23:00)
        │
        ▼
    main.py → pipeline.py (9 步流程)
        │
        ├── data_layer.py ─────── 10+ API 資料源
        ├── hard_truths.py ────── Regime 分類
        ├── relational_guardrail ─ 9 條跨資產規則 (純 Python)
        ├── analyst.py ────────── Gemini 3.5 Flash + Grounding
        ├── logic_guardrail.py ── Gemini Flash (事實校驗)
        ├── narrator.py ───────── Gemini 3.5 Flash (主筆改寫)
        ├── layer_update.py ───── 記憶層更新
        └── memory_layer.py ───── Notion (L1-L4, KH)
```

## 快速開始

### 1. 申請 API Keys

| 服務 | 說明 | 連結 |
|---|---|---|
| Google AI Studio | Gemini API | https://aistudio.google.com/apikey |
| FRED | 經濟資料 | https://fred.stlouisfed.org/docs/api/api_key.html |
| EIA | 原油 (選填) | https://www.eia.gov/opendata/ |
| Notion | Integration | https://www.notion.so/my-integrations |

### 2. 設定 Notion

1. 建立 Database（表格），只需 `title` 欄位
2. 建立 Integration，分享 Database 給它
3. 記下 Database ID

### 3. 本地測試

```bash
cp .env.example .env   # 填入 API keys
pip install -r requirements.txt
python setup_notion.py  # 初始化 Notion 頁面
python main.py test-data
python main.py daily
```

### 4. GitHub 部署

Settings → Secrets → 加入 5 個 key → Push → Actions 手動觸發

---

## 報告結構

| 段落 | 字數 | 目的 |
|---|---|---|
| 一、今天的世界 | 50 | 一句話 |
| 二、數字說了什麼 | 250 | 5 個數字 + 白話 |
| 三、為什麼會這樣 | 600 | 因果鏈 |
| 四、這跟我們有什麼關係 | 300 | 理解世界，不做喊單 |
| 五、今日邊陲 | 300 | 真正邊陲的世界一角 |
| 六、今日一件事 | 200 | 學一個小知識 |

---

*v9-lite — 2026-03-24*
