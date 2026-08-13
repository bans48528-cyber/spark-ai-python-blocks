"""Paths that work both from source and from a PyInstaller release folder."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the bundled resource directory, or the repository root in source mode."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parents[1]


def application_root() -> Path:
    """Return the user-visible release directory, or the repository root in source mode."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return resource_root()
