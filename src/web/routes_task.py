"""
Task API Routes - PR-Review Agent
POST/GET/DELETE /api/tasks, restart, status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.scheduler.task_manager import WebTaskManager

router = APIRouter(tags=["tasks"])

# Global task manager instance
_manager: Optional[WebTaskManager] = None


def get_manager() -> WebTaskManager:
    global _manager
    if _manager is None:
        _manager = WebTaskManager()
    return _manager


class CreateTaskRequest(BaseModel):
    mode: str = "council"
    repo_path: str = ""
    base_commit: str = "HEAD~1"
    target_commit: str = "HEAD"
    pr_description: str = ""
    rag_enabled: bool = True
    max_rounds: int = 3


@router.post("/tasks")
async def create_task(req: CreateTaskRequest):
    manager = get_manager()
    task = manager.create_task(
        mode=req.mode, repo_path=req.repo_path,
        base_commit=req.base_commit, target_commit=req.target_commit,
        pr_description=req.pr_description, rag_enabled=req.rag_enabled,
        max_rounds=req.max_rounds,
    )
    # Auto-start the task
    await manager.start_task(task.task_id)
    return task.to_dict()


@router.get("/tasks")
async def list_tasks():
    manager = get_manager()
    tasks = manager.list_tasks()
    return {"tasks": [t.to_dict() for t in tasks], "stats": manager.get_stats()}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    manager = get_manager()
    if not manager.delete_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot delete task (not found or running)")
    return {"deleted": task_id}


@router.post("/tasks/{task_id}/restart")
async def restart_task(task_id: str):
    manager = get_manager()
    old = manager.get_task(task_id)
    if not old:
        raise HTTPException(status_code=404, detail="Task not found")
    # Create new task with same params
    new_task = manager.create_task(
        mode=old.mode, repo_path=old.repo_path,
        base_commit=old.base_commit, target_commit=old.target_commit,
        pr_description=old.pr_description, rag_enabled=old.rag_enabled,
        max_rounds=old.max_rounds,
    )
    await manager.start_task(new_task.task_id)
    return new_task.to_dict()
