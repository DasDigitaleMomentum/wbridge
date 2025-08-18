"""Help panel component for wbridge GUI pages.

Provides small helpers to render expandable help content from markdown
files stored under src/wbridge/help/en/*.md.
"""

from __future__ import annotations

import gettext
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # type: ignore


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


def build_help_panel(topic: str) -> Gtk.Widget:
    """Create an expander with help content for the given topic."""
    try:
        exp = Gtk.Expander(label=_("Help"))
    except Exception:
        exp = Gtk.Expander(label="Help")
    try:
        content = _render_help(_load_help_text(topic))
        exp.set_child(content)
    except Exception:
        # Ignore rendering issues silently (non-critical UI)
        pass
    exp.set_hexpand(True)
    return exp


def _load_help_text(topic: str) -> str:
    """Load help text from src/wbridge/help/en/{topic}.md."""
    try:
        # components/help_panel.py -> parents[2] == src/wbridge
        base = Path(__file__).resolve().parents[2] / "help" / "en"
        path = base / f"{topic}.md"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return f"{topic} – help not found (resource missing)."
    except Exception as e:
        return f"Help load failed for topic '{topic}': {e!r}"


def _render_help(text: str) -> Gtk.Widget:
    """Render plain text help into a read-only TextView inside a scroller."""
    tv = Gtk.TextView()
    tv.set_monospace(True)
    tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    tv.set_editable(False)
    tv.set_cursor_visible(False)
    buf = tv.get_buffer()
    buf.set_text(text, -1)
    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sc.set_min_content_height(160)
    sc.set_child(tv)
    return sc
