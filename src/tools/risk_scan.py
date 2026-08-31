"""
Risk Scan Tool - PR-Review Agent
Proactive risk pattern scanner for company policy violations.
Scans code diff for specific risk patterns: SQL injection, webhook signing,
sensitive logging, payment fail-open, missing tests, etc.
"""

import os
import re
from typing import Any

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


# ---------------------------------------------------------------------------
# Risk pattern definitions — each maps to a company policy area
# ---------------------------------------------------------------------------
RISK_PATTERNS = {
    "sql_injection": {
        "label": "SQL 注入风险",
        "patterns": [
            (r'(?i)(SELECT|INSERT|UPDATE|DELETE).*\+\s*(request|params|input|user|data|body)',
             "SQL 字符串拼接 — 未使用参数化查询"),
            (r'(?i)f["\'].*\b(SELECT|INSERT|UPDATE|DELETE)\b.*\{',
             "f-string 构造 SQL — 存在注入风险"),
            (r'(?i)\.format\(.*\b(SELECT|INSERT|UPDATE|DELETE)\b',
             ".format() 构造 SQL — 存在注入风险"),
            (r'(?i)execute\s*\(\s*["\'].*%s',
             "使用 % 格式化执行 SQL — 应使用参数化查询"),
        ],
    },
    "webhook_signing": {
        "label": "Webhook 验签缺失",
        "patterns": [
            (r'(?i)def\s+\w*webhook\w*.*:(?!\s*[\s\S]*verify.*signature)',
             "Webhook 处理函数 — 需检查是否验证签名"),
            (r'(?i)webhook.*(?:payload|body|data)(?!.*(?:verify|validate|signature|hmac))',
             "接收 Webhook 数据 — 未见签名验证"),
            (r'(?i)(?:hmac|signature|sign)\s*=\s*(?:None|False|"")',
             "签名验证被禁用或跳过"),
            (r'(?i)skip.*(?:verify|validation|signature)',
             "跳过验证逻辑"),
        ],
    },
    "sensitive_logging": {
        "label": "敏感信息日志泄露",
        "patterns": [
            (r'(?i)(?:log|logger|logging)\.\w+\(.*(?:password|passwd|secret|token|api_key|credit_card|card_number|cvv)',
             "日志中包含敏感字段（密码/密钥/卡号）"),
            (r'(?i)print\(.*(?:password|passwd|secret|token|api_key)',
             "print 输出敏感字段"),
            (r'(?i)(?:log|logger)\.\w+\(.*(?:request\.body|request\.data|request\.json)',
             "日志记录完整请求体 — 可能含敏感数据"),
        ],
    },
    "payment_fail_closed": {
        "label": "支付流程未 fail-closed",
        "patterns": [
            (r'except.*:\s*\n\s*pass(?=.*(?:pay|payment|charge|refund))',
             "支付相关异常被静默吞掉 — 应 fail-closed"),
            (r'(?i)(?:payment|charge|refund|transfer).*except.*(?:continue|pass|return\s+None)',
             "支付失败后未抛出异常 — 应 fail-closed"),
            (r'(?i)(?:timeout|retry).*payment(?!\s*.*(?:raise|fail|error))',
             "支付超时未正确处理 — 应 fail-closed"),
            (r'(?i)payment.*(?:except|catch)\s*(?:Exception|:)\s*$',
             "支付异常捕获过宽 — 可能掩盖失败"),
        ],
    },
    "missing_tests": {
        "label": "关键路径缺少测试",
        "patterns": [
            (r'(?i)def\s+(?:pay|charge|refund|transfer|withdraw)\w*(?!\s*.*test)',
             "支付/资金操作函数 — 需确认有对应测试"),
            (r'(?i)def\s+(?:authenticate|login|register|verify_token)',
             "认证相关函数 — 需确认有对应测试"),
        ],
    },
    "idempotency": {
        "label": "幂等性缺失",
        "patterns": [
            (r'(?i)(?:payment|charge|refund|order).*(?!idempoten)(?:def\s+\w+|POST)',
             "支付/订单操作 — 需确认幂等性"),
        ],
    },
}


class RiskScanTool(ToolBase):
    """Proactive risk scanner for company policy violations."""

    name: str = "risk_scan"
    description: str = (
        "Scan code for company policy risk patterns including: "
        "SQL injection, webhook signing, sensitive logging, "
        "payment fail-closed, missing tests, idempotency issues. "
        "Returns structured risk findings with file, line, severity, and policy reference."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory to scan (default: current directory)",
                "default": ".",
            },
            "risk_categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific risk categories to scan (default: all). "
                               "Options: sql_injection, webhook_signing, sensitive_logging, "
                               "payment_fail_closed, missing_tests, idempotency",
                "default": [],
            },
            "file_pattern": {
                "type": "string",
                "description": "File extension filter, e.g. .py",
                "default": "",
            },
        },
        "required": [],
    }
    is_read_only: bool = True
    is_concurrency_safe: bool = True

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Read-only risk scan allowed",
        )

    async def call(
        self,
        directory: str = ".",
        risk_categories: list[str] | None = None,
        file_pattern: str = "",
        **kwargs,
    ) -> ToolChunk:
        dir_path = os.path.realpath(directory)
        if not os.path.isdir(dir_path):
            return ToolChunk(
                content=[TextBlock(text=f"Error: Directory not found: {directory}")],
                state=ToolResultState.ERROR,
            )

        categories = risk_categories or list(RISK_PATTERNS.keys())
        findings = []
        finding_id = 0

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       {"__pycache__", "node_modules", ".git", "venv", ".venv"}]
            for fname in files:
                if file_pattern and not fname.endswith(file_pattern):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        lines = content.split("\n")
                except (OSError, UnicodeDecodeError):
                    continue

                rel_path = os.path.relpath(fpath, dir_path)

                for cat_key in categories:
                    cat_def = RISK_PATTERNS.get(cat_key)
                    if not cat_def:
                        continue
                    for pattern_str, description in cat_def["patterns"]:
                        try:
                            pattern = re.compile(pattern_str, re.MULTILINE)
                        except re.error:
                            continue
                        for match in pattern.finditer(content):
                            lineno = content[:match.start()].count("\n") + 1
                            # Get the matching line (not the entire match which may span lines)
                            matched_line = lines[lineno - 1].strip() if lineno <= len(lines) else match.group()[:200]
                            finding_id += 1
                            findings.append({
                                "id": f"POL-{finding_id:03d}",
                                "category": "company_policy",
                                "risk_area": cat_key,
                                "severity": _severity_for(cat_key),
                                "title": f"{cat_def['label']}: {description}",
                                "file_path": rel_path,
                                "line": lineno,
                                "evidence": matched_line[:300],
                                "policy_label": cat_def["label"],
                            })

        # Deduplicate by (file_path, line, risk_area)
        seen = set()
        unique = []
        for f in findings:
            key = (f["file_path"], f["line"], f["risk_area"])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        if not unique:
            text = "未发现公司策略违规风险。"
        else:
            summary = {}
            for f in unique:
                summary[f["policy_label"]] = summary.get(f["policy_label"], 0) + 1
            summary_text = "、".join(f"{k}: {v}" for k, v in summary.items())
            text = f"发现 {len(unique)} 个公司策略违规风险（{summary_text}）:\n"
            text += "\n".join(
                f"[{f['severity']}] {f['id']} {f['title']} @ {f['file_path']}:{f['line']}"
                for f in unique
            )

        return ToolChunk(content=[TextBlock(text=text)], state=ToolResultState.SUCCESS)


def _severity_for(cat_key: str) -> str:
    """Map risk category to severity level."""
    severity_map = {
        "sql_injection": "P0",
        "webhook_signing": "P1",
        "sensitive_logging": "P1",
        "payment_fail_closed": "P0",
        "missing_tests": "P2",
        "idempotency": "P1",
    }
    return severity_map.get(cat_key, "P2")