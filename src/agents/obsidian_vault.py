"""Obsidian export folder under output/. Markdown only — no LLM calls.

# Ref: Jobhunter Obsidian layout — Skills / Companies / Jobs
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OBSIDIAN_DIR = PROJECT_ROOT / "output" / "obsidian"
SKILLS_DIRNAME = "Skills"
COMPANIES_DIRNAME = "Companies"
JOBS_DIRNAME = "Jobs"
DOCS_DIRNAME = "jobhunter_docs"
REPO_DOCS_DIR = PROJECT_ROOT / "jobhunter_docs"
DEFAULT_DB_PATH = PROJECT_ROOT / "job_agent.db"

# Exact names only. New cards are created when a JD or dossier contains one of these.
# Ref: Obsidian skill notes — stubs, not model-written essays.
SKILL_RULES: tuple[tuple[str, str], ...] = (
    ("IoT Telemetry", r"iot[\s-]?telemetry|物聯網遙測|物聯網|\biot\b|telemetry|遙測"),
    ("FastAPI", r"\bfastapi\b"),
    ("Django", r"\bdjango\b"),
    ("Flask", r"\bflask\b"),
    ("LangGraph", r"\blanggraph\b"),
    ("LangChain", r"\blangchain\b"),
    ("PostgreSQL", r"\bpostgresql\b|\bpostgres\b"),
    ("MySQL", r"\bmysql\b"),
    ("SQLite", r"\bsqlite\b"),
    ("Redis", r"\bredis\b"),
    ("MongoDB", r"\bmongodb\b|\bmongo\b"),
    ("JavaScript", r"\bjavascript\b"),
    ("TypeScript", r"\btypescript\b"),
    ("Node.js", r"node\.js|\bnodejs\b"),
    ("React", r"\breact\b"),
    ("Next.js", r"next\.js|\bnextjs\b"),
    ("Vue", r"\bvue\b"),
    ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("Kafka", r"\bkafka\b"),
    ("MQTT", r"\bmqtt\b"),
    ("Flutter", r"\bflutter\b"),
    ("PyTorch", r"\bpytorch\b"),
    ("AWS", r"\baws\b"),
    ("Azure", r"\bazure\b"),
    ("RAG", r"\brag\b"),
    ("n8n", r"\bn8n\b"),
    ("Node-RED", r"node-red|nodered"),
    ("Grafana", r"\bgrafana\b"),
    ("Prometheus", r"\bprometheus\b"),
    ("Terraform", r"\bterraform\b"),
    ("Celery", r"\bcelery\b"),
    ("Tailwind", r"\btailwind\b"),
    ("GraphQL", r"\bgraphql\b"),
    ("Java", r"\bjava\b(?!script)"),
    ("Python", r"\bpython\b"),
)

SKILL_STUB_MARKER = "這張卡在職缺或公司技術棧出現此技能名稱時建立。"

# Short factual descriptions. Not candidate history, and not inferred from a JD.
SKILL_DETAILS: dict[str, dict[str, object]] = {
    "Python": {
        "summary": "通用程式語言。在這套資料裡，職缺常把它用作後端 API、資料處理和 AI agent 的實作語言。",
        "related": ["FastAPI", "Django", "Flask"],
    },
    "FastAPI": {
        "summary": "用 Python 撰寫 HTTP API 的框架。路徑、請求和回應可以用型別宣告，並自動產生 API 文件。",
        "related": ["Python"],
    },
    "Django": {
        "summary": "Python 的網站框架。自帶 ORM、路由、管理後台和一套專案結構，適合做成完整的網站後端。",
        "related": ["Python"],
    },
    "Flask": {
        "summary": "較輕的 Python 網站框架。路由和擴充由專案自己組，沒有 Django 那種固定的全套結構。",
        "related": ["Python"],
    },
    "LangGraph": {
        "summary": "把多步 AI agent 編成有狀態的流程圖，用來控制工具呼叫、分支和重試。通常以 Python 撰寫。",
        "related": ["Python", "RAG"],
    },
    "LangChain": {
        "summary": "組裝語言模型應用的 Python 程式庫。常見用途是把提示、工具和文件檢索接成一條鏈。",
        "related": ["Python", "RAG"],
    },
    "RAG": {
        "summary": "檢索增強生成。先從文件或資料庫找出相關內容，再交給模型作答，減少只靠模型記憶回答。",
        "related": ["LangGraph", "LangChain"],
    },
    "PostgreSQL": {
        "summary": "開源的關聯式資料庫。適合需要交易、條件查詢和較嚴謹資料結構的業務資料。",
        "related": ["Python"],
    },
    "MySQL": {
        "summary": "常見的關聯式資料庫，以資料表和 SQL 儲存業務資料。",
        "related": [],
    },
    "SQLite": {
        "summary": "把整個資料庫放在單一檔案的關聯式資料庫。適合本機工具、嵌入式儲存和小型應用。",
        "related": ["Python"],
    },
    "Redis": {
        "summary": "主要放在記憶體的資料儲存。常用於快取、短期狀態，以及背景工作的佇列。",
        "related": ["Celery"],
    },
    "MongoDB": {
        "summary": "文件型資料庫。一筆資料是一份類似 JSON 的文件，不必先定成固定欄位的資料表。",
        "related": [],
    },
    "JavaScript": {
        "summary": "瀏覽器和 Node.js 上常用的程式語言，用來寫網頁互動和伺服器端 JavaScript。",
        "related": ["TypeScript", "Node.js"],
    },
    "TypeScript": {
        "summary": "在 JavaScript 上加上靜態型別。編譯後仍是 JavaScript，用來在較大的前端或 Node 專案裡提早發現型別錯誤。",
        "related": ["JavaScript", "React"],
    },
    "Node.js": {
        "summary": "在伺服器上執行 JavaScript 的執行環境。常用來寫 API、即時服務和工作流工具。",
        "related": ["JavaScript", "TypeScript"],
    },
    "React": {
        "summary": "用來組成使用者介面的 JavaScript 程式庫。畫面由可重用的元件構成。",
        "related": ["TypeScript", "Next.js"],
    },
    "Next.js": {
        "summary": "建在 React 上的網站框架，負責路由、伺服器渲染，以及前端和 API 放在同一個專案。",
        "related": ["React"],
    },
    "Vue": {
        "summary": "用來組成使用者介面的 JavaScript 框架。元件以模板、狀態和方法組織畫面。",
        "related": ["JavaScript", "TypeScript"],
    },
    "Docker": {
        "summary": "把應用和它的依賴包成容器，讓同一套環境可以在不同機器上執行。",
        "related": ["Kubernetes"],
    },
    "Kubernetes": {
        "summary": "編排多個容器的系統，負責部署、擴展、重啟和服務之間的網路。",
        "related": ["Docker"],
    },
    "Kafka": {
        "summary": "分散式的事件串流平台。系統把訊息寫進主題，其他服務再按順序讀取，用來傳遞大量事件。",
        "related": [],
    },
    "MQTT": {
        "summary": "輕量的發布／訂閱訊息協定。裝置把讀數發到主題，後端再訂閱，常見於感測器和設備通訊。",
        "related": ["IoT Telemetry"],
    },
    "IoT Telemetry": {
        "summary": "從感測器或邊緣裝置收集狀態和量測，再送到後端儲存、顯示或告警。傳輸常走 MQTT，或先在閘道上彙整。",
        "related": ["MQTT", "Node-RED", "Python"],
    },
    "Flutter": {
        "summary": "用一套程式碼建立手機介面的框架。介面由 widget 組成，可編譯到 iOS 和 Android。",
        "related": [],
    },
    "PyTorch": {
        "summary": "用 Python 訓練和執行神經網路的程式庫。模型以張量運算組成。",
        "related": ["Python"],
    },
    "AWS": {
        "summary": "Amazon 的雲端平台，提供運算、儲存、資料庫和網路等服務。職缺若只寫 AWS，不代表已指定哪一項產品。",
        "related": ["Terraform"],
    },
    "Azure": {
        "summary": "Microsoft 的雲端平台，提供運算、儲存、資料庫和身份驗證等服務。",
        "related": ["Terraform"],
    },
    "n8n": {
        "summary": "以節點串接的工作流工具。用現成的節點把 API、資料庫和通知接成自動化流程。",
        "related": ["Node.js"],
    },
    "Node-RED": {
        "summary": "以節點串接的流程工具，常用於把裝置、協定和 API 接在一起，尤其是物聯網整合。",
        "related": ["IoT Telemetry", "MQTT"],
    },
    "Grafana": {
        "summary": "把系統指標畫成儀表板的工具。圖表的數據通常來自 Prometheus 或其他指標來源。",
        "related": ["Prometheus"],
    },
    "Prometheus": {
        "summary": "收集和查詢系統指標的監控工具。服務定期交出數值，Prometheus 儲存後供告警和圖表使用。",
        "related": ["Grafana"],
    },
    "Terraform": {
        "summary": "用設定檔描述雲端資源，再建立或更新那些資源。同一份設定可以對應 AWS、Azure 或其他平台。",
        "related": ["AWS", "Azure"],
    },
    "Celery": {
        "summary": "Python 的背景工作佇列。網頁請求先把工作放進佇列，工人行程稍後再執行。",
        "related": ["Python", "Redis"],
    },
    "Tailwind": {
        "summary": "用預先定義的樣式類別寫介面外觀的 CSS 工具，類別直接放在 HTML 或元件上。",
        "related": [],
    },
    "GraphQL": {
        "summary": "一種 API 查詢語言。客戶端在一個請求裡寫明要哪些欄位，伺服器按該查詢回傳。",
        "related": [],
    },
    "Java": {
        "summary": "通用程式語言，常見於企業後端。它和 JavaScript 是兩種語言。",
        "related": [],
    },
}


def safe_note_stem(name: str, limit: int = 60) -> str:
    """Windows-safe note title. Does not call a model."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    cleaned = " ".join(cleaned.split())
    return (cleaned[:limit] or "note").rstrip(" .")


def job_note_stem(company: str, title: str) -> str:
    """Shared title for the JD note, CV note, and cover letter note."""
    return f"{safe_note_stem(company)} — {safe_note_stem(title)}"


def sync_jobhunter_docs(root: Optional[Path] = None) -> int:
    """Copy git-tracked jobhunter_docs/ into the Obsidian vault for graph links.

    # Ref: project READMEs live under jobhunter_docs
    """
    dest = (root or OBSIDIAN_DIR) / DOCS_DIRNAME
    src = REPO_DOCS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        return 0
    written = 0
    for path in src.rglob("*.md"):
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8")
        if target.exists() and target.read_text(encoding="utf-8") == text:
            continue
        target.write_text(text, encoding="utf-8")
        written += 1
    return written


def init_obsidian_vault(root: Optional[Path] = None) -> Path:
    """Create Skills, Companies, Jobs, and jobhunter_docs. Keep existing notes.

    Called on server startup and at the start of each pipeline run.
    Folders are created every time. An existing index is left for the SQLite export to refresh.
    """
    base = root or OBSIDIAN_DIR
    for name in (SKILLS_DIRNAME, COMPANIES_DIRNAME, JOBS_DIRNAME, DOCS_DIRNAME):
        (base / name).mkdir(parents=True, exist_ok=True)
    sync_jobhunter_docs(base)
    index_path = base / "README.md"
    if index_path.exists():
        return base
    stamp = datetime.now(HK_TZ).isoformat(timespec="seconds")
    index = "\n".join(
        [
            "---",
            "type: obsidian-index",
            f"updated_at: {stamp}",
            "---",
            "",
            "# Obsidian",
            "",
            "這份索引在每次伺服器啟動或管線開始時重寫。下面三個資料夾裡已有的筆記不會刪除。",
            "",
            f"- `{SKILLS_DIRNAME}/` — 技能卡",
            f"- `{COMPANIES_DIRNAME}/` — 公司 Dossier",
            f"- `{JOBS_DIRNAME}/` — 職缺、履歷、求職信",
            f"- `{DOCS_DIRNAME}/` — 專案說明（[[Jobhunter docs]]）",
            "",
        ]
    )
    index_path.write_text(index, encoding="utf-8")
    return base


def _bullets(items: Iterable[str]) -> str:
    rows = [str(item).strip() for item in items if str(item).strip()]
    if not rows:
        return "_None._"
    return "\n".join(f"- {row}" for row in rows)


def render_cv_readme(
    *,
    candidate_name: str,
    contact_lines: Sequence[str],
    target_company: str,
    target_role: str,
    professional_summary: str,
    prioritized_skills: Mapping[str, Sequence[str]],
    experience: Sequence[Mapping[str, object]],
    projects: Sequence[Mapping[str, object]],
    certifications: Sequence[str],
    education: Sequence[Mapping[str, object]],
    languages: Sequence[str],
    awards: Sequence[str],
) -> str:
    """Markdown CV from an existing tailored payload. No model call."""
    stem = job_note_stem(target_company, target_role)
    company = safe_note_stem(target_company)
    lines = [
        "---",
        "type: cv",
        f"company: {company}",
        f"role: {safe_note_stem(target_role)}",
        "---",
        "",
        f"# {candidate_name} — CV",
        "",
        f"- 公司：[[{company}]]",
        f"- 職缺：[[{stem}]]",
        f"- 求職信：[[{stem} Cover Letter]]",
        "",
        candidate_name,
        *[line for line in contact_lines if str(line).strip()],
        "",
        f"**{target_role}** · {target_company}",
        "",
        "## Summary",
        "",
        (professional_summary or "").strip() or "_None._",
        "",
        "## Skills",
        "",
    ]
    if prioritized_skills:
        for category, items in prioritized_skills.items():
            lines.append(f"### {category}")
            lines.append("")
            lines.append(_bullets(items))
            lines.append("")
    else:
        lines.append("_None._")
        lines.append("")
    lines.extend(["## Experience", ""])
    if experience:
        for item in experience:
            role = str(item.get("role") or "").strip()
            employer = str(item.get("company") or "").strip()
            period = str(item.get("period") or "").strip()
            lines.append(f"### {role} — {employer}")
            if period:
                lines.append("")
                lines.append(period)
            highlights = item.get("highlights") or []
            lines.append("")
            if isinstance(highlights, str):
                highlights = [highlights]
            lines.append(_bullets(highlights if isinstance(highlights, list) else []))
            lines.append("")
    else:
        lines.append("_None._")
        lines.append("")
    lines.extend(["## Projects", ""])
    if projects:
        for item in projects:
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "").strip()
            heading = f"{name} — {role}" if role else name
            lines.append(f"### {heading}")
            lines.append("")
            description = str(item.get("description") or "").strip()
            if description:
                lines.append(description)
                lines.append("")
            stack = item.get("tech_stack") or []
            if isinstance(stack, str):
                stack = [stack]
            if isinstance(stack, list) and any(str(part).strip() for part in stack):
                lines.append(_bullets(str(part) for part in stack))
                lines.append("")
    else:
        lines.append("_None._")
        lines.append("")
    lines.extend(["## Education", ""])
    edu_rows = []
    for item in education:
        if not isinstance(item, Mapping):
            continue
        degree = str(item.get("degree") or "").strip()
        institution = str(item.get("institution") or "").strip()
        year = item.get("year")
        year_text = "" if year in (None, "") else str(year)
        edu_rows.append(" — ".join(part for part in (degree, institution, year_text) if part))
    lines.append(_bullets(edu_rows))
    lines.extend(["", "## Certifications", "", _bullets(certifications)])
    lines.extend(["", "## Awards", "", _bullets(awards)])
    lines.extend(["", "## Languages", "", _bullets(languages), ""])
    return "\n".join(lines)


def render_cover_letter_readme(
    *,
    candidate_name: str,
    contact_lines: Sequence[str],
    target_company: str,
    target_role: str,
    letter_date: str,
    greeting: str,
    paragraphs: Sequence[str],
    closing: str,
) -> str:
    """Markdown cover letter from an existing payload. No model call."""
    stem = job_note_stem(target_company, target_role)
    company = safe_note_stem(target_company)
    lines = [
        "---",
        "type: cover-letter",
        f"company: {company}",
        f"role: {safe_note_stem(target_role)}",
        "---",
        "",
        f"# {candidate_name} — Cover Letter",
        "",
        f"- 公司：[[{company}]]",
        f"- 職缺：[[{stem}]]",
        f"- 履歷：[[{stem} CV]]",
        "",
        candidate_name,
        *[line for line in contact_lines if str(line).strip()],
        letter_date,
        "",
        target_company,
        target_role,
        "",
        greeting,
        "",
    ]
    for paragraph in paragraphs:
        text = str(paragraph).strip()
        if text:
            lines.append(text)
            lines.append("")
    lines.extend([closing, "", candidate_name, ""])
    return "\n".join(lines)


def write_job_readmes(
    *,
    company: str,
    title: str,
    cv_body: str = "",
    cover_letter_body: str = "",
    root: Optional[Path] = None,
) -> dict[str, str]:
    """Write CV and cover letter Markdown into output/obsidian/Jobs."""
    base = init_obsidian_vault(root)
    jobs = base / JOBS_DIRNAME
    stem = job_note_stem(company, title)
    written: dict[str, str] = {}
    if cv_body.strip():
        path = jobs / f"{stem} CV.md"
        path.write_text(cv_body, encoding="utf-8")
        written["cv_md_path"] = str(path)
    if cover_letter_body.strip():
        path = jobs / f"{stem} Cover Letter.md"
        path.write_text(cover_letter_body, encoding="utf-8")
        written["cover_letter_md_path"] = str(path)
    return written


def skills_in_text(text: str) -> list[str]:
    """Return catalog skill names that appear in text. No model call."""
    blob = text or ""
    found: list[str] = []
    for name, pattern in SKILL_RULES:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            found.append(name)
    return found


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value.strip()]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [value.strip()]
    return []


def _field(row: Mapping[str, object], key: str, default: object = "") -> object:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _yaml_str(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _clip(text: str, limit: int = 6000) -> str:
    body = (text or "").strip()
    if not body:
        return "_None._"
    if len(body) <= limit:
        return body
    return body[:limit].rstrip() + "\n\n_（下文已截斷。全文在 SQLite。）_"


def _unique_stem(used: dict[str, str], stem: str, key: str) -> str:
    if stem not in used or used[stem] == key:
        used[stem] = key
        return stem
    number = 2
    while True:
        alt = f"{stem} ({number})"
        if alt not in used or used[alt] == key:
            used[alt] = key
            return alt
        number += 1


def _rel_link(from_dir: Path, target: str) -> str:
    raw = (target or "").strip()
    if not raw:
        return ""
    try:
        return Path(os.path.relpath(raw, from_dir)).as_posix()
    except ValueError:
        return raw


def render_skill_note(name: str) -> str:
    """Skill card with a fixed description. No model call."""
    detail = SKILL_DETAILS.get(name) or {}
    summary = str(detail.get("summary") or "目錄中的技能。")
    related = detail.get("related") or []
    lines = [
        "---",
        "type: skill",
        "generated: true",
        "---",
        "",
        f"# {name}",
        "",
        summary,
        "",
    ]
    if isinstance(related, list) and related:
        lines.extend(["## 相關技能", ""])
        lines.extend(f"- [[{item}]]" for item in related)
        lines.append("")
    lines.extend(
        [
            "右側 Backlinks 列出要求這項技能的職缺和公司。",
            "",
        ]
    )
    return "\n".join(lines)


def _skill_stub(name: str) -> str:
    return render_skill_note(name)


def _company_note(company: str, dossier: Optional[dict], verdict: str, confidence: object) -> str:
    payload = dossier or {}
    stack = _as_list(payload.get("detected_tech_stack"))
    skills = skills_in_text("\n".join(stack))
    lines = [
        "---",
        "type: company",
        "generated: true",
        f"status: {_yaml_str(verdict)}",
        f"confidence: {int(confidence) if str(confidence or '').strip().isdigit() else 0}",
        "---",
        "",
        f"# {company}",
        "",
    ]
    if skills:
        lines.append("## Skills")
        lines.append("")
        lines.extend(f"- [[{name}]]" for name in skills)
        lines.append("")
    if not payload:
        lines.extend(["SQLite 尚未有這間公司的 Dossier。", ""])
        return "\n".join(lines)
    sections = [
        ("Engineering culture", payload.get("engineering_culture")),
        ("Detected tech stack", stack),
        ("Architectural trade-offs / technical debt", payload.get("architectural_trade_offs")),
        ("Glassdoor / forum sentiment", payload.get("glassdoor_sentiment")),
        ("Recent news and events (12–24 months)", _as_list(payload.get("recent_news_and_events"))),
        ("Red flags", _as_list(payload.get("red_flags"))),
        ("Green flags", _as_list(payload.get("green_flags"))),
        ("Reverse-interview questions", _as_list(payload.get("reverse_interview_questions"))),
        ("Sources", _as_list(payload.get("source_urls"))),
    ]
    salary = str(payload.get("salary_benchmark") or "").strip()
    if salary:
        lines.extend(["## Salary benchmark", "", salary, ""])
    for title, body in sections:
        lines.append(f"## {title}")
        lines.append("")
        if isinstance(body, list):
            lines.append(_bullets(body))
        else:
            lines.append(str(body or "").strip() or "_None._")
        lines.append("")
    return "\n".join(lines)


def _job_note(
    *,
    company_stem: str,
    job_stem: str,
    title: str,
    company: str,
    match_score: object,
    verdict: str,
    row: Mapping[str, object],
    required_skills: Sequence[str],
    missing_named: Sequence[str],
    jobs_dir: Path,
) -> str:
    jd = str(_field(row, "jd_full") or _field(row, "jd_snippet") or "")
    lines = [
        "---",
        "type: job",
        "generated: true",
        f"company: {_yaml_str(company_stem)}",
        f"match_score: {int(match_score or 0)}",
        f"status: {_yaml_str(verdict)}",
        f"cv_status: {_yaml_str(_field(row, 'cv_status'))}",
        f"user_status: {_yaml_str(_field(row, 'user_status'))}",
        "---",
        "",
        f"# {title}",
        "",
        f"- 公司：[[{company_stem}]]",
    ]
    cv_path = str(_field(row, "cv_pdf_path") or "").strip()
    letter_path = str(_field(row, "cover_letter_pdf_path") or "").strip()
    checklist = str(_field(row, "application_checklist_path") or "").strip()
    if cv_path:
        lines.append(f"- 履歷：[[{job_stem} CV]]")
    if letter_path:
        lines.append(f"- 求職信：[[{job_stem} Cover Letter]]")
    if checklist:
        lines.append(f"- 申請清單：[[{job_stem} Checklist]]")
    lines.extend(["", "## Scores", ""])
    lines.append(f"- match_score：{int(match_score or 0)}")
    lines.append(f"- hard_skill_match_score：{_field(row, 'hard_skill_match_score')}")
    lines.append(f"- transferability_score：{_field(row, 'transferability_score')}")
    lines.append(f"- 公司結論：{verdict or '尚未有 Dossier'}")
    lines.extend(["", "## Required skills", ""])
    lines.append(_bullets(f"[[{name}]]" for name in required_skills) if required_skills else "_JD 文字未命中技能目錄。_")
    lines.extend(["", "## Missing skills", ""])
    lines.append(_bullets(f"[[{name}]]" for name in missing_named) if missing_named else "_未命中技能目錄。_")
    lines.extend(["", "## Matched notes", "", _bullets(_as_list(_field(row, "matched_skills", [])))])
    lines.extend(["", "## Gap notes", "", _bullets(_as_list(_field(row, "missing_skills", [])))])
    reason = str(_field(row, "recommendation_reason") or "").strip()
    if reason:
        lines.extend(["", "## Recommendation", "", reason])
    lines.extend(["", "## JD", "", _clip(jd)])
    file_rows: list[str] = []
    for label, raw in (("CV PDF", cv_path), ("Cover letter PDF", letter_path)):
        if raw:
            file_rows.append(f"- {label}：[{Path(raw).name}]({_rel_link(jobs_dir, raw)})")
    if file_rows:
        lines.extend(["", "## Files", "", *file_rows, ""])
    lines.append(f"\n公司原名：{company}\n")
    return "\n".join(lines)


def _pointer_note(*, kind: str, title: str, company_stem: str, job_stem: str, pdf_path: str, jobs_dir: Path) -> str:
    other = "Cover Letter" if kind == "cv" else "CV"
    other_link = f"[[{job_stem} {other}]]"
    label = "履歷" if kind == "cv" else "求職信"
    return "\n".join(
        [
            "---",
            f"type: {kind if kind == 'cv' else 'cover-letter'}",
            "generated: true",
            "source: pdf",
            "---",
            "",
            f"# {title} — {label}",
            "",
            f"- 公司：[[{company_stem}]]",
            f"- 職缺：[[{job_stem}]]",
            f"- {other}：{other_link}",
            "",
            f"PDF：[{Path(pdf_path).name}]({_rel_link(jobs_dir, pdf_path)})",
            "",
            "這是現有 PDF 的索引。Leo 之後若寫出完整 Markdown，會取代這頁。",
            "",
        ]
    )


def export_obsidian_foundation(
    db_path: Optional[Path] = None,
    root: Optional[Path] = None,
) -> dict[str, int]:
    """Write linked company, job, and skill notes from SQLite. No model call.

    Company and job notes are refreshed from the database.
    Existing skill cards and existing CV / cover letter notes are left in place.
    """
    base = init_obsidian_vault(root)
    database = db_path or DEFAULT_DB_PATH
    stats = {"companies": 0, "jobs": 0, "skills_created": 0, "materials": 0}
    if not database.is_file():
        return stats
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        dossiers = conn.execute(
            "SELECT company_name, vetting_verdict, confidence, dossier_json, source_urls "
            "FROM company_dossiers"
        ).fetchall()
        jobs = conn.execute(
            "SELECT id, company_name, job_title, match_score, matched_skills, missing_skills, "
            "jd_snippet, jd_full, recommendation_reason, hard_skill_match_score, "
            "transferability_score, cv_status, cv_pdf_path, cover_letter_pdf_path, "
            "application_checklist_path, user_status "
            "FROM job_postings"
        ).fetchall()
    finally:
        conn.close()

    company_stems: dict[str, str] = {}
    used_company: dict[str, str] = {}
    dossier_by_name: dict[str, sqlite3.Row] = {}
    for row in dossiers:
        name = str(row["company_name"] or "").strip()
        if not name:
            continue
        dossier_by_name[name] = row
        company_stems[name] = _unique_stem(used_company, safe_note_stem(name), name)

    for row in jobs:
        name = str(row["company_name"] or "").strip()
        if name and name not in company_stems:
            company_stems[name] = _unique_stem(used_company, safe_note_stem(name), name)

    companies_dir = base / COMPANIES_DIRNAME
    jobs_dir = base / JOBS_DIRNAME
    skills_dir = base / SKILLS_DIRNAME
    skill_names: set[str] = set()

    for name, stem in company_stems.items():
        row = dossier_by_name.get(name)
        payload: dict = {}
        verdict = ""
        confidence: object = 0
        if row is not None:
            try:
                parsed = json.loads(row["dossier_json"] or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                payload = parsed
            if not _as_list(payload.get("source_urls")):
                payload["source_urls"] = _as_list(row["source_urls"])
            verdict = str(row["vetting_verdict"] or payload.get("vetting_verdict") or "")
            confidence = row["confidence"] if row["confidence"] is not None else payload.get("confidence") or 0
        note = _company_note(name, payload if row is not None else None, verdict, confidence)
        (companies_dir / f"{stem}.md").write_text(note, encoding="utf-8")
        stats["companies"] += 1
        skill_names.update(skills_in_text("\n".join(_as_list(payload.get("detected_tech_stack")))))

    used_jobs: dict[str, str] = {}
    for row in jobs:
        company = str(row["company_name"] or "").strip() or "Unknown company"
        title = str(row["job_title"] or "").strip() or f"Job {row['id']}"
        company_stem = company_stems.get(company) or safe_note_stem(company)
        job_stem = _unique_stem(used_jobs, job_note_stem(company, title), str(row["id"]))
        jd_text = "\n".join(
            [
                str(row["jd_full"] or row["jd_snippet"] or ""),
                "\n".join(_as_list(row["matched_skills"])),
            ]
        )
        required = skills_in_text(jd_text)
        missing_named = [
            name
            for name in skills_in_text("\n".join(_as_list(row["missing_skills"])))
            if name not in required
        ]
        skill_names.update(required)
        skill_names.update(missing_named)
        verdict = ""
        dossier_row = dossier_by_name.get(company)
        if dossier_row is not None:
            verdict = str(dossier_row["vetting_verdict"] or "")
        (jobs_dir / f"{job_stem}.md").write_text(
            _job_note(
                company_stem=company_stem,
                job_stem=job_stem,
                title=title,
                company=company,
                match_score=row["match_score"],
                verdict=verdict,
                row=row,
                required_skills=required,
                missing_named=missing_named,
                jobs_dir=jobs_dir,
            ),
            encoding="utf-8",
        )
        stats["jobs"] += 1
        cv_pdf = str(row["cv_pdf_path"] or "").strip()
        letter_pdf = str(row["cover_letter_pdf_path"] or "").strip()
        if cv_pdf and not (jobs_dir / f"{job_stem} CV.md").exists():
            (jobs_dir / f"{job_stem} CV.md").write_text(
                _pointer_note(
                    kind="cv",
                    title=title,
                    company_stem=company_stem,
                    job_stem=job_stem,
                    pdf_path=cv_pdf,
                    jobs_dir=jobs_dir,
                ),
                encoding="utf-8",
            )
            stats["materials"] += 1
        if letter_pdf and not (jobs_dir / f"{job_stem} Cover Letter.md").exists():
            (jobs_dir / f"{job_stem} Cover Letter.md").write_text(
                _pointer_note(
                    kind="letter",
                    title=title,
                    company_stem=company_stem,
                    job_stem=job_stem,
                    pdf_path=letter_pdf,
                    jobs_dir=jobs_dir,
                ),
                encoding="utf-8",
            )
            stats["materials"] += 1
        checklist = str(row["application_checklist_path"] or "").strip()
        checklist_note = jobs_dir / f"{job_stem} Checklist.md"
        if checklist and Path(checklist).is_file() and not checklist_note.exists():
            body = Path(checklist).read_text(encoding="utf-8", errors="replace")
            checklist_note.write_text(
                "\n".join(
                    [
                        "---",
                        "type: checklist",
                        "generated: true",
                        "---",
                        "",
                        f"- 職缺：[[{job_stem}]]",
                        f"- 公司：[[{company_stem}]]",
                        "",
                        body.strip(),
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            stats["materials"] += 1

    for name in sorted(skill_names):
        path = skills_dir / f"{safe_note_stem(name)}.md"
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current and SKILL_STUB_MARKER not in current and "正文留給你之後手寫" not in current:
            continue
        path.write_text(render_skill_note(name), encoding="utf-8")
        stats["skills_created"] += 1

    stamp = datetime.now(HK_TZ).isoformat(timespec="seconds")
    (base / "README.md").write_text(
        "\n".join(
            [
                "---",
                "type: obsidian-index",
                f"updated_at: {stamp}",
                "---",
                "",
                "# Obsidian",
                "",
                "公司與職缺筆記由 SQLite 轉出，並以 `[[連結]]` 相連。每次啟動會按資料庫重寫這兩類筆記。",
                "空白技能卡會補上說明。已經手寫過的技能卡、履歷和求職信不會被蓋掉。",
                "",
                f"- `{SKILLS_DIRNAME}/` — 技能卡（{len(skill_names)} 項有被連結）",
                f"- `{COMPANIES_DIRNAME}/` — 公司（{stats['companies']}）",
                f"- `{JOBS_DIRNAME}/` — 職缺（{stats['jobs']}）",
                f"- `{DOCS_DIRNAME}/` — 專案說明（[[Jobhunter docs]]）",
                "",
                "專案 README 地圖：[[Jobhunter docs]]。公司卡與職缺卡仍由 SQLite 轉出。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return stats
