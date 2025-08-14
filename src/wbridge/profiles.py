"""
Deprecated shim for profile management.

This module is kept to avoid confusion and to ensure any legacy imports keep working.
The actual implementation lives in `profiles_manager.py`. Import and re-export the public API.
"""

from __future__ import annotations

from .profiles_manager import (
    list_builtin_profiles,
    show_profile,
    install_profile,
)

__all__ = [
    "list_builtin_profiles",
    "show_profile",
    "install_profile",
]
