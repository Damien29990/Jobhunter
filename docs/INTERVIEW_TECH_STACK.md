# Jobhunter — 面試用技術棧說明

> 文件版本：2026-09-17  
> 對象：面試官／技術主管（約 5–8 分鐘口述）  
> 範圍：本倉庫**實際有在用**的技術，不是規劃中的清單。

`Jobhunter` 是一套跑在本機的香港 IT 求職多智能體系統：掃描可信職缺 → 僱主背調 → 量身履歷 PDF → 申請入口與證照審計。狀態全部落在本地 SQLite，儀表板只監控與觸發，不取代代理人寫入。

---

## 一句話怎麼講

「我做了一條 **五代理管線**：本地 **Ollama** 做履歷理解，**DeepSeek** 做推理，**Tavily** 做搜尋，**LangGraph + 純函式閘門** 管流程，**SQLite + sqlite-vec** 當共享記憶，前端是 **Vite + React 18** 的像素辦公室看板。閾值從不交給 LLM 猜。」

---

## 為什麼這樣選（面試常問 Why）

| 決策 | 實際選擇 | 理由 |
|------|----------|------|
| 為什麼不用 OpenAI | DeepSeek（OpenAI 相容 SDK，`base_url=https://api.deepseek.com`） | OpenAI 對香港回 403 |
| 為什麼不用雲端向量庫 | SQLite + `sqlite-vec` | 單機、可攜、無額外包；預設離線 lexical embedding |
| 為什麼分數不叫 LLM 決定 | `gates.py` / `pipeline_gates.py` 純函式 | 可重現、可測、儀表板不必載入 sqlite-vec／openai |
| 為什麼履歷不是 Word 範本 | Jinja2 → Typst CLI → PDF | 版面可程式化、可重試編譯錯誤 |
| 為什麼有兩套編排 | 儀表板用 **subprocess**；排程用 **LangGraph** | 手動重跑要獨立行程與真實 CLI；夜間全管線要條件邊與 checkpoint |
| Canvas 是不是 Canva | **不是** | `templates/canvas/` 是本地 Typst 版面目錄 |

---

## 系統一覽

```
候選人主檔 JSON          Tavily / 官網 / Wikipedia
        │                         │
        ▼                         ▼
   Milo (Ollama) ──PAC──► Rex (DeepSeek) ──職缺──► SQLite + sqlite-vec
                                                     │
                              Dana (背調) ◄──────────┤ composite ≥ 80
                                                     │
                              Leo (Typst PDF) ◄──────┤ verdict = PROCEED
                                                     │
                              Clara (申請包) ◄───────┤ CV 已編譯
                                                     ▼
                              FastAPI :8000  ◄──►  Vite :5173
                              APScheduler 香港 09:00 / 18:00
                              Telegram Bot（可選）
```

---

## 我用了什麼（依層列出）

### 語言與執行環境

| 項目 | 實際使用 |
|------|----------|
| 後端語言 | **Python 3.11+**（conda 環境 `jobhunter`） |
| 套件管理 | `pip`（`requirements.txt`、`src/api/requirements.txt`） |
| 前端語言 | **JavaScript（JSX）**，不是 TypeScript |
| 前端執行 | **Node 20.9+**、`npm` |
| 本機啟動 | `run_dashboard.bat`；FastAPI `127.0.0.1:8000`；Vite `5173`（`/api` proxy） |
| 時區 | **Asia/Hong_Kong（UTC+8）** ISO 8601，`tzdata` + `ZoneInfo` |

### 多智能體編排

| 角色 | 程式 | 職責 |
|------|------|------|
| **Milo** | `src/agents/milo_intake.py` | 匯入 CV、本機 Ollama 對話、寫 `ProfileAcceptanceContext` |
| **Rex** | `src/agents/talent_scout_agent_2.py` | 去識別化、跨產業搜尋軌道、Tavily、雙分數入庫 |
| **Dana** | `src/agents/due_diligence_agent.py` | 僱主研究、`PROCEED` / `AVOID` dossier |
| **Leo** | `src/agents/cv_generator_agent.py` | 依事實改寫履歷、Jinja2 + Typst 出 PDF |
| **Clara** | `src/agents/cert_matcher_agent.py` | 申請頻道偵測、證照對齊、申請清單 |

共用函式庫：`src/agents/talent_scout_agent.py`（`JobDBManager`、可信來源、DeepSeek 客戶端、URL／雇主解析）。

**三種跑法**

1. 各代理 CLI 單獨重跑  
2. 儀表板「執行」→ `agent_runner.py` **subprocess**（IDLE / WORKING / FAILED）  
3. **LangGraph** `StateGraph`：`milo → rex → dana → leo（Typst 最多重試 3 次）→ clara`，`MemorySaver` checkpoint；條件邊在 `src/validators/pipeline_gates.py`

### 模型與外部 API（我實際呼叫的）

| 服務 | 套件／協定 | 用途 |
|------|------------|------|
| **DeepSeek** | `openai` SDK，預設 `deepseek-v4-flash` | Rex／Dana／Leo／Clara 結構化推理 |
| **Tavily** | `tavily-python` Search + Extract | 職缺搜尋、僱主新聞／官網 |
| **Ollama** | `http://localhost:11434/api/generate`，預設 `gemma4:e2b` | Milo 解析 CV、聊天、技能建議 |
| **Wikipedia / Wikidata** | `httpx` | Dana 無 Tavily 或 `DUE_DILIGENCE_BACKEND=official` |
| **Telegram Bot API** | `httpx`，MarkdownV2 | 可選進度與漏斗摘要 |
| **JSON 修復** | `json-repair` | 修 LLM 尾逗號、截斷 JSON |

金鑰只放 `.env`：`DEEPSEEK_API_KEY`（可別名 `OPENAI_API_KEY`）、`TAVILY_API_KEY`、可選 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`。

### 資料與驗證

| 項目 | 實際使用 |
|------|----------|
| 主庫 | 根目錄 `job_agent.db`（SQLite） |
| 向量 | `sqlite-vec` 虛擬表 `vec_job_postings`，`embedding float[1536]` |
| 嵌入 | 預設離線 **lexical feature-hashing**；可選 `fastembed` + `BAAI/bge-small-en-v1.5` |
| 契約 | **Pydantic v2**（`BaseModel`、`Field`、validator；API 模型禁用 `Any`） |
| 主要表 | `job_postings`、`company_dossiers`、`research_search_cache`（14 天）、`milo_chat_history` |
| HTTP | `httpx`（職缺存活檢查、官網、Telegram） |

### 確定性閘門（可當「我怎麼控風險」來講）

數值不由模型決定，封裝成純函式（`src/api/gates.py`、`src/validators/pipeline_gates.py`）：

| 規則 | 值 |
|------|----|
| 綜合分 | hard 55% + transfer 45% |
| Rex 入庫 | 綜合 ≥ 75 **或** 可遷移 ≥ 85 |
| Dana／Leo／Clara 池 | **只看綜合 ≥ 80**（Dana 沒有 85 分後門） |
| Leo 再開做 | 綜合 ≥ 80 **且** `vetting_verdict = PROCEED` |
| Clara 再開做 | `cv_status = MATERIALS_GENERATED` |
| 看板主列 | 綜合 ≥ 35；更低進「擱置」 |

另外：職缺 URL／標題過濾（Phenom、JobsDB 等）、申請入口分類（Workday、Greenhouse、JobsDB…）都是規則，不是 prompt。

### 履歷產出

| 步驟 | 技術 |
|------|------|
| 內容 | DeepSeek → `TailoredCVPayload`（**只准主檔事實**） |
| 選版 | `cv_canvas.py` 依 JD 關鍵字：`classic` / `compact` / `technical` |
| 渲染 | **Jinja2**（`StrictUndefined`） |
| 編譯 | 本機 **Typst CLI** `subprocess` |
| 下載檔名 | `{職位}_{姓名}_cv.pdf` |

### 儀表板

| 層 | 實際使用 |
|----|----------|
| API | **FastAPI** ≥0.115、**Uvicorn**、`python-multipart` |
| 查詢 | SQLite `mode=ro`；過期／擱置旗標另開寫入連線 |
| UI | **Vite 6** + **React 18.3** + **Tailwind CSS 3.4** |
| 圖示 | `lucide-react` |
| 語系 | `i18next` + `react-i18next`（en、zh-HK） |
| 看板 | 自製 Kanban（**沒有** Recharts、**沒有** TanStack Table、**沒有** Next.js） |
| 辦公室動畫 | 自製 20×12 瓷磚 + **A\*** + `requestAnimationFrame`（只動 `transform` / `opacity`） |

儀表板寫入範圍刻意很小：職缺 `expired` / `user_status`、候選人 JSON、Milo 匯入履歷。職缺／dossier／PDF 路徑由代理人寫。

### 排程與通知

- **APScheduler** `BackgroundScheduler` + `CronTrigger`，預設香港時間 09:00、18:00  
- 排程執行完整 LangGraph，不是只跑單一代理  
- Telegram 沒設 token 就靜默跳過，管線照跑  

### 測試

- **pytest**，目錄 `tests/`  
- 覆蓋閘門、URL 過濾、Canvas 選版、檔名、Telegram 格式、PAC／Milo、金鑰別名等  
- 不測真實 DeepSeek／Tavily 帳單呼叫  

---

## 架構原則（可當「你怎麼設計系統」）

1. **LLM 只產內容，閘門是程式。** 分數、Verdict、ATS 入口、版型選擇都是純函式。  
2. **代理人擁有寫入。** FastAPI 預設唯讀，避免 UI 與代理人搶同一條寫交易。  
3. **去識別化才出站。** Rex 送 DeepSeek／Tavily 前剝姓名、電郵、電話、雇主專有名詞。  
4. **Ground truth。** Leo／Clara 系統提示禁止捏造學歷、雇主、證照。  
5. **可單獨重跑。** 每個代理可指定公司或職缺，SQLite 當訊息匯流排。  
6. **本機優先。** 職缺與 PDF 不上雲；金鑰不進 git。

---

## 目錄對照（面試官想看 code 時）

| 主題 | 路徑 |
|------|------|
| 閘門常數 | `src/api/gates.py` |
| LangGraph 拓樸 | `src/agents/pipeline_graph.py` |
| 共用 DB／評分 | `src/agents/talent_scout_agent.py` |
| FastAPI | `src/api/server.py` |
| 儀表板 | `frontend/src/` |
| 版面清單 | `templates/canvas/manifest.json` |
| 依賴 | `requirements.txt`、`src/api/requirements.txt`、`frontend/package.json` |
| 操作說明 | 根目錄 `README.md` |

---

## 依賴速查（套件名）

**Python：** `openai`、`pydantic` v2、`tavily-python`、`httpx`、`sqlite-vec`、`python-dotenv`、`tzdata`、`json-repair`、`langgraph`、`langchain-core`、`apscheduler`、`pypdf`、`fastapi`、`uvicorn`、`python-multipart`、`jinja2`（履歷渲染）。

**前端：** `react` 18.3、`react-dom`、`vite` 6、`tailwindcss` 3.4、`i18next`、`react-i18next`、`lucide-react`。

**本機二進位（非 pip）：** Typst CLI、Ollama。

---

## 刻意沒做、避免講錯

- 不是 Next.js 16、不是 React 19、沒有 shadcn / Recharts / TanStack Table  
- 沒有接 **Canva.com**（只有本地叫 Canvas 的 Typst 目錄）  
- FastAPI **沒有使用者登入**——單機本機工具  
- 沒有雲端 queue（Redis / Celery）；排程是行程內 APScheduler  

---

## 建議口述 60 秒稿

「這是給香港 IT 求職的本機多智能體。Milo 用本機 Ollama 讀履歷；Rex 用 Tavily 在 JobsDB、ATS、企業職缺站搜，DeepSeek 打硬技能與可遷移兩條分數，用 55／45 合成，過閘才入 SQLite。Dana 只看綜合分 80 以上做背調。過關才讓 Leo 用 Jinja 加 Typst 出 PDF，Clara 用規則辨申請入口並核對真實證照。儀表板是 FastAPI 加 React Kanban，夜間用 LangGraph 加 APScheduler 在香港時區跑兩次。我把『模型負責寫』和『程式負責放行』拆開，所以分數和狀態機能用 pytest 測。」
