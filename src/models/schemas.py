"""
Structured output schemas for PR-Review Agent.
Used with AgentScope's structured_schema to force agents to produce
findings output instead of looping on tool calls.
"""

from pydantic import BaseModel, Field


class FindingItem(BaseModel):
    """A single defect finding."""
    id: str = Field(description="Unique finding ID, e.g. SEC-001")
    category: str = Field(description="Category: security, logic, testing, maintainability, compliance")
    severity: str = Field(description="Severity: critical, high, medium, low, info")
    title: str = Field(description="Short title of the finding")
    description: str = Field(description="Detailed description of the issue")
    file_path: str = Field(description="File path where the issue was found")
    line_range: str = Field(description="Line range, e.g. 42-50", default="")
    evidence: str = Field(description="Code snippet evidence", default="")
    suggestion: str = Field(description="Suggested fix", default="")
    confidence: float = Field(description="Confidence score 0-1", default=0.5, ge=0, le=1)
    spec_reference: str = Field(description="Related spec reference", default="")


class FindingsOutput(BaseModel):
    """Structured output schema for reviewer agents.
    
    Agents MUST call GenerateStructuredOutput with this schema
    to produce their final findings. This prevents infinite tool-calling loops.
    """
    findings: list[FindingItem] = Field(
        description="List of defect findings. Empty array if no issues found.",
        default_factory=list,
    )
    summary: str = Field(
        description="Brief summary of the review analysis",
        default="",
    )
