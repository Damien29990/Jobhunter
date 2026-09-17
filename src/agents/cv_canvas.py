"""Leo's CV Template Canvas — local catalog of Typst/Jinja layouts.

Leo calls list/get/pick as tools before rendering. Layout choice is
deterministic from the JD text, not an LLM guess.

# Ref: templates/canvas/manifest.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent.parent
CANVAS_DIR = PROJECT_ROOT / "templates" / "canvas"
MANIFEST_PATH = CANVAS_DIR / "manifest.json"
DEFAULT_TEMPLATE_ID = "classic"


class CanvasTemplate(BaseModel):
    """One layout Leo can load from the Canvas catalog.

    # Ref: templates/canvas/manifest.json
    """

    id: str
    name: str
    file: str
    when: str = ""
    keywords: List[str] = Field(default_factory=list)


def load_canvas_manifest(path: Path = MANIFEST_PATH) -> List[CanvasTemplate]:
    """Read the Canvas catalog. Empty list if the manifest is missing."""
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("templates") or []
    return [CanvasTemplate.model_validate(row) for row in rows]


def list_canvas_templates(path: Path = MANIFEST_PATH) -> List[CanvasTemplate]:
    """Tool: list layouts available on the Canvas."""
    return load_canvas_manifest(path)


def get_canvas_template(
    template_id: str,
    path: Path = MANIFEST_PATH,
) -> CanvasTemplate:
    """Tool: load one Canvas layout by id. Falls back to classic."""
    catalog = load_canvas_manifest(path)
    needle = (template_id or "").strip().lower()
    for item in catalog:
        if item.id.lower() == needle:
            return item
    for item in catalog:
        if item.id == DEFAULT_TEMPLATE_ID:
            return item
    if catalog:
        return catalog[0]
    return CanvasTemplate(
        id=DEFAULT_TEMPLATE_ID,
        name="ATS Classic",
        file="resume.typ.j2",
        when="Built-in fallback",
    )


def pick_canvas_template(
    jd_text: str = "",
    job_title: str = "",
    forced_id: Optional[str] = None,
    path: Path = MANIFEST_PATH,
) -> CanvasTemplate:
    """Tool: choose a Canvas layout. Forced id wins; else first keyword hit.

    Compact is checked before technical so a one-page engineering JD stays compact.
    # Ref: Leo template selection — deterministic
    """
    if (forced_id or "").strip():
        return get_canvas_template(forced_id, path=path)
    blob = f"{job_title}\n{jd_text}".lower()
    catalog = load_canvas_manifest(path)
    ranked = [item for item in catalog if item.id != DEFAULT_TEMPLATE_ID] + [
        item for item in catalog if item.id == DEFAULT_TEMPLATE_ID
    ]
    for item in ranked:
        for keyword in item.keywords:
            if keyword.lower() in blob:
                return item
    return get_canvas_template(DEFAULT_TEMPLATE_ID, path=path)
