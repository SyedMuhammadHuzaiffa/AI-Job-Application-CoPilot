import logging
import os


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure application logging once for Streamlit, tests, and scripts."""
    selected_level = (level or os.getenv("JOB_COPILOT_LOG_LEVEL") or "INFO").upper()
    numeric_level = getattr(logging, selected_level, logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric_level)
        return
    logging.basicConfig(level=numeric_level, format=DEFAULT_LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
