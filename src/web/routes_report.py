"""
Report API Routes - PR-Review Agent
GET /api/tasks/{id}/report, findings, transcript
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from src.web.routes_task import get_manager

router = APIRouter(tags=["reports"])


def _get_task_output_dir(task_id: str) -> Path:
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return Path(task.output_dir)


@router.get("/tasks/{task_id}/report")
async def get_report(task_id: str):
    output_dir = _get_task_output_dir(task_id)
    report_path = output_dir / "report.md"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return PlainTextResponse(report_path.read_text(encoding="utf-8"))


@router.get("/tasks/{task_id}/findings")
async def get_findings(task_id: str):
    output_dir = _get_task_output_dir(task_id)
    findings_path = output_dir / "findings.json"
    if not findings_path.exists():
        raise HTTPException(status_code=404, detail="Findings not generated yet")
    return json.loads(findings_path.read_text(encoding="utf-8"))


@router.get("/tasks/{task_id}/transcript")
async def get_transcript(task_id: str, keyword: str = Query("", description="Search keyword")):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    log_path = Path(task.output_dir) / f"{task_id}_transcript.jsonl"
    if not log_path.exists():
        return {"lines": [], "total": 0}
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if keyword and keyword.lower() not in json.dumps(record, ensure_ascii=False).lower():
                continue
            records.append(record)
        except json.JSONDecodeError:
            continue
    return {"lines": records, "total": len(records)}
