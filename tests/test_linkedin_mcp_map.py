"""Map LinkedIn MCP get_profile JSON onto master_profile fields."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
for extra in (_VALIDATORS, _AGENTS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from contact_links import parse_linkedin_profile_ref
from linkedin_mcp_client import _unwrap_tool_result, master_profile_from_mcp


def test_mcp_profile_maps_experience_and_name() -> None:
    ref = parse_linkedin_profile_ref("damien-yu")
    assert ref is not None
    mapped = master_profile_from_mcp(
        {
            "firstName": "Damien",
            "lastName": "Yu",
            "headline": "Platform Engineer",
            "geoLocationName": "Hong Kong SAR",
            "about": "IoT and backend.",
            "experience": [
                {
                    "title": "Engineer",
                    "companyName": "HKPC",
                    "description": "AI systems",
                }
            ],
            "education": [{"schoolName": "HKU", "degreeName": "MSc"}],
            "skills": [{"name": "Python"}, "FastAPI"],
        },
        ref,
    )
    assert mapped["basics"]["name"] == "Damien Yu"
    assert mapped["basics"]["linkedin"] == "damien-yu"
    assert mapped["experience"][0]["company"] == "HKPC"
    assert mapped["experience"][0]["roles"][0]["role"] == "Engineer"
    assert mapped["education"][0]["institution"] == "HKU"
    assert "Python" in mapped["technical_skills"]["linkedin"]


def test_official_get_profile_shape_unfences_and_maps_dates() -> None:
    ref = parse_linkedin_profile_ref("damien-yu-3ab661260")
    assert ref is not None
    mapped = master_profile_from_mcp(
        {
            "public_id": "damien-yu-3ab661260",
            "name": "Damien Yu",
            "headline": (
                "<<<LINKEDIN-UNTRUSTED-DATA:HEADLINE>>>\n---\n"
                "Platform Engineer\n---\n<<<END-LINKEDIN-UNTRUSTED-DATA>>>"
            ),
            "about": (
                "<<<LINKEDIN-UNTRUSTED-DATA:ABOUT>>>\n---\n"
                "IoT backend.\n---\n<<<END-LINKEDIN-UNTRUSTED-DATA>>>"
            ),
            "experience": [
                {
                    "title": "Engineer",
                    "company": "HKPC",
                    "dates": "2024 - Present",
                    "description": "AI systems",
                }
            ],
            "education": [
                {
                    "school": "HKU",
                    "degree": "MSc",
                    "field_of_study": "CS",
                    "dates": "2018 - 2022",
                }
            ],
        },
        ref,
    )
    assert mapped["basics"]["headline"] == "Platform Engineer"
    assert mapped["basics"]["summary"] == "IoT backend."
    assert mapped["experience"][0]["period"] == "2024 - Present"
    assert mapped["experience"][0]["roles"][0]["period"] == "2024 - Present"
    assert mapped["education"][0]["year"] == "2018 - 2022"


def test_mcp_languages_keep_name_and_proficiency() -> None:
    ref = parse_linkedin_profile_ref("lychee-lai-351b03330")
    mapped = master_profile_from_mcp(
        {
            "public_id": "lychee-lai-351b03330",
            "name": "Lychee Lai",
            "languages": [
                {"name": "Cantonese", "proficiency": "Native or bilingual proficiency"},
                {"name": "English", "proficiency": "Professional working proficiency"},
            ],
        },
        ref,
    )
    assert mapped["languages"][0]["name"] == "Cantonese"
    assert "Cantonese" in mapped["basics"]["languages"][0]


def test_unwrap_json_text_content() -> None:
    body = {"public_id": "lychee-lai", "name": "Lychee Lai", "experience": []}
    reply = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"content": [{"type": "text", "text": json.dumps(body)}]},
    }
    assert _unwrap_tool_result(reply)["public_id"] == "lychee-lai"


def test_agent_mcp_command_uses_uvx_not_cursor() -> None:
    from linkedin_mcp_client import _mcp_command

    os.environ["LINKEDIN_MCP_COMMAND"] = "uvx"
    os.environ["LINKEDIN_MCP_ARGS"] = "linkedin-api-mcp"
    cmd = _mcp_command()
    assert cmd[0].endswith("uvx") or cmd[0].endswith("uvx.exe") or cmd[0] == "uvx"
    assert "linkedin-api-mcp" in cmd


def test_linkedin_mcp_status_explains_where_and_how() -> None:
    from linkedin_mcp_client import linkedin_mcp_status, mcp_status_lines

    status = linkedin_mcp_status()
    assert "not Cursor" in status["connected_in"]
    assert "import-linkedin" in status["how"]
    assert "config/linkedin_mcp" in status["writes_cache"]
    blob = "\n".join(mcp_status_lines())
    assert "Where:" in blob
    assert "get_profile" in blob
