"""
Logger - PR-Review Agent
Task-level transcript.jsonl, multi-level logging
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

AGENT_ACTION = 25
logging.addLevelName(AGENT_ACTION, "AGENT_ACTION")


class TranscriptLogger:
    def __init__(self, task_id: str, output_dir: str = "./output/logs"):
        self._task_id = task_id
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._transcript_path = self._output_dir / f"{task_id}_transcript.jsonl"
        self._logger = logging.getLogger(f"pr_review.{task_id}")
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            self._setup_handlers()

    def _setup_handlers(self):
        fh = logging.FileHandler(self._output_dir / f"{self._task_id}.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-12s | %(name)s | %(message)s"))
        self._logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-12s | %(message)s", datefmt="%H:%M:%S"))
        self._logger.addHandler(ch)

    def _write_transcript(self, level, source, message, metadata=None):
        record = {"timestamp": datetime.now().isoformat(), "task_id": self._task_id,
                  "level": level, "source": source, "message": message, "metadata": metadata or {}}
        try:
            with open(self._transcript_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            self._logger.error(f"Transcript write failed: {e}")

    def info(self, source, message, metadata=None):
        self._logger.info(f"[{source}] {message}")
        self._write_transcript("INFO", source, message, metadata)

    def warning(self, source, message, metadata=None):
        self._logger.warning(f"[{source}] {message}")
        self._write_transcript("WARNING", source, message, metadata)

    def error(self, source, message, metadata=None):
        self._logger.error(f"[{source}] {message}")
        self._write_transcript("ERROR", source, message, metadata)

    def agent_action(self, source, action, metadata=None):
        self._logger.log(AGENT_ACTION, f"[{source}] {action}")
        self._write_transcript("AGENT_ACTION", source, action, metadata)

    def debug(self, source, message, metadata=None):
        self._logger.debug(f"[{source}] {message}")
        self._write_transcript("DEBUG", source, message, metadata)

    @property
    def task_id(self): return self._task_id
    @property
    def transcript_path(self): return self._transcript_path

    def get_transcript(self):
        if not self._transcript_path.exists(): return []
        records = []
        with open(self._transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try: records.append(json.loads(line))
                    except json.JSONDecodeError: continue
        return records


_loggers: Dict[str, TranscriptLogger] = {}

def get_logger(task_id, output_dir="./output/logs"):
    if task_id not in _loggers:
        _loggers[task_id] = TranscriptLogger(task_id, output_dir)
    return _loggers[task_id]

def clear_loggers():
    _loggers.clear()
