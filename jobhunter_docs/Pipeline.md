---
type: jobhunter-doc
kind: pipeline
---

# Pipeline

- 地圖：[[Jobhunter docs]]
- 代理：[[Milo]] · [[Rex]] · [[Dana]] · [[Leo]] · [[Clara]]
- 表：[[Database]]

| 從 | 到 | 閘門 |
|----|----|------|
| [[Rex]] | `job_postings` | 綜合 ≥75 **或** 可遷移 ≥85 才當高質；Dana 池只看綜合 ≥80 |
| [[Dana]] | `company_dossiers` | 自動管線只查 **未有 dossier** 的 ≥80 公司 |
| [[Leo]] | PDF | 綜合 ≥80 **且** `PROCEED` |
| [[Clara]] | 申請清單 | `cv_status = MATERIALS_GENERATED` |

看板主列綜合 ≥35。分數函式在 `src/api/gates.py`、`src/validators/pipeline_gates.py`。
