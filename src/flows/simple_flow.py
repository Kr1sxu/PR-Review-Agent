"""
Simple Flow - PR-Review Agent
Rule-based static analysis, no model calls
Used for offline degradation and basic link validation
Performance target: 100-line diff <= 10 seconds
"""

import re
from typing import Dict, List

from src.flows.base_flow import BaseFlow, Finding, ReviewResult


# Rule-based detection patterns
SECURITY_PATTERNS = [
    (r'(?i)password\s*=\s*["\x27].+["\x27]', "hardcoded_password", "high",
     "检测到硬编码密码"),
    (r'(?i)api_key\s*=\s*["\x27].+["\x27]', "hardcoded_api_key", "high",
     "检测到硬编码API密钥"),
    (r'(?i)secret\s*=\s*["\x27].+["\x27]', "hardcoded_secret", "high",
     "检测到硬编码密钥"),
    (r'(?i)(SELECT|INSERT|UPDATE|DELETE).*\+\s*(request|params|input|user)',
     "sql_injection_risk", "high", "潜在SQL注入 - 查询中使用字符串拼接"),
    (r'(?i)eval\s*\(', "eval_usage", "high", "使用eval()存在安全风险"),
    (r'(?i)exec\s*\(', "exec_usage", "high", "使用exec()存在安全风险"),
    (r'(?i)innerHTML\s*=', "xss_risk", "medium", "直接赋值innerHTML可能导致XSS"),
    (r'(?i)shell\s*=\s*True', "shell_injection", "high", "subprocess中使用shell=True存在风险"),
    (r'(?i)disable.*ssl.*verify|verify\s*=\s*False', "ssl_disabled", "medium",
     "SSL验证已禁用"),
]

QUALITY_PATTERNS = [
    (r'TODO|FIXME|HACK|XXX', "todo_fixme", "info", "发现TODO/FIXME注释"),
    (r'(?i)password|token|secret', "sensitive_keyword", "low",
     "代码中存在敏感关键字 - 请确认无泄露"),
    (r'except\s*:', "bare_except", "medium", "裸except子句捕获所有异常"),
    (r'except\s+Exception', "broad_except", "low", "过宽的异常处理"),
    (r'pass\s*$', "empty_pass", "low", "异常处理中存在空pass语句"),
    (r'print\s*\(', "print_statement", "info", "调试用print语句应移除"),
    (r'console\.log\s*\(', "console_log", "info", "调试用console.log应移除"),
]


class SimpleFlow(BaseFlow):
    """
    Simple rule-based review flow.
    No model calls - uses regex patterns for static analysis.
    Used for offline mode and basic validation.
    """

    @property
    def flow_mode(self) -> str:
        return "simple"

    async def run(self, diff: str, pr_description: str, config: Dict) -> ReviewResult:
        findings = []
        finding_id = 0

        files = self._parse_diff_files(diff)

        for file_path, file_diff in files.items():
            for pattern, category, severity, title in SECURITY_PATTERNS:
                matches = re.finditer(pattern, file_diff)
                for match in matches:
                    finding_id += 1
                    line_num = self._get_line_number(file_diff, match.start())
                    findings.append(Finding(
                        id=f"SEC-{finding_id:03d}",
                        category="security",
                        severity=severity,
                        title=title,
                        description=f"在 {file_path} 中匹配到模式",
                        file_path=file_path,
                        line_range=str(line_num),
                        evidence=match.group()[:200],
                        suggestion="请审查并修复此安全问题",
                        confidence=0.7,
                    ))

            for pattern, category, severity, title in QUALITY_PATTERNS:
                matches = re.finditer(pattern, file_diff, re.MULTILINE)
                for match in matches:
                    finding_id += 1
                    line_num = self._get_line_number(file_diff, match.start())
                    findings.append(Finding(
                        id=f"QUA-{finding_id:03d}",
                        category="quality",
                        severity=severity,
                        title=title,
                        description=f"在 {file_path} 中匹配到模式",
                        file_path=file_path,
                        line_range=str(line_num),
                        evidence=match.group()[:200],
                        suggestion="建议处理此代码质量问题",
                        confidence=0.6,
                    ))

        summary = f"简单扫描发现 {len(findings)} 个潜在问题"
        return ReviewResult(
            findings=findings,
            summary=summary,
            offline=True,
            metadata={"pattern_count": len(SECURITY_PATTERNS) + len(QUALITY_PATTERNS)},
        )

    @staticmethod
    def _parse_diff_files(diff: str) -> Dict[str, str]:
        """Parse unified diff into {file_path: diff_segment} dict"""
        files = {}
        current_file = None
        current_lines = []

        for line in diff.split("\n"):
            if line.startswith("+++ b/"):
                if current_file and current_lines:
                    files[current_file] = "\n".join(current_lines)
                current_file = line[6:]
                current_lines = []
            elif current_file is not None:
                current_lines.append(line)

        if current_file and current_lines:
            files[current_file] = "\n".join(current_lines)

        if not files and diff.strip():
            files["unknown"] = diff

        return files

    @staticmethod
    def _get_line_number(text: str, pos: int) -> int:
        """Get approximate line number for a position in text"""
        return text[:pos].count("\n") + 1
