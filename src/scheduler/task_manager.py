"""
Task Manager - PR-Review Agent v2
Async task queue and lifecycle management.
Connects Web/CLI entry points with the flow engine.
v2: Flow internals handle EvidenceStore persistence and report generation;
task_manager only dispatches and runs Judge.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    task_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    mode: str = "debate"
    repo_path: str = ""
    base_commit: str = ""
    target_commit: str = ""
    pr_description: str = ""
    rag_enabled: bool = True
    max_rounds: int = 3
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    error_message: str = ""
    result_summary: str = ""
    findings_count: int = 0
    flow_mode: str = ""
    output_dir: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class WebTaskManager:

    def __init__(
        self,
        output_dir: str = "./output/tasks",
        max_concurrent: int = 3,
        store_file: str = "task_store.json",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.store_path = self.output_dir / store_file
        self._tasks: Dict[str, TaskInfo] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._load_store()

    def create_task(
        self,
        mode: str = "debate",
        repo_path: str = "",
        base_commit: str = "",
        target_commit: str = "",
        pr_description: str = "",
        rag_enabled: bool = True,
        max_rounds: int = 3,
    ) -> TaskInfo:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        task_output = self.output_dir / task_id
        task_output.mkdir(parents=True, exist_ok=True)

        info = TaskInfo(
            task_id=task_id,
            status=TaskStatus.PENDING,
            mode=mode,
            repo_path=repo_path,
            base_commit=base_commit,
            target_commit=target_commit,
            pr_description=pr_description,
            rag_enabled=rag_enabled,
            max_rounds=max_rounds,
            created_at=now,
            output_dir=str(task_output),
        )
        self._tasks[task_id] = info
        self._save_store()
        logger.info(f"Task created: {task_id} (mode={mode})")
        return info

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[TaskInfo]:
        tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return tasks

    def delete_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status == TaskStatus.RUNNING:
            return False
        del self._tasks[task_id]
        self._save_store()
        return True

    async def start_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return False
        async_task = asyncio.create_task(self._execute_task(task))
        self._running_tasks[task_id] = async_task
        return True

    async def _execute_task(self, task: TaskInfo) -> None:
        await self._semaphore.acquire()
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()
        self._save_store()

        try:
            task_id = task.task_id
            out = Path(task.output_dir)
            out.mkdir(parents=True, exist_ok=True)

            from src.core.config_loader import get_config
            config = get_config()

            diff = ""
            if task.repo_path:
                try:
                    from src.tools.git_ops_tool import GitOps
                    git_tool = GitOps(repo_path=task.repo_path)
                    diff = git_tool.get_diff(
                        base_commit=task.base_commit,
                        target_commit=task.target_commit,
                    )
                except Exception as e:
                    logger.warning(f"Git diff failed: {e}")
                    diff = f"[Error getting diff: {e}]"

            rag_context = ""
            if task.rag_enabled:
                try:
                    from src.rag.retriever import RAGRetriever
                    from src.models.embedding import create_embedding_model
                    embedding_cfg = config.get_model_config("embedding")
                    embedding_model = create_embedding_model(
                        api_url=embedding_cfg.get("api_url", ""),
                        api_key=embedding_cfg.get("api_key", ""),
                        model_name=embedding_cfg.get("model_name", "text-embedding-v4"),
                        dimensions=embedding_cfg.get("dimensions", 1024),
                        timeout=embedding_cfg.get("timeout", 30),
                        batch_size=embedding_cfg.get("batch_size", 10),
                    )
                    rag_cfg = config.get_rag_config()
                    retriever = RAGRetriever(
                        embedding_model=embedding_model,
                        knowledge_base_path=rag_cfg.get("knowledge_base_path", "./knowledge_base"),
                        chunk_size=rag_cfg.get("chunk_size", 512),
                        chunk_overlap=rag_cfg.get("chunk_overlap", 64),
                    )
                    rag_context = await retriever.get_context_string(diff[:3000])
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")

            from src.core.transcript_logger import TranscriptLogger as Transcript
            transcript = Transcript()

            # Create 3-tier models
            from src.models.mimo_wrapper import create_mimo_model
            strong_cfg = config.get_model_config("strong")
            strong_model = create_mimo_model(
                api_url=strong_cfg.get("api_url", ""),
                api_key=strong_cfg.get("api_key", ""),
                model_name=strong_cfg.get("model_name", "deepseek"),
            )

            light_cfg = config.get_model_config("light")
            if light_cfg:
                light_model = create_mimo_model(
                    api_url=light_cfg.get("api_url", strong_cfg.get("api_url", "")),
                    api_key=light_cfg.get("api_key", strong_cfg.get("api_key", "")),
                    model_name=light_cfg.get("model_name", strong_cfg.get("model_name", "mimo")),
                )
            else:
                light_model = strong_model

            medium_cfg = config.get_model_config("medium")
            if medium_cfg:
                medium_model = create_mimo_model(
                    api_url=medium_cfg.get("api_url", strong_cfg.get("api_url", "")),
                    api_key=medium_cfg.get("api_key", strong_cfg.get("api_key", "")),
                    model_name=medium_cfg.get("model_name", strong_cfg.get("model_name", "mimo")),
                )
            else:
                medium_model = strong_model

            from src.agents.agent_factory import AgentFactory
            factory = AgentFactory(
                strong_model=strong_model,
                medium_model=medium_model,
                light_model=light_model,
            )

            flow = self._create_flow(task.mode, factory, task.max_rounds)

            embedding_model_for_store = None
            if task.rag_enabled:
                try:
                    from src.models.embedding import create_embedding_model
                    embedding_cfg = config.get_model_config("embedding")
                    embedding_model_for_store = create_embedding_model(
                        api_url=embedding_cfg.get("api_url", ""),
                        api_key=embedding_cfg.get("api_key", ""),
                        model_name=embedding_cfg.get("model_name", "text-embedding-v4"),
                        dimensions=embedding_cfg.get("dimensions", 1024),
                        timeout=embedding_cfg.get("timeout", 30),
                        batch_size=embedding_cfg.get("batch_size", 10),
                    )
                except Exception:
                    pass

            result = await flow.run(
                diff=diff,
                pr_description=task.pr_description,
                config={
                    "rag_context": rag_context,
                    "task_id": task_id,
                    "scanner_roles": None,
                    "max_rounds": task.max_rounds,
                    "embedding_model": embedding_model_for_store,
                    "output_dir": str(out),
                },
            )

            if transcript and not transcript.empty:
                transcript.save_jsonl(str(out / f"{task_id}_transcript.jsonl"))

            # Run Judge
            from src.judge.judge_runner import JudgeRunner
            judge_runner = JudgeRunner(model=strong_model)

            evidence_store_path = getattr(result, "evidence_store_path", "")
            if evidence_store_path and Path(evidence_store_path).exists():
                from src.flows.evidence_store import EvidenceStore
                store = EvidenceStore.load_json(evidence_store_path)
                judge_input = self._build_judge_input_from_store(
                    store.to_dict(), diff, task.pr_description,
                )
            else:
                from src.report.findings import FindingsCollection
                from src.report.report_renderer import ReportRenderer
                collection = FindingsCollection.from_review_findings(result.findings)
                renderer = ReportRenderer()
                judge_input = renderer.render_judge_input(
                    collection, diff=diff, pr_description=task.pr_description,
                )

            judge_result = await judge_runner.run(judge_input)
            judge_runner.save_result(
                judge_result, task.output_dir, task_id,
                judge_input=judge_input,
            )

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            task.duration_seconds = result.duration_seconds
            task.result_summary = result.summary
            task.findings_count = len(result.findings)
            task.flow_mode = result.flow_mode
            self._save_store()
            logger.info(f"Task completed: {task_id} ({task.findings_count} findings)")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now().isoformat()
            if task.started_at:
                start = datetime.fromisoformat(task.started_at)
                task.duration_seconds = (datetime.now() - start).total_seconds()
            self._save_store()
            logger.error(f"Task failed: {task_id}: {e}")
        finally:
            self._semaphore.release()
            self._running_tasks.pop(task_id, None)

    @staticmethod
    def _create_flow(mode: str, factory, max_rounds: int = 3):
        from src.flows.simple_flow import SimpleFlow
        from src.flows.council_flow import CouncilFlow
        from src.flows.debate_flow import DebateFlow
        from src.flows.agentic_flow import AgenticFlow

        if mode == "simple":
            return SimpleFlow()
        elif mode == "council":
            return CouncilFlow(agent_factory=factory)
        elif mode == "debate":
            return DebateFlow(agent_factory=factory, max_rounds=max_rounds)
        elif mode == "agentic":
            return AgenticFlow(agent_factory=factory, max_rounds=max_rounds)
        else:
            raise ValueError(f"Unknown flow mode: {mode}")

    @staticmethod
    def _build_judge_input_from_store(
        evidence_store_dict: dict,
        diff: str,
        pr_description: str,
    ) -> dict:
        return {
            "diff_summary": diff[:2000] if diff else "",
            "pr_description": pr_description,
            "findings": {
                "findings": evidence_store_dict.get("findings", []),
                "total_count": evidence_store_dict.get("summary", {}).get("total_findings", 0),
                "severity_counts": evidence_store_dict.get("summary", {}).get("severity_counts", {}),
            },
            "policy_references": evidence_store_dict.get("policy_references", []),
            "challenges": evidence_store_dict.get("challenges", []),
            "decisions": evidence_store_dict.get("decisions", []),
            "report_content": "",
            "total_findings": evidence_store_dict.get("summary", {}).get("total_findings", 0),
            "severity_counts": evidence_store_dict.get("summary", {}).get("severity_counts", {}),
        }

    def _save_store(self) -> None:
        data = {tid: t.to_dict() for tid, t in self._tasks.items()}
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_store(self) -> None:
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            for tid, tdict in data.items():
                tdict["status"] = TaskStatus(tdict.get("status", "pending"))
                self._tasks[tid] = TaskInfo(**{k: v for k, v in tdict.items()
                                               if k in TaskInfo.__dataclass_fields__})
            logger.info(f"Loaded {len(self._tasks)} tasks from store")
        except Exception as e:
            logger.warning(f"Failed to load task store: {e}")

    def get_stats(self) -> dict:
        counts = {s.value: 0 for s in TaskStatus}
        for t in self._tasks.values():
            counts[t.status.value] += 1
        return {
            "total": len(self._tasks),
            "running": counts["running"],
            "pending": counts["pending"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "max_concurrent": self.max_concurrent,
        }
