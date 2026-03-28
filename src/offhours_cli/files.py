from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_mapping_file(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        payload = json.loads(text)
    else:
        documents = list(yaml.safe_load_all(text))
        if len(documents) != 1:
            raise ValueError("input files must contain exactly one YAML/JSON document")
        payload = documents[0]

    if not isinstance(payload, dict):
        raise ValueError("input payload must be a JSON/YAML object")
    return payload
