"""Jev-compatible System One client for Laya (or hosted TypeSafe).

Laya answers typed noul / choice / score — it does not generate prose.
Hard gates stay in system_one.py; this module only classifies.

# Ref: Convai Laya + TypeSafe Jev POST /v1/systemone
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

# Fail fast so Rex never blocks on a down classifier.
LAYA_TIMEOUT_SEC: float = 3.0
JD_STATE_CHARS: int = 1500


class LayaConfig(BaseModel):
    """Resolved System One transport. Empty url means heuristic-only.

    # Ref: .env SYSTEM_ONE_* / LAYA_* / TYPESAFE_API_KEY
    """

    url: str = ""
    api_key: str = ""
    model: str = "laya"
    prefer_laya: bool = False


class LooseAnswer(BaseModel):
    """One /v1/systemone answer. Only noul is used by Jobhunter gates.

    # Ref: Jev noul — probability in [0, 1]
    """

    model_config = ConfigDict(extra="ignore")

    noul: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SystemOneResponse(BaseModel):
    """Minimal Jev-compatible response. Extra fields ignored.

    # Ref: TypeSafe /v1/systemone answers map
    """

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    answers: dict[str, LooseAnswer] = Field(default_factory=dict)


def load_laya_config() -> LayaConfig:
    """Read env. Local laya-serve needs a URL; hosted Jev needs a Bearer key."""
    backend = (os.environ.get("SYSTEM_ONE_BACKEND") or "auto").strip().lower()
    url = (os.environ.get("SYSTEM_ONE_URL") or os.environ.get("LAYA_BASE_URL") or "").strip()
    key = (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("LAYA_API_KEY") or "").strip()
    model = (os.environ.get("SYSTEM_ONE_MODEL") or "").strip()
    if url and not url.rstrip("/").endswith("systemone"):
        url = url.rstrip("/") + "/v1/systemone"
    if not url and key:
        url = "https://api.typesafe.ai/v1/systemone"
        model = model or "jev-latest"
    if not model:
        model = "laya"
    prefer = backend == "laya" or (backend == "auto" and bool(url))
    if backend == "heuristic":
        prefer = False
    return LayaConfig(url=url, api_key=key, model=model, prefer_laya=prefer)


def ask_noul(state: str, instructions: str, *, name: str = "gate") -> Optional[float]:
    """Return a calibrated yes-probability, or None if Laya is off / failed.

    # Ref: noul — branch on probability, never parse prose
    """
    cfg = load_laya_config()
    if not cfg.prefer_laya or not cfg.url:
        return None
    payload = {
        "model": cfg.model,
        "state": state[:JD_STATE_CHARS],
        "questions": {
            name: {"type": "noul", "instructions": instructions},
        },
    }
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    try:
        with httpx.Client(timeout=LAYA_TIMEOUT_SEC) as client:
            res = client.post(cfg.url, json=payload, headers=headers)
            res.raise_for_status()
            parsed = SystemOneResponse.model_validate(res.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    answer = parsed.answers.get(name)
    if answer is None or answer.noul is None:
        return None
    return float(answer.noul)
