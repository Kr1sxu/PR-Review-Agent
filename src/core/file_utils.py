"""
File Utilities - PR-Review Agent
Safe file read/write with path validation
"""

import os
from pathlib import Path
from typing import Optional


class FileUtilsError(Exception):
    pass

class PathViolationError(FileUtilsError):
    pass


class FileUtils:
    def __init__(self, allowed_roots: Optional[list] = None):
        self._allowed_roots = [Path(r).resolve() for r in allowed_roots] if allowed_roots else []

    def _validate_path(self, filepath: str) -> Path:
        resolved = Path(filepath).resolve()
        if self._allowed_roots:
            is_allowed = any(str(resolved).startswith(str(r)) for r in self._allowed_roots)
            if not is_allowed:
                raise PathViolationError(f"Path outside allowed dirs: {filepath}")
        return resolved

    def read_file(self, filepath: str, encoding: str = "utf-8") -> str:
        path = self._validate_path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        return path.read_text(encoding=encoding)

    def file_exists(self, filepath: str) -> bool:
        try:
            return self._validate_path(filepath).exists()
        except PathViolationError:
            return False

    def list_dir(self, dirpath: str, pattern: str = "*") -> list:
        path = self._validate_path(dirpath)
        if not path.is_dir():
            raise FileUtilsError(f"Not a directory: {dirpath}")
        return sorted([str(p) for p in path.glob(pattern)])

    def write_file(self, filepath: str, content: str, encoding: str = "utf-8"):
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)

    def write_json(self, filepath: str, data, encoding: str = "utf-8"):
        import json
        self.write_file(filepath, json.dumps(data, ensure_ascii=False, indent=2), encoding)
