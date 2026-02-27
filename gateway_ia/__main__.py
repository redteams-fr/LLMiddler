from __future__ import annotations

import logging
import sys

import uvicorn
from loguru import logger

from gateway_ia.app import create_app
from gateway_ia.config import load_config


class _InterceptHandler(logging.Handler):
    """Route all stdlib logging records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        logger.patch(
            lambda r: r.update(
                name=record.name,
                function=record.funcName,
                line=record.lineno,
            )
        ).opt(exception=record.exc_info).log(level, record.getMessage())


def _make_log_filter(log_level: str, ui_prefix: str, quiet: bool):
    """Build a loguru filter that enforces per-module levels and hides UI access logs."""
    level_no = logger.level(log_level).no
    httpx_no = logger.level("DEBUG").no if log_level == "DEBUG" else logger.level("WARNING").no

    def _filter(record):
        name = record["name"] or ""
        # Per-module level control
        if name.startswith(("httpx", "httpcore")):
            if record["level"].no < httpx_no:
                return False
        elif record["level"].no < level_no:
            return False
        # Filter out UI access-log noise
        if not quiet and name == "uvicorn.access" and ui_prefix in record["message"]:
            return False
        return True

    return _filter


def main() -> None:
    config = load_config()
    log_level = config.logging.level.upper()

    # Configure loguru
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        filter=_make_log_filter(log_level, config.ui.prefix, config.logging.quiet),
        level=0,
    )

    # Intercept all stdlib logging → loguru
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.listen.host,
        port=config.listen.port,
        log_level=log_level.lower(),
        log_config=None,
        access_log=not config.logging.quiet,
    )


if __name__ == "__main__":
    main()
