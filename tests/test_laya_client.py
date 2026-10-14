"""Laya System One client — config + noul parse. No live network."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from laya_client import LayaConfig, SystemOneResponse, load_laya_config


def test_heuristic_when_backend_forced(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_ONE_BACKEND", "heuristic")
    monkeypatch.setenv("LAYA_BASE_URL", "http://127.0.0.1:8080")
    cfg = load_laya_config()
    assert cfg.prefer_laya is False


def test_auto_prefers_laya_when_url_set(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_ONE_BACKEND", "auto")
    monkeypatch.setenv("LAYA_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    cfg = load_laya_config()
    assert cfg.prefer_laya is True
    assert cfg.url.endswith("/v1/systemone")
    assert cfg.model == "laya"


def test_parses_noul_answer() -> None:
    parsed = SystemOneResponse.model_validate(
        {
            "model": "laya",
            "answers": {"evaluate": {"type": "noul", "noul": 0.82}},
            "usage": {"input_tokens": 10},
        }
    )
    assert parsed.answers["evaluate"].noul == 0.82


def test_config_model_is_typed() -> None:
    cfg = LayaConfig()
    assert cfg.url == ""
    assert cfg.prefer_laya is False
