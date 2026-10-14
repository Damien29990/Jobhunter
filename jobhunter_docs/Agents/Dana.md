---
type: jobhunter-doc
kind: agent
agent: Dana
---

# Dana

- 地圖：[[Jobhunter docs]]
- 上一站：[[Rex]] · 下一站：[[Leo]]
- 公司筆記：`Companies/`
- 閘門：[[Pipeline]]

`src/agents/due_diligence_agent.py`。預設 `official` 搜網（Wikipedia／Wikidata／官網），不經 Tavily。自動管線只研究 **未有 dossier** 且綜合 ≥80 的僱主。強制重跑：`--force-refresh` 或單一 job。產出 `PROCEED`／`AVOID`，連到 `Companies/` 筆記。
