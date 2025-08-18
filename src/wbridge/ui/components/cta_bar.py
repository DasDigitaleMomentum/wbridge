# SPDX-License-Identifier: MIT
# Unified bottom Call-To-Action bar container.
# Places provided buttons aligned to the right, within a full-width horizontal box.

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # type: ignore


def build_cta_bar(*buttons: Gtk.Widget) -> Gtk.Widget:
    """
    Build a horizontal CTA bar with right-aligned buttons.
    Usage: container.append(build_cta_bar(btn1, btn2, ...))
    """
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    bar.set_hexpand(True)
    try:
        bar.add_css_class("cta-bar")
    except Exception:
        pass

    # Spacer to push buttons to the right
    spacer = Gtk.Box()
    spacer.set_hexpand(True)
    bar.append(spacer)

    for b in buttons:
        if isinstance(b, Gtk.Widget):
            bar.append(b)

    return bar
