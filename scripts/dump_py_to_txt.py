from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "site-packages",
    "input_pdfs",
    "logs",
    "output",
}

DEFAULT_IGNORED_FILES = {
    ".DS_Store",
    ".env",
    "secrets.toml",
}

PROJECT_CONTEXT_EXTENSIONS = {
    ".md",
    ".toml",
    ".txt",
    ".ini",
    ".cfg",
    ".json",
    ".yaml",
    ".yml",
    ".env",
    ".sample",
}

PROJECT_CONTEXT_FILENAMES = {
    ".gitignore",
    ".python-version",
    "LICENSE",
    "LICENSE.txt",
    "Makefile",
    "Dockerfile",
}


def iter_project_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative_parts = path.relative_to(root).parts
        if any(part in DEFAULT_IGNORED_DIRS for part in relative_parts[:-1]):
            continue
        if path.name in DEFAULT_IGNORED_FILES:
            continue
        if path.suffix == ".pyc":
            continue
        if path.name.startswith("project_context_") and path.suffix == ".txt":
            continue
        if ".git" in relative_parts:
            continue

        yield path


def is_text_candidate(path: Path) -> bool:
    if path.suffix == ".py":
        return True
    if path.name in PROJECT_CONTEXT_FILENAMES:
        return True
    if path.suffix.lower() in PROJECT_CONTEXT_EXTENSIONS:
        return True
    return False


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_section(handle, title: str, rel_path: str, content: str) -> None:
    handle.write(f"\n{'=' * 100}\n")
    handle.write(f"{title}: {rel_path}\n")
    handle.write(f"{'=' * 100}\n")
    handle.write(content)
    if not content.endswith("\n"):
        handle.write("\n")


def build_tree(root: Path, files: list[Path]) -> str:
    lines = []
    for file_path in files:
        rel = file_path.relative_to(root)
        depth = len(rel.parts) - 1
        indent = "    " * depth
        lines.append(f"{indent}- {rel.as_posix()}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump project Python files and supporting context into one text file."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root to scan. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output text file path. Defaults to project_context_<timestamp>.txt in the repo root.",
    )
    args = parser.parse_args()

    root: Path = args.root.resolve()
    output_path = args.output
    if output_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = root / f"project_context_{stamp}.txt"
    else:
        output_path = output_path.resolve()

    files = [path for path in iter_project_files(root) if is_text_candidate(path)]
    py_files = [path for path in files if path.suffix == ".py"]
    context_files = [path for path in files if path.suffix != ".py"]

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(f"Project root: {root}\n")
        handle.write(f"Generated at: {datetime.now().isoformat(timespec='seconds')}\n")
        handle.write("\n")
        handle.write("Directory / file hierarchy:\n")
        handle.write(build_tree(root, files))
        handle.write("\n\n")

        handle.write("Python source files:\n")
        for path in py_files:
            rel = path.relative_to(root).as_posix()
            write_section(handle, "FILE", rel, read_text_file(path))

        if context_files:
            handle.write("\n\nSupporting project context:\n")
            for path in context_files:
                rel = path.relative_to(root).as_posix()
                write_section(handle, "FILE", rel, read_text_file(path))

    print(f"Wrote {output_path}")
    print(f"Included {len(py_files)} Python files and {len(context_files)} context files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
