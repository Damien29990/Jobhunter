"""People table: integer person_id, short tag, master flag, profile JSON path.

Chat history keys off people.id. The API alias ``default`` means whichever
row currently has is_master=1 — that identity can change.

# Ref: job_agent.db people + milo_chat_history.person_id
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

HK_TZ = ZoneInfo("Asia/Hong_Kong")
RESERVED_TAGS = frozenset({"default", "master", ""})
_TAG_RE = re.compile(r"[^A-Za-z0-9_-]+")


class PersonRecord(BaseModel):
    """One candidate stored in SQLite.

    # Ref: people table — tag is the short dashboard name, not default/master
    """

    model_config = ConfigDict(extra="forbid")
    id: int
    tag: str
    full_name: str = ""
    is_master: bool = False
    profile_path: str


def now_hk_iso() -> str:
    """Asia/Hong_Kong ISO 8601 second precision.

    # Ref: workspace rule — Asia/Hong_Kong UTC+8
    """
    return datetime.now(HK_TZ).isoformat(timespec="seconds")


def normalize_tag(raw: str) -> str:
    """Short people tag. Never default or master.

    # Ref: people.tag UNIQUE
    """
    tag = _TAG_RE.sub("-", (raw or "").strip()).strip("-_")
    if not tag or tag.lower() in RESERVED_TAGS:
        return ""
    return tag[:40]


def tag_for_profile_file(path: Path, full_name: str) -> str:
    """Derive a dashboard tag from the JSON filename and display name."""
    if path.name == "master_profile.json":
        parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
        first = normalize_tag(parts[0]) if parts else ""
        if first:
            return first
        joined = normalize_tag("-".join(parts)) if parts else ""
        return joined or "home"
    return normalize_tag(path.stem) or "person"


def relative_profile_path(path: Path, project_root: Path) -> str:
    """Store profile JSON location relative to the repo when possible."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def absolute_profile_path(stored: str, project_root: Path) -> Path:
    raw = Path(stored)
    if raw.is_absolute():
        return raw
    return project_root / raw


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create people, person_id on chat, and jd_full on job_postings.

    # Ref: job_agent.db migrations — safe on existing files
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL DEFAULT '',
            is_master INTEGER NOT NULL DEFAULT 0,
            profile_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS people_one_master "
            "ON people(is_master) WHERE is_master = 1"
        )
    except sqlite3.OperationalError:
        conn.execute("UPDATE people SET is_master = 0 WHERE id NOT IN (SELECT id FROM people WHERE is_master = 1 LIMIT 1)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS people_one_master "
            "ON people(is_master) WHERE is_master = 1"
        )
    chat_cols = {row[1] for row in conn.execute("PRAGMA table_info(milo_chat_history)").fetchall()}
    if chat_cols:
        if "person_id" not in chat_cols:
            conn.execute("ALTER TABLE milo_chat_history ADD COLUMN person_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS milo_chat_history_person_id "
            "ON milo_chat_history(person_id)"
        )
    job_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    if job_cols and "jd_full" not in job_cols:
        conn.execute("ALTER TABLE job_postings ADD COLUMN jd_full TEXT")
        conn.execute(
            "UPDATE job_postings SET jd_full = jd_snippet "
            "WHERE jd_full IS NULL OR TRIM(COALESCE(jd_full, '')) = ''"
        )


def _unique_tag(conn: sqlite3.Connection, desired: str, keep_id: Optional[int] = None) -> str:
    base = normalize_tag(desired) or "person"
    tag = base
    n = 2
    while True:
        row = conn.execute("SELECT id FROM people WHERE lower(tag) = lower(?)", (tag,)).fetchone()
        if row is None or (keep_id is not None and int(row[0]) == int(keep_id)):
            return tag
        tag = f"{base}-{n}"[:40]
        n += 1


def upsert_person(
    conn: sqlite3.Connection,
    *,
    tag: str,
    full_name: str,
    profile_path: str,
    is_master: bool = False,
) -> PersonRecord:
    """Insert or update a person keyed by profile_path.

    # Ref: people.profile_path UNIQUE
    """
    path = (profile_path or "").replace("\\", "/")
    name = (full_name or "").strip()
    existing = conn.execute(
        "SELECT id, tag, full_name, is_master, profile_path FROM people WHERE profile_path = ?",
        (path,),
    ).fetchone()
    if is_master:
        if existing:
            conn.execute(
                "UPDATE people SET is_master = 0 WHERE is_master = 1 AND id != ?",
                (int(existing[0]),),
            )
        else:
            conn.execute("UPDATE people SET is_master = 0 WHERE is_master = 1")
    if existing:
        person_id = int(existing[0])
        next_tag = _unique_tag(conn, tag or existing[1], keep_id=person_id)
        conn.execute(
            """
            UPDATE people SET tag = ?, full_name = ?, is_master = ?, profile_path = ?
            WHERE id = ?
            """,
            (next_tag, name or existing[2], 1 if is_master or existing[3] else 0, path, person_id),
        )
        if is_master:
            conn.execute("UPDATE people SET is_master = 1 WHERE id = ?", (person_id,))
            conn.execute("UPDATE people SET is_master = 0 WHERE id != ?", (person_id,))
    else:
        next_tag = _unique_tag(conn, tag)
        cur = conn.execute(
            """
            INSERT INTO people (tag, full_name, is_master, profile_path, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (next_tag, name, 1 if is_master else 0, path, now_hk_iso()),
        )
        person_id = int(cur.lastrowid)
        if is_master:
            conn.execute("UPDATE people SET is_master = 0 WHERE id != ?", (person_id,))
    row = conn.execute(
        "SELECT id, tag, full_name, is_master, profile_path FROM people WHERE id = ?",
        (person_id,),
    ).fetchone()
    assert row is not None
    return PersonRecord(
        id=int(row[0]),
        tag=str(row[1]),
        full_name=str(row[2] or ""),
        is_master=bool(row[3]),
        profile_path=str(row[4]),
    )


def _read_basics(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    basics = data.get("basics") if isinstance(data, dict) else {}
    if not isinstance(basics, dict):
        basics = {}
    name = str(basics.get("name") or "").strip()
    return name, tag_for_profile_file(path, name)


def sync_people_from_config(conn: sqlite3.Connection, project_root: Path) -> None:
    """Mirror config JSON files into people. One is_master row.

    # Ref: config/master_profile.json + config/profiles/{tag}.json
    """
    ensure_schema(conn)
    config_dir = project_root / "config"
    master = config_dir / "master_profile.json"
    profiles = config_dir / "profiles"
    files: list[tuple[Path, bool]] = []
    if master.is_file():
        files.append((master, True))
    if profiles.is_dir():
        for path in sorted(profiles.glob("*.json")):
            files.append((path, False))
    has_master = conn.execute("SELECT 1 FROM people WHERE is_master = 1 LIMIT 1").fetchone() is not None
    for path, is_master_file in files:
        rel = relative_profile_path(path, project_root)
        full_name, tag = _read_basics(path)
        existing = conn.execute(
            "SELECT is_master FROM people WHERE profile_path = ?", (rel,)
        ).fetchone()
        make_master = False
        if existing is not None:
            make_master = bool(existing[0])
        elif is_master_file and not has_master:
            make_master = True
            has_master = True
        upsert_person(
            conn,
            tag=tag,
            full_name=full_name,
            profile_path=rel,
            is_master=make_master,
        )
    if conn.execute("SELECT 1 FROM people WHERE is_master = 1 LIMIT 1").fetchone() is None:
        master_rel = relative_profile_path(master, project_root) if master.is_file() else ""
        if master_rel:
            conn.execute("UPDATE people SET is_master = 1 WHERE profile_path = ?", (master_rel,))
        else:
            conn.execute(
                "UPDATE people SET is_master = 1 WHERE id = (SELECT MIN(id) FROM people)"
            )
    _backfill_chat_person_id(conn)


def _backfill_chat_person_id(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(milo_chat_history)").fetchall()}
    if "person_id" not in cols:
        return
    master = conn.execute("SELECT id FROM people WHERE is_master = 1 LIMIT 1").fetchone()
    master_id = int(master[0]) if master else None
    dangling = conn.execute(
        "SELECT DISTINCT candidate_id FROM milo_chat_history "
        "WHERE person_id IS NULL AND candidate_id IS NOT NULL"
    ).fetchall()
    for (cid,) in dangling:
        key = str(cid or "").strip()
        person_id: Optional[int] = None
        if key.lower() in RESERVED_TAGS:
            person_id = master_id
        else:
            row = conn.execute("SELECT id FROM people WHERE lower(tag) = lower(?)", (key,)).fetchone()
            if row:
                person_id = int(row[0])
            else:
                person_id = master_id
        if person_id is not None:
            conn.execute(
                "UPDATE milo_chat_history SET person_id = ? "
                "WHERE person_id IS NULL AND candidate_id = ?",
                (person_id, cid),
            )


def get_person(conn: sqlite3.Connection, person_id: int) -> Optional[PersonRecord]:
    row = conn.execute(
        "SELECT id, tag, full_name, is_master, profile_path FROM people WHERE id = ?",
        (int(person_id),),
    ).fetchone()
    if not row:
        return None
    return PersonRecord(
        id=int(row[0]),
        tag=str(row[1]),
        full_name=str(row[2] or ""),
        is_master=bool(row[3]),
        profile_path=str(row[4]),
    )


def resolve_person(conn: sqlite3.Connection, ref: Optional[str]) -> Optional[PersonRecord]:
    """Map API ref (tag, integer id, or default) to a people row.

    ``default`` is the current is_master person, not a stored tag.
    """
    key = str(ref or "").strip()
    if not key or key.lower() in RESERVED_TAGS:
        row = conn.execute(
            "SELECT id, tag, full_name, is_master, profile_path FROM people "
            "WHERE is_master = 1 LIMIT 1"
        ).fetchone()
    elif key.isdigit():
        row = conn.execute(
            "SELECT id, tag, full_name, is_master, profile_path FROM people WHERE id = ?",
            (int(key),),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, tag, full_name, is_master, profile_path FROM people "
            "WHERE lower(tag) = lower(?)",
            (key,),
        ).fetchone()
    if not row:
        return None
    return PersonRecord(
        id=int(row[0]),
        tag=str(row[1]),
        full_name=str(row[2] or ""),
        is_master=bool(row[3]),
        profile_path=str(row[4]),
    )


def list_people(conn: sqlite3.Connection) -> list[PersonRecord]:
    rows = conn.execute(
        "SELECT id, tag, full_name, is_master, profile_path FROM people "
        "ORDER BY is_master DESC, tag COLLATE NOCASE"
    ).fetchall()
    return [
        PersonRecord(
            id=int(row[0]),
            tag=str(row[1]),
            full_name=str(row[2] or ""),
            is_master=bool(row[3]),
            profile_path=str(row[4]),
        )
        for row in rows
    ]


def resolve_profile_path_for_ref(
    conn: sqlite3.Connection,
    ref: Optional[str],
    project_root: Path,
) -> Optional[Path]:
    person = resolve_person(conn, ref)
    if person is None:
        return None
    return absolute_profile_path(person.profile_path, project_root)
