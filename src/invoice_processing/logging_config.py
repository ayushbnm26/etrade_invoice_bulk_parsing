from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
from typing import Iterator


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_dir / "invoice_processing.log", encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)


@contextmanager
def capture_invoice_logs(log_dir: Path, log_file_name: str = "invoice_processing.log") -> Iterator[Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file_name

    logger = logging.getLogger("invoice_processing")
    previous_level = logger.level
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    try:
        yield log_path
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()
        logger.setLevel(previous_level)


def flush_invoice_logs() -> None:
    for handler in logging.getLogger("invoice_processing").handlers:
        handler.flush()
