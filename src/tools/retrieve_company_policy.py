"""
Retrieve Company Policy Tool - PR-Review Agent
Retrieves relevant company policy sections from the knowledge base
based on code context (keywords, file paths, risk areas).
"""

import os
import re
from pathlib import Path
from typing import Any

from agentscope.tool._base import ToolBase
from agentscope.tool._response import ToolChunk, ToolResultState
from agentscope.message._block import TextBlock
from agentscope.permission._decision import PermissionDecision
from agentscope.permission._types import PermissionBehavior
from agentscope.permission._context import PermissionContext


# Default knowledge base path
_DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "knowledge_base"

# Map risk areas / keywords to knowledge base files and sections
_POLICY_INDEX = {
    # SQL injection
    "sql_injection":       {"file": "security.md", "section": "SQL Injection Prevention"},
    "parameterized":       {"file": "security.md", "section": "SQL Injection Prevention"},
    "sql":                 {"file": "security.md", "section": "SQL Injection Prevention"},
    # Webhook
    "webhook":             {"file": "payment.md",  "section": "Payment Flow Integrity"},
    "webhook_signing":     {"file": "payment.md",  "section": "Payment Flow Integrity"},
    "signature":           {"file": "payment.md",  "section": "Payment Flow Integrity"},
    # Sensitive logging
    "sensitive_logging":   {"file": "security.md", "section": "Sensitive Data Handling"},
    "logging":             {"file": "security.md", "section": "Sensitive Data Handling"},
    "log":                 {"file": "security.md", "section": "Sensitive Data Handling"},
    "sensitive":           {"file": "security.md", "section": "Sensitive Data Handling"},
    # Payment fail-closed
    "payment":             {"file": "payment.md",  "section": "Error Handling"},
    "payment_fail_closed": {"file": "payment.md",  "section": "Error Handling"},
    "fail_closed":         {"file": "payment.md",  "section": "Error Handling"},
    "refund":              {"file": "payment.md",  "section": "Refund Safety"},
    "transaction":         {"file": "payment.md",  "section": "Transaction Safety"},
    # Idempotency
    "idempotency":         {"file": "payment.md",  "section": "Double Payment Prevention"},
    "idempotent":          {"file": "payment.md",  "section": "Double Payment Prevention"},
    # Testing
    "missing_tests":       {"file": "testing.md",  "section": "Test Coverage Requirements"},
    "test_coverage":       {"file": "testing.md",  "section": "Test Coverage Requirements"},
    "test_isolation":      {"file": "testing.md",  "section": "Test Isolation"},
    # Auth
    "authentication":      {"file": "security.md", "section": "Authentication & Authorization"},
    "auth":                {"file": "security.md", "section": "Authentication & Authorization"},
    "csrf":                {"file": "security.md", "section": "CSRF Protection"},
    # Secrets
    "secret":              {"file": "security.md", "section": "Secret Management"},
    "hardcoded":           {"file": "security.md", "section": "Secret Management"},
    # Input validation
    "input_validation":    {"file": "security.md", "section": "Input Validation"},
    "xss":                 {"file": "security.md", "section": "XSS Prevention"},
    # PCI
    "pci":                 {"file": "payment.md",  "section": "PCI DSS Compliance"},
    "credit_card":         {"file": "payment.md",  "section": "PCI DSS Compliance"},
    "card_number":         {"file": "payment.md",  "section": "PCI DSS Compliance"},
    # Audit
    "audit":               {"file": "payment.md",  "section": "Audit Trail"},
}


class RetrieveCompanyPolicyTool(ToolBase):
    """Retrieve relevant company policy sections from the knowledge base."""

    name: str = "retrieve_company_policy"
    description: str = (
        "Retrieve relevant company policy sections based on keywords or risk areas. "
        "Returns policy text from knowledge base files (security.md, payment.md, testing.md). "
        "Use this to check what the company requires before flagging a violation."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords or risk areas to look up. "
                               "Examples: ['sql_injection', 'webhook', 'payment', 'sensitive_logging', 'test_coverage']",
            },
        },
        "required": ["keywords"],
    }
    is_read_only: bool = True
    is_concurrency_safe: bool = True

    def __init__(self, knowledge_base_path: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.kb_path = Path(knowledge_base_path) if knowledge_base_path else _DEFAULT_KB_PATH

    async def check_permissions(
        self, tool_input: dict[str, Any], context: PermissionContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Read-only policy retrieval allowed",
        )

    async def call(self, keywords: list[str], **kwargs) -> ToolChunk:
        if not keywords:
            return ToolChunk(
                content=[TextBlock(text="请提供至少一个关键词来检索公司策略。")],
                state=ToolResultState.ERROR,
            )

        # Collect unique (file, section) pairs to retrieve
        to_retrieve: dict[str, set[str]] = {}  # filename -> set of sections
        unresolved = []

        for kw in keywords:
            kw_lower = kw.lower().strip()
            match = _POLICY_INDEX.get(kw_lower)
            if match:
                fname = match["file"]
                section = match["section"]
                to_retrieve.setdefault(fname, set()).add(section)
            else:
                unresolved.append(kw)

        if not to_retrieve:
            # Fallback: try to find the keyword in all KB files
            return await self._keyword_search(keywords)

        # Read and extract sections
        results = []
        for fname, sections in to_retrieve.items():
            fpath = self.kb_path / fname
            if not fpath.exists():
                results.append(f"[{fname}] 文件不存在")
                continue
            content = fpath.read_text(encoding="utf-8")
            for section in sections:
                extracted = self._extract_section(content, section)
                if extracted:
                    results.append(f"## [{fname}] {section}\n{extracted}")
                else:
                    results.append(f"## [{fname}] {section}\n（未找到该章节）")

        text = "\n\n".join(results)
        if unresolved:
            text += f"\n\n（以下关键词未匹配到策略: {', '.join(unresolved)}）"

        return ToolChunk(content=[TextBlock(text=text)], state=ToolResultState.SUCCESS)

    async def _keyword_search(self, keywords: list[str]) -> ToolChunk:
        """Fallback: search KB files for keywords directly."""
        results = []
        for fpath in sorted(self.kb_path.glob("*.md")):
            try:
                content = fpath.read_text(encoding="utf-8")
            except OSError:
                continue
            for kw in keywords:
                if kw.lower() in content.lower():
                    # Find the section containing the keyword
                    for line in content.split("\n"):
                        if kw.lower() in line.lower():
                            results.append(f"[{fpath.name}] {line.strip()}")
                            break

        if results:
            text = f"关键词匹配结果:\n" + "\n".join(results[:20])
        else:
            text = f"未在知识库中找到与 {', '.join(keywords)} 相关的策略。"
        return ToolChunk(content=[TextBlock(text=text)], state=ToolResultState.SUCCESS)

    @staticmethod
    def _extract_section(content: str, section_title: str) -> str:
        """Extract a markdown section by title."""
        lines = content.split("\n")
        start_idx = None
        start_level = 0

        for i, line in enumerate(lines):
            if line.strip().lower().startswith("##") and section_title.lower() in line.lower():
                start_idx = i
                start_level = len(line) - len(line.lstrip("#"))
                break

        if start_idx is None:
            return ""

        # Collect lines until next section of same or higher level
        result_lines = []
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if line.strip().startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                if level <= start_level:
                    break
            result_lines.append(line)

        return "\n".join(result_lines).strip()