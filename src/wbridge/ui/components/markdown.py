# SPDX-License-Identifier: MIT
# Minimal Markdown -> Pango-Markup converter for help content
# Subset supported: headings (#, ##), bullet lists (-, *), inline code `code`,
# fenced code blocks ``` ``` , bold **text**, italic *text*
# No external dependencies.

from __future__ import annotations
import re
from typing import List
from html import escape as _html_escape


_HEADING_1 = re.compile(r"^\s*# (.+?)\s*$")
_HEADING_2 = re.compile(r"^\s*## (.+?)\s*$")
_HEADING_3 = re.compile(r"^\s*### (.+?)\s*$")
_BULLET = re.compile(r"^(\s*)[-\*] (.+)$")
_INLINE_CODE = re.compile(r"`([^`]+?)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
# Basic italic that avoids conflicting with bold (**): single * on both sides
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _escape_pango(text: str) -> str:
    # Robust HTML escaping for Pango markup (no un-escaping)
    return _html_escape(text, quote=False)


def _escape_basic(text: str) -> str:
    # Basic HTML escaping; do not un-escape later
    return _html_escape(text, quote=False)


def _format_inline(text: str) -> str:
    # Apply inline formatting to already-escaped text
    # Order: code, bold, italic
    def repl_code(m: re.Match) -> str:
        inner = m.group(1)
        inner = _escape_basic(inner)
        return f"<span font_family='monospace'>{inner}</span>"

    text = _INLINE_CODE.sub(repl_code, text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    return text


def md_to_pango(md: str) -> str:
    """
    Convert a minimal subset of Markdown to Pango markup.
    - returns a string suitable for Gtk.Label(use_markup=True)
    - preserves newlines
    """
    if not md:
        return ""

    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    out: List[str] = []
    in_code_block = False
    code_block_lines: List[str] = []

    fence_re = re.compile(r"^\s*```")  # language ignored

    for raw in lines:
        if fence_re.match(raw):
            if not in_code_block:
                # starting a code block
                in_code_block = True
                code_block_lines = []
            else:
                # closing a code block - emit block
                in_code_block = False
                code_text = "\n".join(code_block_lines)
                code_text = _escape_basic(code_text)
                out.append(f"<span font_family='monospace'>{code_text}</span>")
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(raw)
            continue

        # Normal line processing
        line = raw

        # Headings
        m = _HEADING_1.match(line)
        if m:
            txt = _format_inline(_escape_basic(m.group(1).strip()))
            out.append(f"<span weight='bold' size='x-large'>{txt}</span>")
            continue

        m = _HEADING_2.match(line)
        if m:
            txt = _format_inline(_escape_basic(m.group(1).strip()))
            out.append(f"<span weight='bold' size='large'>{txt}</span>")
            continue

        m = _HEADING_3.match(line)
        if m:
            txt = _format_inline(_escape_basic(m.group(1).strip()))
            out.append(f"<span weight='bold' size='medium'>{txt}</span>")
            continue

        # Bullets
        m = _BULLET.match(line)
        if m:
            indent = m.group(1)
            body = m.group(2)
            body = _format_inline(_escape_basic(body.strip()))
            out.append(f"{indent}• {body}")
            continue

        # Paragraph / plain line
        txt = _format_inline(_escape_basic(line))
        out.append(txt)

    # If file ends while still in a code block, flush it
    if in_code_block and code_block_lines:
        code_text = "\n".join(code_block_lines)
        code_text = _escape_basic(code_text)
        out.append(f"<span font_family='monospace'>{code_text}</span>")

    # Join with newlines. Gtk.Label will honor '\n' with wrap enabled.
    return "\n".join(out)
