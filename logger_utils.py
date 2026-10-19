"""Centralized logging configuration module for EDMC plugins.

This module initializes and configures the core logger for the plugin,
ensuring a standardized output format for all log messages.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import appname

plugin_name = Path(__file__).parent.name


def setup_logger() -> logging.Logger:
    """Configure and return the primary plugin logger.

    This function should be called within the main plugin entry point
    (e.g., load.py) during initialization.

    Returns:
        logging.Logger: The fully configured logger instance.
    """
    logger = logging.getLogger(f"{appname}.{plugin_name}")

    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)

        logger_channel = logging.StreamHandler()
        logger_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d:%(funcName)s: %(message)s"
        )
        logger_formatter.default_time_format = "%Y-%m-%d %H:%M:%S"
        logger_formatter.default_msec_format = "%s.%03d"

        logger_channel.setFormatter(logger_formatter)
        logger.addHandler(logger_channel)

    return logger


# Global logger instance ready to be imported across plugin modules
logger: logging.Logger = setup_logger()
