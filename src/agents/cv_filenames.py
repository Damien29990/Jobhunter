"""Filesystem-safe tailored-CV filenames.

# Ref: dashboard download — {job_name}_{user_name}_cv.pdf
"""

from __future__ import annotations

import re


def filename_token(value: str, fallback: str = "file") -> str:
    """Turn a job title or person name into a single path-safe token."""
    cleaned = re.sub(r'[<>:"/\\|?*,;]+', " ", value or "")
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return (cleaned[:80] or fallback).strip("._") or fallback


def cv_download_filename(job_title: str, user_name: str, ext: str = "pdf") -> str:
    """Return `{job_name}_{user_name}_cv.{ext}` for Content-Disposition / disk."""
    job = filename_token(job_title, "job")
    user = filename_token(user_name, "candidate")
    suffix = (ext or "pdf").lstrip(".").lower() or "pdf"
    return f"{job}_{user}_cv.{suffix}"
