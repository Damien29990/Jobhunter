"""DossierPayload must accept Agent 2 list-shaped JSON (news is List[str])."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.api.models import DossierPayload, JobOut, _parse_text_list


def test_news_list_does_not_wipe_payload():
    payload = DossierPayload.model_validate(
        {
            "company_name": "Acme",
            "vetting_verdict": "PROCEED",
            "salary_benchmark": "HKD 40k–60k",
            "detected_tech_stack": ["Python", "React"],
            "engineering_culture": "Squads ship weekly.",
            "glassdoor_sentiment": "Mixed WLB.",
            "recent_news_and_events": ["Won a 2025 tender.", "Opened a Kowloon hub."],
            "architectural_trade_offs": "Mainframe still in the loop.",
            "red_flags": ["Legacy COBOL"],
            "green_flags": ["Cloud migration funded"],
            "reverse_interview_questions": ["How is cutover gated?"],
            "source_urls": ["https://example.com/news"],
            "confidence": 72,
        }
    )
    assert payload.recent_news_and_events == ["Won a 2025 tender.", "Opened a Kowloon hub."]
    assert payload.detected_tech_stack == ["Python", "React"]
    assert payload.salary_benchmark == "HKD 40k–60k"


def test_news_plain_string_kept():
    payload = DossierPayload.model_validate({"recent_news_and_events": "Opened an HK office."})
    assert payload.recent_news_and_events == ["Opened an HK office."]


def test_parse_text_list_json_array_string():
    assert _parse_text_list('["a", "b"]') == ["a", "b"]


def test_job_out_embeds_nested_dossier():
    job = JobOut.model_validate(
        {
            "id": 1,
            "job_url": "https://example.com/j",
            "job_title": "Engineer",
            "company_name": "Acme",
            "dossier": {
                "id": 9,
                "company_name": "Acme",
                "vetting_verdict": "PROCEED",
                "confidence": 70,
                "dossier": {
                    "engineering_culture": "Weekly ship.",
                    "recent_news_and_events": ["Won a tender."],
                },
            },
        }
    )
    assert job.dossier is not None
    assert job.dossier.vetting_verdict == "PROCEED"
    assert job.dossier.dossier.recent_news_and_events == ["Won a tender."]
