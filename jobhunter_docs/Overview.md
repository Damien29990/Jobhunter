---
type: jobhunter-doc
kind: overview
---

# Overview

- 地圖：[[Jobhunter docs]]
- 架構：[[Architecture]]
- 全文：[[Root README]]

Jobhunter 是本機香港 IT 求職多智能體。狀態只落在 `job_agent.db` 與 `output/`。

| 代理 | 筆記 | 程式 |
|------|------|------|
| 0 | [[Milo]] | `src/agents/milo_intake.py` |
| 1 | [[Rex]] | `src/agents/talent_scout_agent_2.py` |
| 2 | [[Dana]] | `src/agents/due_diligence_agent.py` |
| 3 | [[Leo]] | `src/agents/cv_generator_agent.py` |
| 4 | [[Clara]] | `src/agents/cert_matcher_agent.py` |

DeepSeek 取代 OpenAI（香港 403）。Rex 搜尋用 Tavily。Dana 預設 `DUE_DILIGENCE_BACKEND=official`（Wikipedia／官網），不必經 Tavily。
