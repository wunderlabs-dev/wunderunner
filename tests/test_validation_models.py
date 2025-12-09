"""Tests for validation models."""

import pytest

from wunderunner.models.validation import GradeBreakdown, ValidationResult


class TestGradeBreakdown:
    """Tests for GradeBreakdown model."""

    def test_total_calculation(self) -> None:
        """Total should sum all categories."""
        breakdown = GradeBreakdown(
            secrets=30,
            runtime=20,
            package_manager=15,
            source_copy=10,
            base_image=5,
            build_mode=10,
            simplicity=5,
            system_deps=5,
            bonus=10,
        )
        assert breakdown.total == 110

    def test_default_values(self) -> None:
        """Default values should be zero."""
        breakdown = GradeBreakdown()
        assert breakdown.total == 0
        assert breakdown.secrets == 0
        assert breakdown.runtime == 0

    def test_partial_values(self) -> None:
        """Partial values should work correctly."""
        breakdown = GradeBreakdown(secrets=25, runtime=15)
        assert breakdown.total == 40


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_result(self) -> None:
        """Valid result should have is_valid=True."""
        result = ValidationResult(
            is_valid=True,
            grade=95,
            breakdown=GradeBreakdown(
                secrets=30,
                runtime=20,
                package_manager=15,
                source_copy=10,
                base_image=5,
                build_mode=10,
                simplicity=5,
            ),
            feedback="Excellent Dockerfile",
        )
        assert result.is_valid
        assert result.grade == 95
        assert result.issues == []

    def test_invalid_result(self) -> None:
        """Invalid result should have is_valid=False."""
        result = ValidationResult(
            is_valid=False,
            grade=55,
            breakdown=GradeBreakdown(secrets=15, runtime=10),
            feedback="Missing secrets",
            issues=["Missing ARG for DATABASE_URL"],
            recommendations=["Add ARG DATABASE_URL before RUN commands"],
        )
        assert not result.is_valid
        assert result.grade == 55
        assert len(result.issues) == 1

    def test_programmatic_failure_factory(self) -> None:
        """programmatic_failure should create a failed result."""
        issues = ["Missing WORKDIR", "Invalid FROM"]
        result = ValidationResult.programmatic_failure(issues)

        assert not result.is_valid
        assert result.grade == 0
        assert result.breakdown.total == 0
        assert result.feedback == "Failed programmatic validation"
        assert result.issues == issues
        assert result.recommendations == issues
