---
type: jobhunter-doc
kind: interview
---

# Interview

- 地圖：[[Jobhunter docs]]
- 原則：[[Architecture]] · [[Privacy]] · [[Pipeline]]
- 全文：[[Interview tech stack]]

一句話：本機五代理管線。[[Milo]] 用 Ollama 讀履歷；[[Rex]] 用 Tavily 搜、DeepSeek 打雙分數；[[Dana]] 背調；[[Leo]] Jinja+Typst 出 PDF；[[Clara]] 規則辨申請入口。儀表板 FastAPI + React。夜間 LangGraph + APScheduler。
