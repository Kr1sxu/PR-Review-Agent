"""
Tools Unit Tests - PR-Review Agent
Test read-only constraints, parameter validation, tool registration
"""

import os
import pytest
from pathlib import Path

from agentscope.tool._response import ToolResultState

from src.tools.read_file import ReadFileTool
from src.tools.search_code import SearchCodeTool
from src.tools.run_tests import RunTestsTool
from src.tools.tool_registry import create_toolkit


class TestReadFileTool:
    """Read file tool tests"""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\nprint('world')\n", encoding="utf-8")
        tool = ReadFileTool()
        result = await tool.call(str(test_file))
        assert result.state == ToolResultState.SUCCESS
        text = result.content[0].text
        assert "print('hello')" in text
        assert "1 |" in text  # line number

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_path):
        tool = ReadFileTool()
        result = await tool.call(str(tmp_path / "nonexistent.py"))
        assert result.state == ToolResultState.ERROR

    @pytest.mark.asyncio
    async def test_path_restriction(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        tool = ReadFileTool(allowed_roots=[str(allowed)])
        result = await tool.call(str(secret))
        assert result.state == ToolResultState.ERROR

    def test_is_read_only(self):
        tool = ReadFileTool()
        assert tool.is_read_only is True


class TestSearchCodeTool:
    """Search code tool tests"""

    @pytest.mark.asyncio
    async def test_search_keyword(self, tmp_path):
        (tmp_path / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def world():\n    pass\n", encoding="utf-8")
        tool = SearchCodeTool()
        result = await tool.call("hello", directory=str(tmp_path))
        assert result.state == ToolResultState.SUCCESS
        assert "a.py" in result.content[0].text

    @pytest.mark.asyncio
    async def test_search_with_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("password = '123'\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("password = '456'\n", encoding="utf-8")
        tool = SearchCodeTool()
        result = await tool.call("password", directory=str(tmp_path), file_pattern=".py")
        assert "a.py" in result.content[0].text
        assert "b.txt" not in result.content[0].text

    @pytest.mark.asyncio
    async def test_search_no_results(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        tool = SearchCodeTool()
        result = await tool.call("nonexistent_keyword_xyz", directory=str(tmp_path))
        assert result.state == ToolResultState.SUCCESS
        assert "No matches" in result.content[0].text

    @pytest.mark.asyncio
    async def test_search_invalid_directory(self):
        tool = SearchCodeTool()
        result = await tool.call("test", directory="/nonexistent/path/xyz")
        assert result.state == ToolResultState.ERROR

    def test_is_read_only(self):
        tool = SearchCodeTool()
        assert tool.is_read_only is True


class TestRunTestsTool:
    """Run tests tool tests"""

    @pytest.mark.asyncio
    async def test_disabled_by_default(self):
        tool = RunTestsTool()
        result = await tool.call("pytest")
        assert result.state == ToolResultState.DENIED
        assert "DISABLED" in result.content[0].text

    @pytest.mark.asyncio
    async def test_enabled_runs_command(self, tmp_path):
        tool = RunTestsTool(enabled=True)
        result = await tool.call("echo hello", cwd=str(tmp_path), timeout=10)
        assert result.state == ToolResultState.SUCCESS
        assert "hello" in result.content[0].text

    @pytest.mark.asyncio
    async def test_command_whitelist(self):
        tool = RunTestsTool(enabled=True, allowed_commands=["pytest", "python"])
        result = await tool.call("rm -rf /")
        assert result.state == ToolResultState.DENIED

    def test_is_not_read_only(self):
        tool = RunTestsTool()
        assert tool.is_read_only is False


class TestToolRegistry:
    """Tool registry tests"""

    @pytest.mark.asyncio
    async def test_create_toolkit(self):
        toolkit = create_toolkit()
        schemas = await toolkit.get_tool_schemas()
        assert len(schemas) >= 3

    def test_create_toolkit_with_tests_enabled(self):
        toolkit = create_toolkit(enable_tests=True)
        assert toolkit is not None
