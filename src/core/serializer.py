"""
JSON Serializer - PR-Review Agent
Handles datetime, Path, custom objects
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any


class SerializerError(Exception):
    pass


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        if isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        if isinstance(obj, Path):
            return {"__type__": "Path", "value": str(obj)}
        if hasattr(obj, "__dict__"):
            return {"__type__": obj.__class__.__name__, "value": obj.__dict__}
        return super().default(obj)


def _object_hook(dct):
    if "__type__" in dct:
        t, v = dct["__type__"], dct["value"]
        if t == "datetime": return datetime.fromisoformat(v)
        if t == "date": return date.fromisoformat(v)
        if t == "Path": return Path(v)
    return dct


def to_json(obj, ensure_ascii=False, indent=2):
    try:
        return json.dumps(obj, cls=CustomEncoder, ensure_ascii=ensure_ascii, indent=indent)
    except (TypeError, ValueError) as e:
        raise SerializerError(f"JSON serialize failed: {e}")


def from_json(json_str):
    try:
        return json.loads(json_str, object_hook=_object_hook)
    except (json.JSONDecodeError, ValueError) as e:
        raise SerializerError(f"JSON deserialize failed: {e}")


def save_json(filepath, obj, encoding="utf-8"):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_text(to_json(obj), encoding=encoding)


def load_json(filepath, encoding="utf-8"):
    if not Path(filepath).exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")
    return from_json(Path(filepath).read_text(encoding=encoding))


def to_jsonl(records):
    return "\n".join(json.dumps(r, cls=CustomEncoder, ensure_ascii=False) for r in records)


def from_jsonl(jsonl_str):
    return [json.loads(l, object_hook=_object_hook) for l in jsonl_str.strip().split("\n") if l.strip()]
