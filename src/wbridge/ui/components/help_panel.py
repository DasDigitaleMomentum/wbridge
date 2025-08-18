"""Help panel component for wbridge GUI pages.

Behavior:
- Popover-only: Gtk.Popover containing Markdown rendered to Pango-Markup.
  The popover is attached to the Help button in the page header and uses
  dynamic width (~60–65% of the window, min 520px). No Revealer mode anymore.

Help markdown files are stored under src/wbridge/help/en/*.md.
"""

from __future__ import annotations

import gettext
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # type: ignore

from .markdown import md_to_pango


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


def build_help_panel(topic: str, mode: str | None = None) -> Gtk.Widget:
    """
    Create a help widget (Popover-only).
    The 'mode' parameter is accepted for backward compatibility but ignored.
    """
    text = _load_help_text(topic)
    content_label = _render_help_pango(text)

    # Wrap content in a scroller (min-height/width controlled by CSS; also set fallback)
    sc = Gtk.ScrolledWindow()
    # Breiteres, ergonomisches Popover: keine horizontale Scrollbar, Höhe automatisch
    try:
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    except Exception:
        pass
    try:
        # natürliche Breite vom Kind übernehmen (GTK4)
        sc.set_propagate_natural_width(True)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        sc.set_min_content_height(160)
        sc.set_min_content_width(520)
    except Exception:
        pass
    sc.set_child(content_label)

    # Popover-only (mode parameter is ignored)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    try:
        box.add_css_class("help-popover")
    except Exception:
        pass
    # margins as fallback if CSS not applied
    try:
        box.set_margin_top(6); box.set_margin_bottom(6); box.set_margin_start(8); box.set_margin_end(8)
    except Exception:
        pass
    box.append(sc)
    pop = Gtk.Popover()
    try:
        pop.set_has_arrow(True)
        pop.set_autohide(True)
    except Exception:
        pass
    pop.set_child(box)
    return pop


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


def _render_help_pango(text: str) -> Gtk.Widget:
    """Render Markdown text as Pango-Markup into a Gtk.Label."""
    try:
        markup = md_to_pango(text or "")
    except Exception:
        # Fallback to plain text if markdown conversion fails
        markup = (text or "")

    lbl = Gtk.Label()
    lbl.set_use_markup(True)
    lbl.set_wrap(True)
    lbl.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    lbl.set_xalign(0.0)
    try:
        lbl.set_markup(markup)
    except Exception:
        # If markup fails (malformed), show as plain text
        lbl.set_text(text or "")
    return lbl
