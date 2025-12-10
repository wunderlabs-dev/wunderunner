"""Pydantic models for generation results."""

from pydantic import BaseModel, Field, field_validator


def strip_markdown_fences(content: str) -> str:
    """Strip markdown code fences from content if present."""
    content = content.strip()
    # Remove ```dockerfile, ```yaml, or ``` at start
    for prefix in ("```dockerfile", "```yaml", "```"):
        if content.startswith(prefix):
            content = content[len(prefix) :]
            break
    # Remove ``` at end
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


class DockerfileResult(BaseModel):
    """Result of Dockerfile generation with confidence tracking."""

    dockerfile: str = Field(description="The generated Dockerfile content")
    confidence: int = Field(
        ge=0,
        le=10,
        description="Confidence score 0-10. 9-10 for proven patterns, 5-8 for reasonable "
        "solutions, 1-4 for uncertain fixes, 0 for blind guesses.",
    )
    reasoning: str = Field(
        description="Brief explanation of why this Dockerfile should work and what was fixed"
    )

    @field_validator("dockerfile", mode="after")
    @classmethod
    def strip_fences(cls, v: str) -> str:
        """Strip markdown code fences if the model included them."""
        return strip_markdown_fences(v)
