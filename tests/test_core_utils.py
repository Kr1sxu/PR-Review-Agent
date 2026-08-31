import json, pytest
from datetime import datetime
from pathlib import Path
from src.core.file_utils import FileUtils, PathViolationError
from src.core.serializer import to_json, from_json, save_json, load_json, to_jsonl, from_jsonl

class TestFileUtils:
    def test_read(self, tmp_path):
        (tmp_path / "t.txt").write_text("hello", encoding="utf-8")
        assert FileUtils([str(tmp_path)]).read_file(str(tmp_path / "t.txt")) == "hello"

    def test_path_violation(self, tmp_path):
        with pytest.raises(PathViolationError):
            FileUtils([str(tmp_path)]).read_file(str(tmp_path.parent / "secret.txt"))

    def test_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FileUtils([str(tmp_path)]).read_file(str(tmp_path / "nope.txt"))

    def test_exists(self, tmp_path):
        (tmp_path / "e.txt").write_text("x", encoding="utf-8")
        u = FileUtils([str(tmp_path)])
        assert u.file_exists(str(tmp_path / "e.txt")) and not u.file_exists(str(tmp_path / "no.txt"))

    def test_no_restriction(self, tmp_path):
        (tmp_path / "o.txt").write_text("open", encoding="utf-8")
        assert FileUtils().read_file(str(tmp_path / "o.txt")) == "open"

class TestSerializer:
    def test_datetime_roundtrip(self):
        dt = datetime(2026, 7, 23, 14, 30)
        assert from_json(to_json(dt)) == dt

    def test_path_roundtrip(self):
        p = Path("/a/b/c")
        assert str(from_json(to_json(p))) == str(p)

    def test_jsonl_roundtrip(self):
        records = [{"id": 1, "msg": "one"}, {"id": 2, "msg": "two"}]
        assert from_jsonl(to_jsonl(records)) == records

    def test_save_load(self, tmp_path):
        fp = str(tmp_path / "test.json")
        save_json(fp, {"key": "value"})
        assert load_json(fp) == {"key": "value"}

    def test_load_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json(str(tmp_path / "no.json"))
