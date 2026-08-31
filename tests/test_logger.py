import json, pytest
from src.core.logger import TranscriptLogger, get_logger, clear_loggers

@pytest.fixture(autouse=True)
def clean():
    clear_loggers(); yield; clear_loggers()

class TestTranscriptLogger:
    def test_info(self, tmp_path):
        l = TranscriptLogger("t1", str(tmp_path))
        l.info("src", "hello")
        assert len(l.get_transcript()) == 1
        assert l.get_transcript()[0]["level"] == "INFO"

    def test_warning(self, tmp_path):
        l = TranscriptLogger("t2", str(tmp_path))
        l.warning("src", "warn", {"k": "v"})
        assert l.get_transcript()[0]["metadata"]["k"] == "v"

    def test_agent_action(self, tmp_path):
        l = TranscriptLogger("t3", str(tmp_path))
        l.agent_action("scanner", "search")
        assert l.get_transcript()[0]["level"] == "AGENT_ACTION"

    def test_isolation(self, tmp_path):
        a = TranscriptLogger("a", str(tmp_path))
        b = TranscriptLogger("b", str(tmp_path))
        a.info("s", "from a"); b.info("s", "from b")
        assert len(a.get_transcript()) == 1 and a.get_transcript()[0]["task_id"] == "a"

    def test_empty_transcript(self, tmp_path):
        assert TranscriptLogger("empty", str(tmp_path)).get_transcript() == []

    def test_singleton(self, tmp_path):
        assert get_logger("s1", str(tmp_path)) is get_logger("s1", str(tmp_path))

    def test_jsonl_format(self, tmp_path):
        l = TranscriptLogger("jl", str(tmp_path))
        l.info("s", "test")
        with open(l.transcript_path, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
            assert all(k in data for k in ["timestamp", "task_id", "level", "source", "message", "metadata"])
