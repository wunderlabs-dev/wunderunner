"""Pydantic models for generation results."""

from pydantic import BaseModel, Field


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
