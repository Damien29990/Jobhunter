---
type: jobhunter-doc
kind: database
---

# Database

- 地圖：[[Jobhunter docs]]
- 流程：[[Pipeline]]
- 欄位全文：[[Root README]]

單一檔 `job_agent.db`（SQLite + `sqlite-vec`）。

| 表 | 誰寫 | 連到 |
|----|------|------|
| `job_postings` | [[Rex]]、[[Leo]]、[[Clara]] | [[Jobs]] 資料夾筆記 |
| `vec_job_postings` | [[Rex]] | 職缺向量 |
| `company_dossiers` | [[Dana]] | [[Companies]] 資料夾筆記 |
| `research_search_cache` | [[Dana]] | 14 天快取 |
| `milo_chat_history` | [[Milo]] | PAC／聊天 |
| `agent_runs` | 各代理結束時 | tokens、Tavily credits |

Obsidian 匯出：`src/agents/obsidian_vault.py` 把公司與職缺寫成 `[[wikilink]]`。
