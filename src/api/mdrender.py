"""Tiny offline markdown -> HTML renderer (no external dependency).

Good enough for viewing Agent 2 dossiers and Agent 4 checklists in the
detail drawer. Not a full CommonMark implementation.
"""
from __future__ import annotations

import html as html_mod
import re


def _inline(text: str) -> str:
    text = html_mod.escape(text)
    # bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # italic
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", text)
    # inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # links [t](u)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return text


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>"); in_ul = False
        if in_ol:
            out.append("</ol>"); in_ol = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("# "):
            close_lists(); out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            close_lists(); out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            close_lists(); out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if in_ol:
                out.append("</ol>"); in_ol = False
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif re.match(r"^\d+\.\s", line):
            if in_ul:
                out.append("</ul>"); in_ul = False
            if not in_ol:
                out.append("<ol>"); in_ol = True
            _ol_item = re.sub(r'^\d+\.\s', '', line)
            out.append(f"<li>{_inline(_ol_item)}</li>")
        elif not line.strip():
            close_lists(); out.append("")
        else:
            close_lists(); out.append(f"<p>{_inline(line)}</p>")
    close_lists()
    body = "\n".join(out)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:Inter,system-ui,sans-serif;color:#e2e8f0;background:#0b1120;"
        "max-width:760px;margin:0 auto;padding:20px;line-height:1.6}"
        "h1{color:#f59e0b;font-size:1.4rem;margin:1rem 0 .5rem}"
        "h2{color:#10b981;font-size:1.15rem;margin:1rem 0 .4rem}"
        "h3{color:#06b6d4;font-size:1rem;margin:.8rem 0 .3rem}"
        "a{color:#06b6d4} code{background:#1e293b;padding:1px 5px;border-radius:3px;color:#fbbf24}"
        "ul,ol{padding-left:1.4rem} li{margin:.2rem 0} p{margin:.4rem 0}"
        "</style></head><body>" + body + "</body></html>"
    )
