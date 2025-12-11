"""Tests for compose generation with services."""


def test_compose_prompt_includes_services():
    """Compose USER_PROMPT template accepts services parameter."""
    from wunderunner.agents.generation.compose import USER_PROMPT

    # Should render without error when services provided
    rendered = USER_PROMPT.render(
        analysis={"project_structure": {"runtime": "node", "port": 3000}},
        dockerfile="FROM node:20",
        secrets=[],
        learnings=[],
        hints=[],
        existing_compose=None,
        services=[{"type": "postgres", "env_vars": ["DATABASE_URL"]}],
    )

    assert "postgres" in rendered


def test_compose_system_prompt_mentions_services():
    """Compose SYSTEM_PROMPT includes guidance for services."""
    from wunderunner.agents.generation.compose import SYSTEM_PROMPT

    assert "services" in SYSTEM_PROMPT.lower()
    # Should mention depends_on for service ordering
    assert "depends_on" in SYSTEM_PROMPT
