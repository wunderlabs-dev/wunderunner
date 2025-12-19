"""Constraint management for fix history."""

from wunderunner.pipeline.models import (
    Constraint,
    ConstraintStatus,
    FixAttempt,
    FixHistory,
)

SOFT_THRESHOLD = 3  # Constraints become soft after this many successes


def derive_constraint(attempt: FixAttempt, rule: str) -> Constraint:
    """Create a constraint from a successful fix attempt.

    Args:
        attempt: The fix attempt that succeeded.
        rule: The constraint rule text.

    Returns:
        New hard constraint.
    """
    return Constraint(
        id=f"c{attempt.attempt}",
        rule=rule,
        reason=attempt.diagnosis,
        from_attempt=attempt.attempt,
        success_count=0,
        status=ConstraintStatus.HARD,
    )


def increment_success_counts(history: FixHistory) -> FixHistory:
    """Increment success_count for all constraints after successful build.

    Constraints become soft after reaching SOFT_THRESHOLD successes.

    Args:
        history: Current fix history.

    Returns:
        Updated fix history with incremented counts.
    """
    updated_constraints = []

    for constraint in history.active_constraints:
        new_count = constraint.success_count + 1
        new_status = constraint.status

        if new_count >= SOFT_THRESHOLD and constraint.status == ConstraintStatus.HARD:
            new_status = ConstraintStatus.SOFT

        updated_constraints.append(
            Constraint(
                id=constraint.id,
                rule=constraint.rule,
                reason=constraint.reason,
                from_attempt=constraint.from_attempt,
                added_at=constraint.added_at,
                success_count=new_count,
                status=new_status,
            )
        )

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )


def update_constraints(
    history: FixHistory,
    new_constraint: Constraint,
    violated: bool = False,
) -> FixHistory:
    """Add or update a constraint in history.

    If violated=True, resets an existing constraint with same rule to hard.

    Args:
        history: Current fix history.
        new_constraint: Constraint to add or update.
        violated: Whether this is a violated constraint being reset.

    Returns:
        Updated fix history.
    """
    updated_constraints = []

    # Check if constraint with same rule exists
    found_existing = False
    for existing in history.active_constraints:
        if existing.rule == new_constraint.rule:
            found_existing = True
            if violated:
                # Reset to hard with 0 success count
                updated_constraints.append(
                    Constraint(
                        id=new_constraint.id,
                        rule=new_constraint.rule,
                        reason=new_constraint.reason,
                        from_attempt=new_constraint.from_attempt,
                        success_count=0,
                        status=ConstraintStatus.HARD,
                    )
                )
            else:
                # Keep existing
                updated_constraints.append(existing)
        else:
            updated_constraints.append(existing)

    # Add new if not found
    if not found_existing:
        updated_constraints.append(new_constraint)

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )
