# Jobhunter

本機香港 IT 求職多智能體（Milo → Rex → Dana → Leo → Clara）。狀態在 `job_agent.db`。

**完整說明與雙向連結在 [`jobhunter_docs/`](jobhunter_docs/Jobhunter%20docs.md)。** 舊 README 全文：[`jobhunter_docs/Archives/Root README.md`](jobhunter_docs/Archives/Root%20README.md)。

把 Obsidian vault 指到 `output/obsidian` 時，啟動 FastAPI 或管線會把 `jobhunter_docs` 同步進去，並與 `Companies/`、`Jobs/`、`Skills/` 相連。入口筆記：`jobhunter_docs/Jobhunter docs.md`。

## 啟動

```cmd
conda activate jobhunter
copy .env.example .env
run_dashboard.bat
```

- 安裝與指令：[jobhunter_docs/Setup.md](jobhunter_docs/Setup.md)、[Usage.md](jobhunter_docs/Usage.md)
- 儀表板：[Dashboard.md](jobhunter_docs/Dashboard.md)
- 面試：[Interview.md](jobhunter_docs/Interview.md)
