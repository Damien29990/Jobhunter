---
type: jobhunter-doc
kind: architecture
---

# Architecture

- 地圖：[[Jobhunter docs]]
- 流程：[[Pipeline]]
- 資料庫：[[Database]]
- 全文：[[Root README]]

共用庫：`src/agents/talent_scout_agent.py`（可信來源、`JobDBManager`、DeepSeek 客戶端、URL／雇主解析、雙分數純函式）。

兩種編排：

1. 儀表板：`src/api/agent_runner.py` **subprocess**（真實 CLI）
2. 排程：`src/agents/pipeline_graph.py` **LangGraph**（條件邊、checkpoint）

```mermaid
flowchart LR
  Milo --> Rex --> Dana --> Leo --> Clara
```

閘門是程式，不是 prompt。見 [[Pipeline]] 與面試稿 [[Interview tech stack]]。
