"""Application logging to stderr."""

from __future__ import annotations

import logging
import os
import sys

LOGGER_NAME = "ktrmnl"


def configure(runtime: str = "device") -> logging.Logger:
    """Configure process-wide application logging once.

    Messages go to stderr. ``KTRMNL_LOG_LEVEL`` selects the logging level;
    use ``DEBUG`` for detailed content and network diagnostics.
    """

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    level_name = os.environ.get("KTRMNL_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logging.captureWarnings(True)
    logger.info("logging initialized runtime=%s level=%s", runtime, level_name)
    return logger
