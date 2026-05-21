# Daily Intelligence Brief Lite

每天自動產出一篇輕量、高品質的世界日報。

這不是研究系統，也不是投資建議機器。它的目標很單純：用少量可靠數字、一條清楚主線、一個真正邊陲的世界角落，加上一個小知識，幫讀者理解今天世界正在發生什麼。

## Product Shape

讀者是受過良好教育、關心世界局勢，但不一定有金融、總經或地緣政治背景的一般讀者。

文章應該像一位有世界感的專欄作者寫的短文：

- 清楚，但不幼化
- 有數字，但不被數字淹沒
- 有市場，但不喊單
- 有地緣政治，但不故作玄奧
- 有邊陲知識，讓讀者每天多認識世界一角

讀完後的感覺應該是：

> 我知道今天世界的主線是什麼，也順手多懂了一個主流新聞不太照到的地方或概念。

## Daily Structure

| 段落 | 目的 |
|---|---|
| 今天的世界 | 用 2-3 句話說出今天的主線 |
| 數字說了什麼 | 只選 3-5 個真正支撐主線的數字 |
| 為什麼會這樣 | 把市場、政策、能源、地緣或社會變化串成因果鏈 |
| 這跟我們有什麼關係 | 幫讀者理解世界，不提供投資指令 |
| 今日邊陲 | 固定保留，必須是真正被主流資訊忽略的地方 |
| 今日一件事 | 一個金融、地理、能源、糧食、治理或社會小知識 |

## Editorial Principles

### 1. One Main Thread

每天只抓一條主線，不追求把所有資料都塞進文章。資料是支撐文章的骨架，不是文章本身。

### 2. Real Periphery

「今日邊陲」是這份日報的辨識度，不是裝飾。

邊陲選題刻意避開已經被資訊淹沒的中心：

- 不把 G7、中國、台灣、華爾街、矽谷、Fed、歐盟核心當成邊陲主角
- 優先選邊境地帶、小國、內陸走廊、港口、礦區、糧食帶、航道、島嶼、治理破碎地區
- 如果和今天市場沒有直接關係，文章必須坦白說沒有直接關係，不硬湊

### 3. One Useful Concept

「今日一件事」使用混合式候選池：

- `knowledge_terms.py` 提供 curated 小知識池
- pipeline 會依今日主線、regime、邊陲 keywords 和已用術語挑 8 個候選
- Analyst 優先從候選池選詞
- 如果候選池不適合，LLM 可以自產，但必須和今日主線或邊陲有明確關係
- KH 會避免近期重複

### 4. Lightweight Memory

Notion 記憶層只服務文章品質：

- L1：昨日摘要
- L2：最近市場結構
- L3：後續追蹤線索
- L4：反面思考紀錄
- KH：已講過的小知識

它不是完整研究資料庫。更重的研究工作應該放在別的系統。

## Architecture

```text
GitHub Actions
        |
        v
main.py
        |
        +-- preflight.py          # secrets + FRED key health check
        +-- pipeline.py           # daily / weekly orchestration
                |
                +-- data_layer.py          # market and macro inputs
                +-- hard_truths.py         # derived facts + regime
                +-- relational_guardrail.py# pure Python cross-asset flags
                +-- periphery.py           # true-periphery selector
                +-- knowledge_terms.py     # curated "today's concept" pool
                +-- analyst.py             # story angle + structured draft
                +-- logic_guardrail.py     # fact consistency check
                +-- narrator.py            # final article voice
                +-- memory_layer.py        # Notion read/write
                +-- layer_update.py        # memory updates
```

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env`:

```bash
cp .env.example .env
```

Run a health check:

```bash
python main.py doctor
```

Test data collection:

```bash
python main.py test-data
```

Run the daily brief:

```bash
python main.py daily
```

Run for a specific date:

```bash
python main.py daily --date 2026-05-21
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Required Secrets

For GitHub Actions, configure these repository secrets:

| Secret | Required | Purpose |
|---|---:|---|
| `GOOGLE_API_KEY` | Yes | Gemini generation |
| `FRED_API_KEY` | Yes | macro and rates data |
| `NOTION_TOKEN` | Yes | Notion write target |
| `NOTION_DATABASE_ID` | Yes | Notion database |
| `EIA_API_KEY` | No | optional energy data |

`python main.py doctor` checks required values and validates the FRED key without printing secret values.

## GitHub Actions

Workflow: `.github/workflows/daily-brief.yml`

- Scheduled at UTC 23:00, which is Taiwan morning
- Uses `Asia/Taipei` for the report date
- Runs preflight before daily generation
- Uses concurrency so overlapping runs do not stack up
- Timeout is 30 minutes
- Supports manual commands:
  - `daily`
  - `weekly`
  - `test-data`
  - `test-regime`

## Models

Configured in `config.py`:

```python
MODEL_ANALYST = "gemini-3.5-flash"
MODEL_FLASH = "gemini-3.5-flash"
MODEL_NARRATOR = "gemini-3.5-flash"
```

## Notion Setup

1. Create a Notion database with a `Name` title property.
2. Create a Notion integration.
3. Share the database with the integration.
4. Put the integration token and database ID into `.env` or GitHub Secrets.
5. Run:

```bash
python setup_notion.py
```

Optional database properties used by the app:

- `Date`
- `Regime`
- `Type`
- `Periphery`

If these properties are missing, report creation has a fallback path, but the cleanest setup is to include them.

## Tests

The test suite covers:

- Taiwan date handling
- preflight missing env and invalid FRED key paths
- hard truth missing-data tolerance
- logic guardrail fail-closed behavior
- Notion patch failure behavior
- editorial positioning
- true-periphery constraints
- knowledge-term candidate selection

Run:

```bash
python -m unittest discover -s tests -v
```

## Design Bias

When in doubt, optimize for:

1. A better article
2. Fewer brittle data dependencies
3. Clearer failure messages
4. Less investment-report energy
5. More world texture

This repo should remain lite.
