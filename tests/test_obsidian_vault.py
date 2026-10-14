"""Obsidian folder init and CV / cover letter Markdown. No network."""

from __future__ import annotations

import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from obsidian_vault import (  # noqa: E402
    init_obsidian_vault,
    render_cover_letter_readme,
    render_cv_readme,
    sync_jobhunter_docs,
    write_job_readmes,
)


def test_init_creates_folders_and_keeps_existing_notes(tmp_path: Path) -> None:
    root = tmp_path / "obsidian"
    init_obsidian_vault(root)
    skill = root / "Skills" / "Python.md"
    skill.write_text("keep me", encoding="utf-8")

    again = init_obsidian_vault(root)

    assert again == root
    assert (root / "Companies").is_dir()
    assert (root / "Jobs").is_dir()
    assert (root / "jobhunter_docs" / "Jobhunter docs.md").is_file()
    vault_index = (root / "README.md").read_text(encoding="utf-8")
    assert "Skills/" in vault_index
    assert "jobhunter_docs" in vault_index
    assert skill.read_text(encoding="utf-8") == "keep me"


def test_jobhunter_docs_sync_has_agent_wikilinks(tmp_path: Path) -> None:
    n = sync_jobhunter_docs(tmp_path / "obsidian")
    rex = (
        tmp_path / "obsidian" / "jobhunter_docs" / "Agents" / "Rex.md"
    ).read_text(encoding="utf-8")
    assert n >= 1
    assert "[[Dana]]" in rex
    assert "[[Milo]]" in rex


def test_every_catalog_skill_has_a_description() -> None:
    from obsidian_vault import SKILL_DETAILS, SKILL_RULES, SKILL_STUB_MARKER, render_skill_note

    for name, _pattern in SKILL_RULES:
        note = render_skill_note(name)
        assert name in SKILL_DETAILS
        assert len(str(SKILL_DETAILS[name]["summary"])) > 20
        assert f"# {name}" in note
        assert SKILL_STUB_MARKER not in note


def test_skills_in_text_uses_catalog_only() -> None:
    from obsidian_vault import skills_in_text

    found = skills_in_text("Need Python, FastAPI, and JavaScript.")
    assert found == ["FastAPI", "JavaScript", "Python"]


def test_export_links_sqlite_rows(tmp_path: Path) -> None:
    import json
    import sqlite3

    from obsidian_vault import export_obsidian_foundation

    db = tmp_path / "job.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE company_dossiers ("
        "company_name TEXT, vetting_verdict TEXT, confidence INTEGER, "
        "dossier_json TEXT, source_urls TEXT)"
    )
    conn.execute(
        "CREATE TABLE job_postings ("
        "id INTEGER, company_name TEXT, job_title TEXT, match_score INTEGER, "
        "matched_skills TEXT, missing_skills TEXT, jd_snippet TEXT, jd_full TEXT, "
        "recommendation_reason TEXT, hard_skill_match_score INTEGER, "
        "transferability_score INTEGER, cv_status TEXT, cv_pdf_path TEXT, "
        "cover_letter_pdf_path TEXT, application_checklist_path TEXT, user_status TEXT)"
    )
    dossier = {
        "engineering_culture": "Small product team.",
        "detected_tech_stack": ["Python", "FastAPI"],
        "source_urls": ["https://example.com"],
        "red_flags": [],
        "green_flags": [],
        "recent_news_and_events": [],
        "reverse_interview_questions": [],
    }
    conn.execute(
        "INSERT INTO company_dossiers VALUES (?, ?, ?, ?, ?)",
        ("UDomain", "PROCEED", 62, json.dumps(dossier), "[]"),
    )
    conn.execute(
        "INSERT INTO job_postings VALUES (1, ?, ?, 82, ?, ?, ?, ?, '', 80, 70, '', '', '', '', '')",
        (
            "UDomain",
            "AI Engineer",
            json.dumps(["Ships FastAPI services."]),
            json.dumps(["Kafka is not on the CV."]),
            "Build Python and FastAPI APIs.",
            "Build Python and FastAPI APIs.",
        ),
    )
    conn.commit()
    conn.close()
    kept = tmp_path / "obsidian" / "Skills" / "Python.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("hand written", encoding="utf-8")

    stats = export_obsidian_foundation(db, tmp_path / "obsidian")
    company = (tmp_path / "obsidian" / "Companies" / "UDomain.md").read_text(encoding="utf-8")
    job = (tmp_path / "obsidian" / "Jobs" / "UDomain — AI Engineer.md").read_text(encoding="utf-8")

    assert stats["companies"] == 1
    assert stats["jobs"] == 1
    assert "[[FastAPI]]" in company
    assert "[[UDomain]]" in job
    assert "[[Python]]" in job
    assert "[[Kafka]]" in job
    assert "事件串流" in (tmp_path / "obsidian" / "Skills" / "Kafka.md").read_text(encoding="utf-8")
    assert kept.read_text(encoding="utf-8") == "hand written"
    assert (tmp_path / "obsidian" / "Skills" / "Kafka.md").is_file()


def test_cv_and_cover_letter_readme_are_linked(tmp_path: Path) -> None:
    cv = render_cv_readme(
        candidate_name="Damien",
        contact_lines=["Hong Kong"],
        target_company="UDomain",
        target_role="AI Engineer",
        professional_summary="Builds Python services.",
        prioritized_skills={"Backend": ["FastAPI"]},
        experience=[{
            "company": "Example Ltd",
            "role": "Engineer",
            "period": "2024",
            "highlights": ["Shipped an API"],
        }],
        projects=[{
            "name": "Telemetry",
            "description": "Edge ingest",
            "tech_stack": ["Python"],
            "role": "",
        }],
        certifications=["AWS SAA"],
        education=[{"degree": "BSc", "institution": "PolyU", "year": 2020}],
        languages=["Cantonese"],
        awards=[],
    )
    letter = render_cover_letter_readme(
        candidate_name="Damien",
        contact_lines=["Hong Kong"],
        target_company="UDomain",
        target_role="AI Engineer",
        letter_date="07 October 2026",
        greeting="Dear Hiring Manager,",
        paragraphs=["I am applying."],
        closing="Yours sincerely,",
    )
    written = write_job_readmes(
        company="UDomain",
        title="AI Engineer",
        cv_body=cv,
        cover_letter_body=letter,
        root=tmp_path / "obsidian",
    )

    cv_text = Path(written["cv_md_path"]).read_text(encoding="utf-8")
    letter_text = Path(written["cover_letter_md_path"]).read_text(encoding="utf-8")
    assert "Builds Python services." in cv_text
    assert "[[UDomain — AI Engineer Cover Letter]]" in cv_text
    assert "[[UDomain — AI Engineer CV]]" in letter_text
    assert "I am applying." in letter_text
