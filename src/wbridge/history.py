"""
History management for clipboard and primary selections.

- In-memory ring buffers per selection type.
- Dedupe consecutive duplicates.
- Apply entry to clipboard/primary (to be wired from the GTK app).

This module does not talk to GTK directly; the GUI layer should call into this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RingBuffer:
    max_size: int = 50
    items: List[str] = field(default_factory=list)

    def add_front(self, text: str) -> None:
        if not text:
            return
        if self.items and self.items[0] == text:
            return  # dedupe consecutive duplicates
        self.items.insert(0, text)
        if len(self.items) > self.max_size:
            self.items.pop()

    def get(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def list(self, limit: Optional[int] = None) -> List[str]:
        if limit is None:
            return list(self.items)
        return list(self.items[: max(0, limit)])

    def swap_last_two(self) -> bool:
        if len(self.items) < 2:
            return False
        self.items[0], self.items[1] = self.items[1], self.items[0]
        return True


class HistoryStore:
    """
    Holds two ring buffers: one for the clipboard and one for the primary selection.
    """

    def __init__(self, max_size: int = 50) -> None:
        self.clipboard = RingBuffer(max_size=max_size)
        self.primary = RingBuffer(max_size=max_size)

    def add_clipboard(self, text: str) -> None:
        self.clipboard.add_front(text)

    def add_primary(self, text: str) -> None:
        self.primary.add_front(text)

    def list(self, which: str, limit: Optional[int] = None) -> List[str]:
        rb = self._resolve(which)
        return rb.list(limit)

    def get(self, which: str, index: int) -> Optional[str]:
        rb = self._resolve(which)
        return rb.get(index)

    def swap_last_two(self, which: str) -> bool:
        rb = self._resolve(which)
        return rb.swap_last_two()

    def _resolve(self, which: str) -> RingBuffer:
        key = (which or "clipboard").lower()
        if key == "primary":
            return self.primary
        return self.clipboard
