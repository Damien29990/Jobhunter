"""CV Word extract + reverse-chronological experience dates."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / "src" / "agents"
_VALIDATORS = _ROOT / "src" / "validators"
for extra in (_AGENTS, _VALIDATORS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from cv_experience import normalize_experience_list, parse_period_bounds
from cv_docx import extract_docx_text


def _docx_bytes(document_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
    return buf.getvalue()


def test_docx_keeps_paragraph_and_table_order() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Senior Software Engineer</w:t></w:r></w:p>
    <w:p><w:r><w:t>Nov 2024 – Mar 2026</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>EC Goal</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>2024-2026</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:p><w:r><w:t>Intern Jun 2023</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    text = extract_docx_text(_docx_bytes(xml))
    assert "Senior Software Engineer" in text
    assert "EC Goal | 2024-2026" in text
    assert text.index("Senior Software Engineer") < text.index("EC Goal")
    assert text.index("EC Goal") < text.index("Intern Jun 2023")
    assert "\n" in text


def test_experience_sorted_recent_first_and_dates_not_swapped() -> None:
    rows = normalize_experience_list(
        [
            {"company": "Octopus", "role": "PT", "period": "Aug 2023 - Nov 2023"},
            {"company": "Self", "role": "SSE", "period": "MAR 2026 - Present"},
            {"company": "EC Goal", "role": "SSE", "period": "NOV 2024 - MAR 2026"},
        ]
    )
    assert [r["company"] for r in rows] == ["Self", "EC Goal", "Octopus"]
    start, end, present = parse_period_bounds(rows[1]["period"])
    assert start and end and start < end
    assert present is False


def test_swapped_years_are_corrected() -> None:
    rows = normalize_experience_list(
        [{"company": "X", "role": "Dev", "period": "2026 - 2024"}]
    )
    start, end, _ = parse_period_bounds(rows[0]["period"])
    assert start and end and start < end


def test_same_company_promotions_keep_separate_periods() -> None:
    rows = normalize_experience_list(
        [
            {
                "company": "EC Goal",
                "roles": [
                    {
                        "role": "Software Engineer",
                        "period": "2024-11 – 2025-06",
                        "highlights": ["Built APIs"],
                        "skills_used": ["Python"],
                    },
                    {
                        "role": "Senior Software Engineer",
                        "period": "2025-06 – Present",
                        "highlights": ["Led platform"],
                        "skills_used": ["FastAPI"],
                    },
                ],
            }
        ]
    )
    assert len(rows) == 1
    titles = [stint["role"] for stint in rows[0]["roles"]]
    assert titles[0] == "Senior Software Engineer"
    assert titles[1] == "Software Engineer"
    assert rows[0]["role"] == "Senior Software Engineer"
