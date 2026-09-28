"""People table, master uniqueness, and chat person_id."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from people_store import (
    ensure_schema,
    list_people,
    resolve_person,
    sync_people_from_config,
    tag_for_profile_file,
    upsert_person,
)


def test_tag_never_default_or_master() -> None:
    assert tag_for_profile_file(Path("config/master_profile.json"), "Damien Yu") == "Damien"
    assert tag_for_profile_file(Path("config/profiles/Lychee.json"), "Lychee Lai") == "Lychee"


def test_people_and_chat_use_integer_id(tmp_path: Path) -> None:
    root = tmp_path
    config = root / "config"
    profiles = config / "profiles"
    profiles.mkdir(parents=True)
    master = config / "master_profile.json"
    master.write_text(
        json.dumps({"basics": {"name": "Damien Yu"}}),
        encoding="utf-8",
    )
    (profiles / "Lychee.json").write_text(
        json.dumps({"basics": {"name": "Lychee Lai"}}),
        encoding="utf-8",
    )
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE milo_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE job_postings (
            id INTEGER PRIMARY KEY,
            jd_snippet TEXT
        )
        """
    )
    conn.execute("INSERT INTO job_postings (id, jd_snippet) VALUES (1, 'short')")
    conn.execute(
        "INSERT INTO milo_chat_history (candidate_id, role, content, created_at) "
        "VALUES ('default', 'user', 'hello master', '2026-09-24T10:00:00+08:00')"
    )
    ensure_schema(conn)
    sync_people_from_config(conn, root)
    people = list_people(conn)
    assert len(people) == 2
    masters = [p for p in people if p.is_master]
    assert len(masters) == 1
    assert masters[0].tag != "default"
    assert masters[0].tag != "master"
    lychee = resolve_person(conn, "Lychee")
    assert lychee is not None
    assert lychee.is_master is False
    aliased = resolve_person(conn, "default")
    assert aliased is not None
    assert aliased.id == masters[0].id
    row = conn.execute(
        "SELECT person_id FROM milo_chat_history WHERE content = 'hello master'"
    ).fetchone()
    assert row is not None
    assert int(row[0]) == masters[0].id
    full = conn.execute("SELECT jd_full FROM job_postings WHERE id = 1").fetchone()
    assert full is not None
    assert full[0] == "short"
    conn.close()


def test_only_one_master() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    first = upsert_person(
        conn, tag="Damien", full_name="Damien Yu",
        profile_path="config/master_profile.json", is_master=True,
    )
    second = upsert_person(
        conn, tag="Lychee", full_name="Lychee Lai",
        profile_path="config/profiles/Lychee.json", is_master=True,
    )
    people = list_people(conn)
    masters = [p for p in people if p.is_master]
    assert len(masters) == 1
    assert masters[0].id == second.id
    assert resolve_person(conn, "default").id == second.id
    assert first.id != second.id
    conn.close()
