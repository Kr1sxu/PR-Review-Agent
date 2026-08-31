"""
Tool Registry - PR-Review Agent
Unified tool registration for AgentScope Toolkit
"""

import logging
from typing import Optional

from agentscope.tool._toolkit import Toolkit

from src.tools.read_file import ReadFileTool
from src.tools.search_code import SearchCodeTool
from src.tools.run_tests import RunTestsTool
from src.tools.risk_scan import RiskScanTool
from src.tools.retrieve_company_policy import RetrieveCompanyPolicyTool
from src.tools.git_ops_tool import GitOpsTool

logger = logging.getLogger(__name__)


def create_toolkit(
    allowed_roots: list[str] | None = None,
    enable_tests: bool = False,
    test_commands: list[str] | None = None,
    repo_path: str = ".",
) -> Toolkit:
    """
    Create and configure the AgentScope Toolkit with all PR-Review tools.
    :param allowed_roots: Allowed root directories for file access
    :param enable_tests: Whether to enable test execution
    :param test_commands: Whitelist of allowed test commands
    :param repo_path: Path to the git repository for GitOpsTool
    :return: Configured Toolkit instance
    """
    tools = [
        ReadFileTool(allowed_roots=allowed_roots),
        SearchCodeTool(),
        RunTestsTool(enabled=enable_tests, allowed_commands=test_commands),
        RiskScanTool(),
        RetrieveCompanyPolicyTool(),
        GitOpsTool(repo_path=repo_path),
    ]
    toolkit = Toolkit(tools=tools)
    logger.info(
        f"Toolkit created with {len(tools)} tools, "
        f"tests={'enabled' if enable_tests else 'disabled'}"
    )
    return toolkit
