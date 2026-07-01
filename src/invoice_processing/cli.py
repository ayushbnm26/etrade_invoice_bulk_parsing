from __future__ import annotations

import argparse
import logging
from pathlib import Path

from invoice_processing.bulk_processing import BulkInvoiceProcessor
from invoice_processing.config import DEFAULT_INPUT_DIR, DEFAULT_LOG_DIR, DEFAULT_OUTPUT_DIR
from invoice_processing.logging_config import setup_logging
from invoice_processing.upload_validation import build_uploaded_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Etrade invoice PDFs into one bulk team workbook.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Folder containing uploaded files.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Folder for generated artifacts.")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="Folder for runtime logs.")
    parser.add_argument("--log-level", default="INFO", help="Python log level, for example INFO or DEBUG.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_dir.resolve(), args.log_level)
    logger = logging.getLogger(__name__)

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("Input folder does not exist or is not a folder: %s", input_dir)
        return 2

    files = sorted(path for path in input_dir.iterdir() if path.is_file())
    if not files:
        logger.error("No input files found in: %s", input_dir)
        return 2

    uploads = [
        build_uploaded_file(index, path.name, path.read_bytes())
        for index, path in enumerate(files, start=1)
    ]

    try:
        result = BulkInvoiceProcessor().process(uploads, work_dir=output_dir / "bulk_run")
    except Exception as exc:
        logger.exception("Bulk processing failed: %s", exc)
        return 99

    print(f"Team workbook created: {result.public_workbook_path}")
    print(f"Internal workbook created: {result.internal_workbook_path}")
    print(f"Files processed: {result.total_files}")
    print(f"Successful invoices: {result.successful_invoices}")
    print(f"Failed invoices: {result.failed_invoices}")
    print(f"Line items extracted: {result.total_item_rows}")
    return 0 if result.successful_invoices else 1


if __name__ == "__main__":
    raise SystemExit(main())
