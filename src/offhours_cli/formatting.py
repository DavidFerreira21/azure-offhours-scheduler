from __future__ import annotations

import json
import sys
from typing import Any, Iterable

import yaml


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return str(value)


def render_mapping_table(data: dict[str, Any]) -> str:
    if not data:
        return ""

    keys = [str(key) for key in data.keys()]
    width = max(len(key) for key in keys)
    return "\n".join(f"{key.ljust(width)} : {_stringify(data[key])}" for key in keys)


def render_rows_table(rows: Iterable[dict[str, Any]], columns: list[str] | None = None) -> str:
    rows_list = list(rows)
    if not rows_list:
        return "(empty)"

    ordered_columns = columns or list(rows_list[0].keys())
    widths = {column: len(column) for column in ordered_columns}
    rendered_rows: list[dict[str, str]] = []

    for row in rows_list:
        rendered_row: dict[str, str] = {}
        for column in ordered_columns:
            value = _stringify(row.get(column, ""))
            rendered_row[column] = value
            widths[column] = max(widths[column], len(value))
        rendered_rows.append(rendered_row)

    header = "  ".join(column.ljust(widths[column]) for column in ordered_columns)
    separator = "  ".join("-" * widths[column] for column in ordered_columns)
    body = [
        "  ".join(rendered_row[column].ljust(widths[column]) for column in ordered_columns)
        for rendered_row in rendered_rows
    ]
    return "\n".join([header, separator, *body])


def emit_output(
    data: Any,
    *,
    output_format: str,
    stream=None,
    table_columns: list[str] | None = None,
) -> None:
    target_stream = stream or sys.stdout

    if output_format == "json":
        target_stream.write(json.dumps(data, indent=2, ensure_ascii=True))
        target_stream.write("\n")
        return

    if output_format == "yaml":
        target_stream.write(yaml.safe_dump(data, sort_keys=False, allow_unicode=False))
        return

    if isinstance(data, dict):
        target_stream.write(render_mapping_table(data))
        target_stream.write("\n")
        return

    if isinstance(data, list):
        target_stream.write(render_rows_table(data, columns=table_columns))
        target_stream.write("\n")
        return

    target_stream.write(f"{_stringify(data)}\n")
