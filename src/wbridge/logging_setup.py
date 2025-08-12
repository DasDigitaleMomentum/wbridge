"""
Logging setup for wbridge.

- Logs to console (stdout) and to a file under XDG state dir.
- Default level: INFO. Can be overridden via environment variable WBRIDGE_LOG_LEVEL.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .platform import xdg_state_dir


def setup_logging() -> logging.Logger:
    level_name = os.environ.get("WBRIDGE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_dir: Path = xdg_state_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bridge.log"

    logger = logging.getLogger("wbridge")
    logger.setLevel(level)
    logger.propagate = False  # avoid duplicate logs

    # Clear existing handlers if any (idempotent setup)
    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (rotating)
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.debug("Logging initialized at level %s", level_name)
    logger.info("Log file: %s", str(log_file))
    return logger
