"""Pydantic models for pipeline artifacts."""

from pydantic import BaseModel, Field


class RuntimeFindings(BaseModel):
    """Output from runtime-detector specialist."""

    language: str = Field(description="Runtime language: python, node, go, rust")
    version: str | None = Field(default=None, description="Version string: 3.11, 20, 1.21")
    framework: str | None = Field(default=None, description="Web framework: fastapi, express, gin")
    entrypoint: str | None = Field(default=None, description="Main file path: src/main.py")
