"""Fetch a LinkedIn profile through Jobhunter's MCP child process (not Cursor).

Usage (cmd.exe, repo root):

  python scripts\\fetch_linkedin_mcp.py lychee-lai-351b03330

Auth: run `uvx linkedin-api-mcp auth` once, or set LINKEDIN_COOKIE in .env.
This script never prints the cookie. Raw JSON is written under
config/linkedin_mcp/{handle}_raw.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "src" / "agents"
VALIDATORS = ROOT / "src" / "validators"
for extra in (AGENTS, VALIDATORS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from linkedin_mcp_client import dump_linkedin_mcp  # noqa: E402


def main(argv: list[str]) -> int:
    raw = (argv[1] if len(argv) > 1 else "lychee-lai-351b03330").strip()
    try:
        debug = dump_linkedin_mcp(raw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = str(debug.get("out_path") or "")
    summary = {
        "ok": bool(debug.get("payload")),
        "error": debug.get("error") or "",
        "tools": debug.get("tools") or [],
        "command": debug.get("command") or [],
        "out_path": out_path,
        "payload_keys": sorted((debug.get("payload") or {}).keys())
        if isinstance(debug.get("payload"), dict)
        else [],
        "stderr_tail": (debug.get("stderr_tail") or "")[-800:],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    payload = debug.get("payload")
    if isinstance(payload, dict):
        print("\n--- payload ---\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif out_path:
        print(f"\nNo payload. Open {out_path} for raw MCP replies.")
    return 0 if debug.get("payload") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
