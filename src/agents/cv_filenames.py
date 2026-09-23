"""Filesystem-safe tailored application-document filenames.

# Ref: dashboard download — {job_name}_{user_name}_{cv|cover_letter}.{ext}
"""

from __future__ import annotations

import re

_ALLOWED_KINDS = frozenset({"cv", "cover_letter"})


def filename_token(value: str, fallback: str = "file") -> str:
    """Turn a job title or person name into a single path-safe token."""
    cleaned = re.sub(r'[<>:"/\\|?*,;]+', " ", value or "")
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return (cleaned[:80] or fallback).strip("._") or fallback


def materials_filename(
    job_title: str,
    user_name: str,
    kind: str = "cv",
    ext: str = "pdf",
) -> str:
    """Return `{job_name}_{user_name}_{kind}.{ext}` for Content-Disposition / disk."""
    job = filename_token(job_title, "job")
    user = filename_token(user_name, "candidate")
    suffix = (ext or "pdf").lstrip(".").lower() or "pdf"
    slug = (kind or "cv").strip().lower().replace(" ", "_")
    if slug not in _ALLOWED_KINDS:
        slug = "cv"
    return f"{job}_{user}_{slug}.{suffix}"


def cv_download_filename(job_title: str, user_name: str, ext: str = "pdf") -> str:
    """Return `{job_name}_{user_name}_cv.{ext}` for Content-Disposition / disk."""
    return materials_filename(job_title, user_name, "cv", ext)


def cover_letter_filename(job_title: str, user_name: str, ext: str = "pdf") -> str:
    """Return `{job_name}_{user_name}_cover_letter.{ext}`."""
    return materials_filename(job_title, user_name, "cover_letter", ext)
