"""Tests for exception hierarchy."""

import pytest

from wunderunner.exceptions import (
    AnalyzeError,
    BuildError,
    DockerfileError,
    HealthcheckError,
    ServicesError,
    StartError,
    ValidationError,
    WunderunnerError,
)


class TestExceptionHierarchy:
    """Test exception inheritance and structure."""

    def test_base_exception_exists(self):
        """WunderunnerError is the base exception."""
        error = WunderunnerError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"

    @pytest.mark.parametrize(
        "exception_class",
        [
            AnalyzeError,
            DockerfileError,
            ServicesError,
            BuildError,
            StartError,
            HealthcheckError,
            ValidationError,
        ],
    )
    def test_all_exceptions_inherit_from_base(self, exception_class):
        """All custom exceptions inherit from WunderunnerError."""
        error = exception_class("specific error")
        assert isinstance(error, WunderunnerError)
        assert isinstance(error, Exception)

    def test_exceptions_preserve_message(self):
        """Exceptions preserve their error messages."""
        msg = "Build failed: missing dependency"
        error = BuildError(msg)
        assert str(error) == msg
        assert error.args == (msg,)

    def test_exceptions_can_be_raised_and_caught(self):
        """Exceptions can be raised and caught by type."""
        with pytest.raises(BuildError):
            raise BuildError("build failed")

        # Can also catch by base type
        with pytest.raises(WunderunnerError):
            raise ValidationError("validation failed")
