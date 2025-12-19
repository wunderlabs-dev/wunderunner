"""Tests for ERROR-RESEARCH agent."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.errors.research import run_error_research
from wunderunner.pipeline.models import (
    ErrorAnalysis,
    ExhaustionItem,
    FixAttempt,
    FixError,
    FixHistory,
)


@pytest.fixture
def error_context() -> dict:
    """Sample error context."""
    return {
        "phase": "BUILD",
        "error": "npm ERR! Missing script: build",
        "log_path": "/tmp/logs/attempt-1.log",
    }


@pytest.fixture
def fix_history() -> FixHistory:
    """Sample fix history with one attempt."""
    return FixHistory(
        project="test",
        attempts=[
            FixAttempt(
                attempt=1,
                phase="BUILD",
                error=FixError(type="syntax", message="Dockerfile syntax error"),
                diagnosis="Missing FROM instruction",
                outcome="success",
            )
        ],
        active_constraints=[],
    )


@pytest.mark.asyncio
async def test_run_error_research_returns_analysis(
    tmp_path: Path, error_context: dict, fix_history: FixHistory
):
    """run_error_research returns ErrorAnalysis."""
    mock_analysis = ErrorAnalysis(
        error_summary="BUILD failed: missing build script",
        root_cause="package.json has no build script",
        fix_history_review="1 previous attempt for syntax error",
        exhaustion_status=[
            ExhaustionItem(approach="Add build script", attempted=False),
            ExhaustionItem(approach="Use different start command", attempted=False),
        ],
        recommendation="continue",
        suggested_approach="Add build script to package.json",
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="# Project Research\n...",
            fix_history=fix_history,
        )

    assert isinstance(result, ErrorAnalysis)
    assert result.recommendation == "continue"
    assert len(result.exhaustion_status) == 2


@pytest.mark.asyncio
async def test_run_error_research_detects_exhaustion(
    tmp_path: Path, error_context: dict
):
    """run_error_research can recommend stopping."""
    history = FixHistory(
        project="test",
        attempts=[
            FixAttempt(
                attempt=1, phase="BUILD", diagnosis="d", outcome="failure",
                error=FixError(type="x", message="x"),
            ),
            FixAttempt(
                attempt=2, phase="BUILD", diagnosis="d", outcome="failure",
                error=FixError(type="x", message="x"),
            ),
            FixAttempt(
                attempt=3, phase="BUILD", diagnosis="d", outcome="failure",
                error=FixError(type="x", message="x"),
            ),
        ],
        active_constraints=[],
    )

    mock_analysis = ErrorAnalysis(
        error_summary="Persistent failure",
        root_cause="Unknown",
        fix_history_review="3 failed attempts",
        exhaustion_status=[
            ExhaustionItem(approach="Approach 1", attempted=True),
            ExhaustionItem(approach="Approach 2", attempted=True),
        ],
        recommendation="stop",
        suggested_approach=None,
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="...",
            fix_history=history,
        )

    assert result.recommendation == "stop"
