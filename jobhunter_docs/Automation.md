---
type: jobhunter-doc
kind: automation
---

# Automation

- 地圖：[[Jobhunter docs]]
- 編排：[[Architecture]]
- 全文：[[Root README]]

`src/api/scheduler.py`：香港時間預設 09:00、18:00。Telegram：`src/api/telegram_notifier.py`。沒有 bot token 就跳過通知。用量見代理結束時的 `agent_runs` 與 [[Dashboard]] 用量面板。
