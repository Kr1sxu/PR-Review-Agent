"""
Evidence Store - PR-Review Agent v2
共享证据仓库：Findings + 政策引用 + 质疑记录 + 裁决记录 + 辩论历史
基于 PostgreSQL 持久化，支持跨任务长期记忆检索。

所有审查角色通过 EvidenceStore 读写数据。
内存中保留完整数据结构用于流程逻辑，同时异步写入 PostgreSQL。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.flows.base_flow import Finding, finding_to_dict

logger = logging.getLogger(__name__)


# ============================================================
# 数据类定义（与原版保持一致）
# ============================================================

@dataclass
class PolicyReference:
    """公司规范引用条目"""
    policy_id: str = ""
    policy_area: str = ""
    policy_label: str = ""
    rule_text: str = ""
    matched_finding_ids: list = field(default_factory=list)
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class Challenge:
    """Critic 质疑记录"""
    challenge_id: str = ""
    finding_id: str = ""
    challenger: str = ""
    action: str = ""
    reason: str = ""
    new_severity: str = ""
    merge_target_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class Decision:
    """Lead Controller 裁决记录"""
    decision_id: str = ""
    finding_id: str = ""
    action: str = ""
    reason: str = ""
    new_severity: str = ""
    merge_target_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class DebateRound:
    """多轮辩论历史记录"""
    round_number: int = 0
    lead_action: str = ""
    target_finding_id: str = ""
    actor: str = ""
    result_summary: str = ""
    consensus_score: float = 0.0
    findings_count: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


# ============================================================
# EvidenceStore 核心类
# ============================================================

class EvidenceStore:
    """
    共享证据仓库 - 所有审查角色的数据中枢。

    内存中维护完整数据结构（用于流程逻辑和 to_dict），
    异步持久化到 PostgreSQL（用于长期记忆和事后复盘）。
    """

    def __init__(self, task_id: str = ""):
        self.task_id = task_id
        self.findings: List[Finding] = []
        self.policy_references: List[PolicyReference] = []
        self.challenges: List[Challenge] = []
        self.decisions: List[Decision] = []
        self.debate_history: List[DebateRound] = []
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = ""
        self._challenge_counter: int = 0
        self._decision_counter: int = 0
        self._persist_enabled: bool = True  # 是否启用 PostgreSQL 持久化

    # ==================================================================
    # 数据写入（内存 + 异步持久化）
    # ==================================================================

    async def add_findings(self, findings: List[Finding]) -> None:
        """添加 findings 并异步写入数据库"""
        self.findings.extend(findings)
        self.updated_at = datetime.now().isoformat()
        if self._persist_enabled and self.task_id:
            await self._persist_findings(findings)

    async def add_policy_references(self, refs: List[PolicyReference]) -> None:
        self.policy_references.extend(refs)
        self.updated_at = datetime.now().isoformat()
        if self._persist_enabled and self.task_id:
            await self._persist_policy_references(refs)

    async def add_challenge(self, challenge: Challenge) -> None:
        self._challenge_counter += 1
        if not challenge.challenge_id:
            challenge.challenge_id = f"C{self._challenge_counter:03d}"
        if not challenge.timestamp:
            challenge.timestamp = datetime.now().isoformat()
        self.challenges.append(challenge)
        self.updated_at = datetime.now().isoformat()
        if self._persist_enabled and self.task_id:
            await self._persist_challenge(challenge)

    async def add_decision(self, decision: Decision) -> None:
        self._decision_counter += 1
        if not decision.decision_id:
            decision.decision_id = f"D{self._decision_counter:03d}"
        if not decision.timestamp:
            decision.timestamp = datetime.now().isoformat()
        self.decisions.append(decision)
        self.updated_at = datetime.now().isoformat()
        if self._persist_enabled and self.task_id:
            await self._persist_decision(decision)

    async def add_debate_round(self, round_record: DebateRound) -> None:
        if not round_record.timestamp:
            round_record.timestamp = datetime.now().isoformat()
        self.debate_history.append(round_record)
        self.updated_at = datetime.now().isoformat()
        if self._persist_enabled and self.task_id:
            await self._persist_debate_round(round_record)

    # ==================================================================
    # 数据查询
    # ==================================================================

    @property
    def latest_consensus_score(self) -> float:
        if self.debate_history:
            return self.debate_history[-1].consensus_score
        return 0.0

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def is_empty(self) -> bool:
        return len(self.findings) == 0

    def get_active_findings(self) -> List[Finding]:
        """获取未被 REJECT 的 findings"""
        rejected_ids = set()
        for d in self.decisions:
            if d.action == "REJECT":
                rejected_ids.add(d.finding_id)
        return [f for f in self.findings if f.id not in rejected_ids]
    def get_finding(self, finding_id: str) -> Optional[Finding]:
        """根据 ID 获取单个 finding"""
        for f in self.findings:
            if f.id == finding_id:
                return f
        return None

    async def merge_findings(self, source_id: str, target_id: str) -> bool:
        """合并 source finding 到 target finding"""
        source = self.get_finding(source_id)
        target = self.get_finding(target_id)
        if not source or not target:
            return False
        # 合并证据
        if source.evidence:
            target.evidence = (target.evidence + "\n---\n" + source.evidence).strip()
        # 合并来源
        if source.sources:
            existing = set(target.sources or [])
            existing.update(source.sources)
            target.sources = list(existing)
        # 取更高严重度
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        s_sev = severity_order.get(source.severity, 0)
        t_sev = severity_order.get(target.severity, 0)
        if s_sev > t_sev:
            target.severity = source.severity
        # 移除 source
        self.findings = [f for f in self.findings if f.id != source_id]
        self.updated_at = datetime.now().isoformat()
        return True

    async def remove_finding(self, finding_id: str) -> bool:
        """移除指定 finding"""
        before = len(self.findings)
        self.findings = [f for f in self.findings if f.id != finding_id]
        if len(self.findings) < before:
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def update_severity(self, finding_id: str, new_severity: str) -> bool:
        """更新 finding 的严重度"""
        f = self.get_finding(finding_id)
        if f:
            f.severity = new_severity
            self.updated_at = datetime.now().isoformat()
            return True
        return False


    def to_dict(self) -> dict:
        """序列化为字典（供 report_writer / judge 使用）"""
        return {
            "task_id": self.task_id,
            "findings": [finding_to_dict(f) for f in self.findings],
            "policy_references": [r.to_dict() for r in self.policy_references],
            "challenges": [c.to_dict() for c in self.challenges],
            "decisions": [d.to_dict() for d in self.decisions],
            "debate_history": [r.to_dict() for r in self.debate_history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "summary": {
                "findings_count": len(self.findings),
                "policy_refs_count": len(self.policy_references),
                "challenges_count": len(self.challenges),
                "decisions_count": len(self.decisions),
                "debate_rounds": len(self.debate_history),
            },
        }

    # ==================================================================
    # PostgreSQL 持久化（异步写入）
    # ==================================================================

    async def _get_conn(self):
        from src.core.database import get_pool
        return get_pool()

    async def _persist_findings(self, findings: List[Finding]) -> None:
        try:
            pool = await self._get_conn()
            records = []
            for f in findings:
                records.append((
                    self.task_id,
                    f.id,
                    f.category,
                    f.severity,
                    f.title,
                    f.description,
                    f.file_path,
                    f.line_range,
                    f.evidence,
                    f.suggestion,
                    f.confidence,
                    f.spec_reference,
                    json.dumps(f.sources, ensure_ascii=False),
                ))
            await pool.executemany(
                """INSERT INTO findings
                   (task_id, finding_id, category, severity, title, description,
                    file_path, line_range, evidence, suggestion, confidence,
                    spec_reference, sources)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
                records,
            )
        except Exception as e:
            logger.warning(f"Failed to persist findings to PostgreSQL: {e}")

    async def _persist_policy_references(self, refs: List[PolicyReference]) -> None:
        try:
            pool = await self._get_conn()
            records = []
            for r in refs:
                records.append((
                    self.task_id,
                    r.policy_id,
                    r.policy_area,
                    r.policy_label,
                    r.rule_text,
                    json.dumps(r.matched_finding_ids, ensure_ascii=False),
                    r.source,
                ))
            await pool.executemany(
                """INSERT INTO policy_references
                   (task_id, policy_id, policy_area, policy_label, rule_text,
                    matched_finding_ids, source)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                records,
            )
        except Exception as e:
            logger.warning(f"Failed to persist policy_references: {e}")

    async def _persist_challenge(self, c: Challenge) -> None:
        try:
            pool = await self._get_conn()
            await pool.execute(
                """INSERT INTO challenges
                   (task_id, challenge_id, finding_id, challenger, action,
                    reason, new_severity, merge_target_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                self.task_id, c.challenge_id, c.finding_id, c.challenger,
                c.action, c.reason, c.new_severity, c.merge_target_id,
            )
        except Exception as e:
            logger.warning(f"Failed to persist challenge: {e}")

    async def _persist_decision(self, d: Decision) -> None:
        try:
            pool = await self._get_conn()
            await pool.execute(
                """INSERT INTO decisions
                   (task_id, decision_id, finding_id, action, reason,
                    new_severity, merge_target_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                self.task_id, d.decision_id, d.finding_id,
                d.action, d.reason, d.new_severity, d.merge_target_id,
            )
        except Exception as e:
            logger.warning(f"Failed to persist decision: {e}")

    async def _persist_debate_round(self, r: DebateRound) -> None:
        try:
            pool = await self._get_conn()
            await pool.execute(
                """INSERT INTO debate_history
                   (task_id, round_number, lead_action, target_finding_id,
                    actor, result_summary, consensus_score, findings_count)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                self.task_id, r.round_number, r.lead_action,
                r.target_finding_id, r.actor, r.result_summary,
                r.consensus_score, r.findings_count,
            )
        except Exception as e:
            logger.warning(f"Failed to persist debate_round: {e}")

    # ==================================================================
    # 审查摘要持久化（用于长期记忆检索）
    # ==================================================================

    async def persist_review_summary(self, embedding: List[float] = None) -> None:
        """将本次审查摘要写入 review_history + review_vectors"""
        if not self.task_id:
            return
        try:
            from src.core.database import get_conn
            severity_dist = {}
            for f in self.findings:
                severity_dist[f.severity] = severity_dist.get(f.severity, 0) + 1

            async with get_conn() as conn:
                await conn.execute(
                    """INSERT INTO review_history
                       (task_id, findings_count, severity_dist, created_at)
                       VALUES ($1, $2, $3::jsonb, NOW())
                       ON CONFLICT (task_id) DO UPDATE
                       SET findings_count = EXCLUDED.findings_count,
                           severity_dist = EXCLUDED.severity_dist""",
                    self.task_id,
                    len(self.findings),
                    json.dumps(severity_dist, ensure_ascii=False),
                )

                if embedding:
                    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                    summary = self._build_summary_text()
                    await conn.execute(
                        """INSERT INTO review_vectors (task_id, summary_text, embedding)
                           VALUES ($1, $2, $3::vector)""",
                        self.task_id, summary, vec_str,
                    )
        except Exception as e:
            logger.warning(f"Failed to persist review summary: {e}")

    def _build_summary_text(self) -> str:
        """构建审查摘要文本（用于向量化）"""
        parts = [f"Task: {self.task_id}"]
        parts.append(f"Findings: {len(self.findings)}")
        for f in self.findings[:10]:
            parts.append(f"[{f.severity}] {f.category}: {f.title}")
        for d in self.decisions:
            parts.append(f"Decision: {d.action} on {d.finding_id}")
        return "\n".join(parts)

    # ==================================================================
    # JSON 持久化（兼容原有接口，同时写入 PostgreSQL）
    # ==================================================================

    def save_json(self, path: str) -> None:
        """保存到 JSON 文件（兼容原有流程，同时触发 PostgreSQL 持久化）"""
        import asyncio
        from pathlib import Path

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"EvidenceStore saved to {path}")

        # 异步写入 PostgreSQL 审查摘要
        if self._persist_enabled and self.task_id:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.persist_review_summary())
                else:
                    loop.run_until_complete(self.persist_review_summary())
            except Exception:
                pass

    @classmethod
    def load_json(cls, path: str) -> "EvidenceStore":
        """从 JSON 文件加载（兼容原有接口）"""
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls(task_id=data.get("task_id", ""))
        store.created_at = data.get("created_at", "")
        store.updated_at = data.get("updated_at", "")

        for item in data.get("findings", []):
            store.findings.append(Finding(
                id=item.get("id", ""),
                category=item.get("category", ""),
                severity=item.get("severity", "medium"),
                title=item.get("title", ""),
                description=item.get("description", ""),
                file_path=item.get("file_path", ""),
                line_range=item.get("line_range", ""),
                evidence=item.get("evidence", ""),
                suggestion=item.get("suggestion", ""),
                confidence=item.get("confidence", 0.5),
                spec_reference=item.get("spec_reference", ""),
                sources=item.get("sources", []),
                metadata=item.get("metadata", {}),
            ))

        for item in data.get("policy_references", []):
            store.policy_references.append(PolicyReference(
                policy_id=item.get("policy_id", ""),
                policy_area=item.get("policy_area", ""),
                policy_label=item.get("policy_label", ""),
                rule_text=item.get("rule_text", ""),
                matched_finding_ids=item.get("matched_finding_ids", []),
                source=item.get("source", ""),
                metadata=item.get("metadata", {}),
            ))

        for item in data.get("challenges", []):
            store.challenges.append(Challenge(
                challenge_id=item.get("challenge_id", ""),
                finding_id=item.get("finding_id", ""),
                challenger=item.get("challenger", ""),
                action=item.get("action", ""),
                reason=item.get("reason", ""),
                new_severity=item.get("new_severity", ""),
                merge_target_id=item.get("merge_target_id", ""),
                timestamp=item.get("timestamp", ""),
            ))

        for item in data.get("decisions", []):
            store.decisions.append(Decision(
                decision_id=item.get("decision_id", ""),
                finding_id=item.get("finding_id", ""),
                action=item.get("action", ""),
                reason=item.get("reason", ""),
                new_severity=item.get("new_severity", ""),
                merge_target_id=item.get("merge_target_id", ""),
                timestamp=item.get("timestamp", ""),
            ))

        for item in data.get("debate_history", []):
            store.debate_history.append(DebateRound(
                round_number=item.get("round_number", 0),
                lead_action=item.get("lead_action", ""),
                target_finding_id=item.get("target_finding_id", ""),
                actor=item.get("actor", ""),
                result_summary=item.get("result_summary", ""),
                consensus_score=item.get("consensus_score", 0.0),
                findings_count=item.get("findings_count", 0),
                timestamp=item.get("timestamp", ""),
            ))

        store._challenge_counter = len(store.challenges)
        store._decision_counter = len(store.decisions)
        logger.info(f"EvidenceStore loaded from {path}: {len(store.findings)} findings")
        return store

    # ==================================================================
    # 长期记忆查询（跨任务检索）
    # ==================================================================

    @staticmethod
    async def query_similar_reviews(
        embedding: List[float], top_k: int = 5
    ) -> List[dict]:
        """检索历史上最相似的审查记录"""
        from src.core.database import get_pool
        pool = get_pool()
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        rows = await pool.fetch(
            """SELECT rh.task_id, rh.findings_count, rh.severity_dist,
                      rh.created_at,
                      1 - (rv.embedding <=> $1::vector) AS similarity
               FROM review_vectors rv
               JOIN review_history rh ON rv.task_id = rh.task_id
               ORDER BY rv.embedding <=> $1::vector
               LIMIT $2""",
            vec_str,
            top_k,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def query_findings_by_category(
        category: str, limit: int = 20
    ) -> List[dict]:
        """查询某类别的历史 findings（用于模式发现）"""
        from src.core.database import get_pool
        pool = get_pool()
        rows = await pool.fetch(
            """SELECT task_id, finding_id, severity, title, description,
                      file_path, suggestion, created_at
               FROM findings
               WHERE category = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            category, limit,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def query_high_frequency_patterns(min_count: int = 3) -> List[dict]:
        """查询高频问题模式（category + severity 维度）"""
        from src.core.database import get_pool
        pool = get_pool()
        rows = await pool.fetch(
            """SELECT category, severity, COUNT(*) as freq,
                      ARRAY_AGG(DISTINCT file_path) as affected_files
               FROM findings
               GROUP BY category, severity
               HAVING COUNT(*) >= $1
               ORDER BY freq DESC""",
            min_count,
        )
        return [dict(r) for r in rows]

    def __repr__(self) -> str:
        return (
            f"EvidenceStore(task_id={self.task_id!r}, "
            f"findings={len(self.findings)}, "
            f"policies={len(self.policy_references)}, "
            f"challenges={len(self.challenges)}, "
            f"decisions={len(self.decisions)}, "
            f"debate_rounds={len(self.debate_history)})"
        )