---
type: jobhunter-doc
kind: setup
---

# Setup

- 地圖：[[Jobhunter docs]]
- 操作：[[Usage]]
- 全文：[[Root README]]

Python 3.11+（conda `jobhunter`）、DeepSeek key、Typst CLI。Rex 需要 Tavily。Dana 預設 official，可不填 Tavily。

```cmd
conda activate jobhunter
pip install -r requirements.txt
copy .env.example .env
run_dashboard.bat
```

FastAPI `http://127.0.0.1:8000`，Vite `http://127.0.0.1:5174`（以 `frontend/vite.config.js` 為準）。金鑰只放 `.env`。
