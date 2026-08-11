"""JSON Schema validation helpers for versioned OpenRestore artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"


def schema_path(kind: str) -> Path:
    path = SCHEMA_ROOT / f"{kind}.schema.json"
    if not path.is_file():
        raise ValueError(f"Unknown schema kind: {kind}")
    return path


def read_documents(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in handle if line.strip()]
        document = json.load(handle)
    return document if isinstance(document, list) else [document]


def validate_file(kind: str, path: Path) -> int:
    with schema_path(kind).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for index, document in enumerate(read_documents(path), start=1):
        for error in validator.iter_errors(document):
            location = ".".join(str(item) for item in error.absolute_path) or "<root>"
            errors.append(f"document {index}, {location}: {error.message}")
    if errors:
        raise ValueError("\n".join(errors))
    return len(read_documents(path))
