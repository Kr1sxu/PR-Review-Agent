"""
Score API Routes - PR-Review Agent
POST /api/tasks/{id}/judge - trigger AI scoring
GET  /api/tasks/{id}/judge - get scoring result
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

from src.web.routes_task import get_manager

router = APIRouter(tags=["scoring"])


@router.post("/tasks/{task_id}/judge")
async def trigger_judge(task_id: str):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.output_dir:
        raise HTTPException(status_code=400, detail="Task has no output directory")

    findings_path = Path(task.output_dir) / "findings.json"
    report_path = Path(task.output_dir) / "report.md"
    if not findings_path.exists():
        raise HTTPException(status_code=400, detail="No findings to judge yet")

    from src.models.mimo_wrapper import create_mimo_model
    from src.core.config_loader import get_config
    from src.judge.judge_runner import JudgeRunner
    from src.report.report_renderer import ReportRenderer
    from src.report.findings import FindingsCollection

    config = get_config()
    mimo_cfg = config.get_model_config("mimo")
    model = create_mimo_model(
        api_url=mimo_cfg.get("api_url", ""),
        api_key=mimo_cfg.get("api_key", ""),
    )

    collection = FindingsCollection.load_json(str(findings_path))
    renderer = ReportRenderer()
    report_content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    judge_input = renderer.render_judge_input(
        collection, report_content=report_content,
    )

    runner = JudgeRunner(model=model)
    result = await runner.run(judge_input)
    paths = runner.save_result(result, task.output_dir, task_id)

    return {"status": "completed", "scores": result.scores.to_dict(), "paths": paths}


@router.get("/tasks/{task_id}/judge")
async def get_judge_result(task_id: str):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    judge_path = Path(task.output_dir) / f"{task_id}_judge.json"
    if not judge_path.exists():
        # Try without prefix
        judge_path = Path(task.output_dir) / "judge.json"
    if not judge_path.exists():
        raise HTTPException(status_code=404, detail="Judge result not found")

    return json.loads(judge_path.read_text(encoding="utf-8"))
