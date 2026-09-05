"""
Structured Operational Logging Foundation
Configures standard stream logging with secret masking to prevent token/key leaks.
"""

import logging
import sys

from app.core.config import settings


class SecretMaskingFormatter(logging.Formatter):
    """Custom logging formatter that strips/masks sensitive tokens & keys from log outputs."""

    SENSITIVE_PATTERNS = [
        "SUPABASE_SERVICE_ROLE_KEY",
        "GEMINI_API_KEY",
        "REVENUECAT_SECRET_KEY",
        "REVENUECAT_WEBHOOK_AUTH_TOKEN",
        "REVENUECAT_WEBHOOK_SIGNING_SECRET",
        "Bearer ",
    ]

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        # Ensure raw secret values are masked if accidentally included in log messages
        for secret_val in [
            settings.SUPABASE_SERVICE_ROLE_KEY,
            settings.GEMINI_API_KEY,
            settings.REVENUECAT_SECRET_KEY,
            settings.REVENUECAT_WEBHOOK_AUTH_TOKEN,
            settings.REVENUECAT_WEBHOOK_SIGNING_SECRET,
        ]:
            if secret_val and len(secret_val) > 4 and secret_val in formatted:
                formatted = formatted.replace(secret_val, "***REDACTED_SECRET***")
        return formatted


def setup_logging() -> logging.Logger:
    """Initialize structured logger for the application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger("internmatch_backend")
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = SecretMaskingFormatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()


def get_logger(name: str = "internmatch_backend") -> logging.Logger:
    """Retrieve logger instance with secret masking formatter configured."""
    setup_logging()
    return logging.getLogger(name)
