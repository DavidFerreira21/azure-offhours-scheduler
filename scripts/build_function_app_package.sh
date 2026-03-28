#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/function"
OUTPUT_PATH="${1:-/tmp/offhours-function-package.zip}"

mkdir -p "$(dirname "$OUTPUT_PATH")"

python3 - "$APP_DIR" "$OUTPUT_PATH" <<'PY'
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

app_dir = Path(sys.argv[1]).resolve()
output_path = Path(sys.argv[2]).resolve()

entries = [
    "host.json",
    "requirements.txt",
    "OffHoursTimer",
    ".python_packages",
    "config",
    "discovery",
    "handlers",
    "persistence",
    "reporting",
    "scheduler",
]

output_path.unlink(missing_ok=True)

with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for entry_name in entries:
        entry_path = app_dir / entry_name
        if not entry_path.exists():
            raise SystemExit(f"missing publish entry: {entry_path}")

        if entry_path.is_file():
            archive.write(entry_path, entry_name)
            continue

        for candidate in sorted(entry_path.rglob("*")):
            if not candidate.is_file():
                continue
            if "__pycache__" in candidate.parts:
                continue
            archive.write(candidate, candidate.relative_to(app_dir).as_posix())
PY

echo "$OUTPUT_PATH"
