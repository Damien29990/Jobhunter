"""Extract text from a .docx package without flattening XML into one line.

# Ref: OOXML w:p / w:tbl reading order
"""

from __future__ import annotations

import io
import zipfile

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def _docx_paragraph_text(paragraph) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        local = _docx_local(node.tag)
        if local == "t" and node.text:
            parts.append(node.text)
        elif local in {"tab", "br"}:
            parts.append("\n" if local == "br" else "\t")
    return "".join(parts).strip()


def extract_docx_text(data: bytes) -> str:
    """Read Word paragraphs and table cells with newlines."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml")
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    lines: list[str] = []
    body = root.find(f"{W_NS}body")
    if body is None:
        body = root
    for child in list(body):
        local = _docx_local(child.tag)
        if local == "p":
            text = _docx_paragraph_text(child)
            if text:
                lines.append(text)
        elif local == "tbl":
            for row in child.iter(f"{W_NS}tr"):
                cells: list[str] = []
                for cell in row.findall(f"{W_NS}tc"):
                    cell_bits = [
                        _docx_paragraph_text(p)
                        for p in cell.findall(f"{W_NS}p")
                        if _docx_paragraph_text(p)
                    ]
                    cells.append(" ".join(cell_bits))
                row_text = " | ".join(c for c in cells if c)
                if row_text:
                    lines.append(row_text)
    return "\n".join(lines).strip()
