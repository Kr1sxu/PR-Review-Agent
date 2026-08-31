"""
Skill Loader - PR-Review Agent
Loads SKILL.md content and provides structured sections for agents.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default skill path relative to project root
_DEFAULT_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "code-review" / "SKILL.md"


def load_skill(skill_path: Optional[str] = None) -> str:
    """
    Load the full SKILL.md content.
    :param skill_path: Optional custom path to SKILL.md
    :return: Full skill content as string, or empty string if not found
    """
    path = Path(skill_path) if skill_path else _DEFAULT_SKILL_PATH
    if not path.exists():
        logger.warning(f"Skill file not found: {path}")
        return ""
    try:
        content = path.read_text(encoding="utf-8")
        logger.info(f"Loaded skill: {path} ({len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"Failed to load skill: {e}")
        return ""


def get_review_checklist(skill_content: str) -> str:
    """Extract the review checklist section (Section 1)."""
    return _extract_section(skill_content, "## 1. 审查清单", "## 2. 输出格式")


def get_output_schema(skill_content: str) -> str:
    """Extract the output format section (Section 2)."""
    return _extract_section(skill_content, "## 2. 输出格式", "## 3. 裁决规则")


def get_decision_rules(skill_content: str) -> str:
    """Extract the decision rules section (Section 3)."""
    return _extract_section(skill_content, "## 3. 裁决规则", "## 4. 常见反模式")


def get_anti_patterns(skill_content: str) -> str:
    """Extract the anti-patterns section (Section 4)."""
    return _extract_section(skill_content, "## 4. 常见反模式", "## 5. 审查辅助工具")


def get_review_tools(skill_content: str) -> str:
    """Extract the review tools section (Section 5)."""
    return _extract_section(skill_content, "## 5. 审查辅助工具", "## 6. 审查工作流")


def get_review_workflow(skill_content: str) -> str:
    """Extract the review workflow section (Section 6)."""
    return _extract_section(skill_content, "## 6. 审查工作流", "## 附录")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two markdown section markers."""
    start_idx = content.find(start_marker)
    if start_idx == -1:
        return ""
    end_idx = content.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        return content[start_idx:].strip()
    return content[start_idx:end_idx].strip()
