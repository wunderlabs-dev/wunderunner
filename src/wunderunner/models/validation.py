"""Pydantic models for Dockerfile validation."""

from pydantic import BaseModel


class GradeBreakdown(BaseModel):
    """Point breakdown for each grading category."""

    secrets: int = 0  # 0-30
    runtime: int = 0  # 0-20
    package_manager: int = 0  # 0-15
    source_copy: int = 0  # 0-10
    base_image: int = 0  # 0-5
    build_mode: int = 0  # 0-10 (development vs production appropriateness)
    simplicity: int = 0  # 0-5
    system_deps: int = 0  # 0-5
    bonus: int = 0  # 0-10

    @property
    def total(self) -> int:
        """Calculate total grade (max 110 with bonus)."""
        return (
            self.secrets
            + self.runtime
            + self.package_manager
            + self.source_copy
            + self.base_image
            + self.build_mode
            + self.simplicity
            + self.system_deps
            + self.bonus
        )


class ValidationResult(BaseModel):
    """Result of Dockerfile validation."""

    is_valid: bool
    grade: int  # 0-110
    breakdown: GradeBreakdown
    feedback: str
    issues: list[str] = []
    recommendations: list[str] = []

    @classmethod
    def programmatic_failure(cls, issues: list[str]) -> "ValidationResult":
        """Create a failed result from programmatic validation."""
        return cls(
            is_valid=False,
            grade=0,
            breakdown=GradeBreakdown(),
            feedback="Failed programmatic validation",
            issues=issues,
            recommendations=issues,
        )
