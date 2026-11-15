"""Structured logging setup.

Never logs secrets, tokens, or full document contents.
"""

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=_FORMAT,
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger("mnemos")
