"""
Task Manager Tests - PR-Review Agent
Test task creation, lifecycle, concurrency, persistence
"""

import asyncio
import json
import pytest
from pathlib import Path

from src.scheduler.task_manager import WebTaskManager, TaskInfo, TaskStatus


class TestTaskCreation:
    """Task creation tests"""

    def test_create_task(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path), max_concurrent=2)
        task = manager.create_task(mode="simple", repo_path="/repo")
        assert task.task_id != ""
        assert task.status == TaskStatus.PENDING
        assert task.mode == "simple"

    def test_create_multiple_tasks(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        t1 = manager.create_task(mode="simple")
        t2 = manager.create_task(mode="council")
        assert t1.task_id != t2.task_id
        assert manager.get_stats()["total"] == 2

    def test_task_output_dir_created(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        task = manager.create_task()
        assert Path(task.output_dir).exists()


class TestTaskLifecycle:
    """Task lifecycle and status tests"""

    def test_get_task(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        task = manager.create_task()
        retrieved = manager.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_get_nonexistent_task(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        assert manager.get_task("nonexistent") is None

    def test_list_tasks(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        manager.create_task(mode="simple")
        manager.create_task(mode="council")
        manager.create_task(mode="debate")
        tasks = manager.list_tasks()
        assert len(tasks) == 3

    def test_delete_pending_task(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        task = manager.create_task()
        assert manager.delete_task(task.task_id) is True
        assert manager.get_task(task.task_id) is None

    def test_delete_nonexistent_task(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        assert manager.delete_task("nonexistent") is False


class TestTaskPersistence:
    """Task store persistence tests"""

    def test_save_and_reload(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path), store_file="store.json")
        manager.create_task(mode="simple", repo_path="/repo")
        manager.create_task(mode="council")

        # Create new manager instance (simulates restart)
        manager2 = WebTaskManager(output_dir=str(tmp_path), store_file="store.json")
        assert manager2.get_stats()["total"] == 2
        tasks = manager2.list_tasks()
        modes = {t.mode for t in tasks}
        assert "simple" in modes
        assert "council" in modes

    def test_store_file_exists(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path), store_file="store.json")
        manager.create_task()
        assert (tmp_path / "store.json").exists()

    def test_store_is_valid_json(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path), store_file="store.json")
        manager.create_task(mode="debate")
        data = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
        assert len(data) == 1


class TestTaskStats:
    """Task statistics tests"""

    def test_stats_empty(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        stats = manager.get_stats()
        assert stats["total"] == 0
        assert stats["running"] == 0

    def test_stats_with_tasks(self, tmp_path):
        manager = WebTaskManager(output_dir=str(tmp_path))
        manager.create_task(mode="simple")
        manager.create_task(mode="council")
        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["pending"] == 2
        assert stats["max_concurrent"] == 3


class TestTaskInfo:
    """TaskInfo dataclass tests"""

    def test_to_dict(self):
        info = TaskInfo(task_id="abc", mode="debate", status=TaskStatus.PENDING)
        d = info.to_dict()
        assert d["task_id"] == "abc"
        assert d["status"] == "pending"

    def test_task_with_metadata(self):
        info = TaskInfo(
            task_id="xyz",
            status=TaskStatus.COMPLETED,
            findings_count=5,
            flow_mode="debate",
        )
        d = info.to_dict()
        assert d["findings_count"] == 5
        assert d["flow_mode"] == "debate"
