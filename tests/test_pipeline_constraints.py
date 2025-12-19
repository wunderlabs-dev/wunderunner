"""Tests for constraint management."""

from wunderunner.pipeline.errors.constraints import (
    derive_constraint,
    increment_success_counts,
    update_constraints,
)
from wunderunner.pipeline.models import (
    Constraint,
    ConstraintStatus,
    FixAttempt,
    FixError,
    FixHistory,
)


def test_derive_constraint_creates_hard_constraint():
    """derive_constraint creates a hard constraint from fix attempt."""
    attempt = FixAttempt(
        attempt=1,
        phase="BUILD",
        error=FixError(type="missing_dependency", message="No module pandas"),
        diagnosis="pandas not installed",
        outcome="success",
    )

    constraint = derive_constraint(attempt, "MUST include pandas in pip install")

    assert constraint.status == ConstraintStatus.HARD
    assert constraint.rule == "MUST include pandas in pip install"
    assert constraint.from_attempt == 1
    assert constraint.success_count == 0


def test_increment_success_counts_increments():
    """increment_success_counts adds 1 to all constraint success_count."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=0),
            Constraint(id="c2", rule="rule2", reason="r2", from_attempt=2, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 1
    assert updated.active_constraints[1].success_count == 3


def test_increment_success_counts_makes_soft_at_threshold():
    """Constraints become soft after 3 successful builds."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 3
    assert updated.active_constraints[0].status == ConstraintStatus.SOFT


def test_update_constraints_adds_new():
    """update_constraints adds new constraint to history."""
    history = FixHistory(project="test", active_constraints=[])
    new_constraint = Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1)

    updated = update_constraints(history, new_constraint)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].rule == "rule1"


def test_update_constraints_resets_violated():
    """update_constraints resets violated constraint to hard."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(
                id="c1", rule="rule1", reason="r1", from_attempt=1,
                success_count=5, status=ConstraintStatus.SOFT,
            ),
        ],
    )

    # Same rule, new attempt = was violated
    new_constraint = Constraint(id="c1-v2", rule="rule1", reason="violated", from_attempt=3)

    updated = update_constraints(history, new_constraint, violated=True)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].status == ConstraintStatus.HARD
    assert updated.active_constraints[0].success_count == 0
