"""
SelectionMonitor: GTK4/GDK-based polling of clipboard and primary selections.

- Uses GLib.timeout_add to periodically schedule async reads on the GTK main loop.
- Dedupe consecutive duplicates and invoke a callback on changes.
- No external tools; works under Wayland via Gdk.Display APIs.

Intended use:
    from .selection_monitor import SelectionMonitor
    monitor = SelectionMonitor(interval_ms=300, on_change=handle_change)
    monitor.start()
    ...
    monitor.stop()

Callback signature:
    on_change(which: str, text: str) where which in {"clipboard","primary"}
"""

from __future__ import annotations

import gi
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gdk, GLib  # type: ignore
from typing import Callable, Optional


class SelectionMonitor:
    def __init__(self, interval_ms: int = 300, on_change: Optional[Callable[[str, str], None]] = None) -> None:
        self._interval_ms = max(50, int(interval_ms))
        self._on_change = on_change
        self._running = False

        self._display: Optional[object] = None
        self._cache_clip: Optional[str] = None
        self._cache_prim: Optional[str] = None

    def _ensure_display(self) -> object:
        if self._display is None:
            try:
                self._display = Gdk.Display.get_default()
            except Exception:
                self._display = None
        return self._display

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        GLib.timeout_add(self._interval_ms, self._tick)  # type: ignore

    def stop(self) -> None:
        # We cannot cancel timeout_add directly; we use the _running flag to stop rescheduling.
        self._running = False

    def _tick(self) -> bool:
        if not self._running:
            return False
        try:
            disp = self._ensure_display()
            if disp is None:
                return True  # try again next tick

            clip = disp.get_clipboard()  # type: ignore[attr-defined]
            prim = disp.get_primary_clipboard()  # type: ignore[attr-defined]

            # Schedule async reads; callbacks will dedupe and notify.
            clip.read_text_async(None, self._on_read, "clipboard")  # type: ignore[arg-type]
            prim.read_text_async(None, self._on_read, "primary")  # type: ignore[arg-type]
        except Exception:
            # Keep ticking even if a read fails once
            pass
        return True

    def _on_read(self, source, res, which: str) -> None:
        try:
            text = source.read_text_finish(res) or ""
        except Exception:
            text = ""

        text_stripped = text.strip()
        if not text_stripped:
            return

        if which == "clipboard":
            if text != self._cache_clip:
                self._cache_clip = text
                if self._on_change:
                    self._on_change("clipboard", text)
        else:
            if text != self._cache_prim:
                self._cache_prim = text
                if self._on_change:
                    self._on_change("primary", text)
