"""Regression detection agent for Dockerfile changes."""

from jinja2 import Template
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from wunderunner.settings import Validation, get_model


class RegressionResult(BaseModel):
    """Result of regression check."""

    has_regression: bool = Field(description="True if previous fixes were undone")
    violations: list[str] = Field(
        default_factory=list,
        description="List of specific fixes that were undone",
    )
    adjusted_confidence: int = Field(
        ge=0,
        le=10,
        description="Adjusted confidence score (capped at 3 if regression detected)",
    )


USER_PROMPT = Template("""\
<new_dockerfile>
{{ dockerfile }}
</new_dockerfile>

<historical_fixes>
These fixes were applied in previous iterations and should be preserved:
{% for fix in historical_fixes %}
{{ loop.index }}. {{ fix.explanation }}
{%- if fix.fix %}
   Applied: {{ fix.fix }}
{%- endif %}
{%- if fix.error %}
   Original error: {{ fix.error }}
{%- endif %}
{% endfor %}
</historical_fixes>

<original_confidence>{{ original_confidence }}</original_confidence>

Check if the new Dockerfile preserves all the historical fixes.
""")

SYSTEM_PROMPT = """\
<task>
You are a regression detector. Check if a new Dockerfile undoes any previous fixes.

For each historical fix, verify it's still present in the new Dockerfile.
A regression means a fix that worked before is now missing or undone.
</task>

<examples>
Historical fix: "Added ARG DATABASE_URL for build-time secret"
New Dockerfile has: ARG DATABASE_URL → NO REGRESSION
New Dockerfile missing ARG DATABASE_URL → REGRESSION

Historical fix: "Changed to node:20 (non-alpine) for native deps"
New Dockerfile has: FROM node:20-alpine → REGRESSION (went back to alpine)
New Dockerfile has: FROM node:20 → NO REGRESSION
</examples>

<output>
- has_regression: true if ANY fix was undone
- violations: list what was undone (empty if no regression)
- adjusted_confidence: if regression, cap at 3. Otherwise return original_confidence.
</output>
"""

agent = Agent(
    model=get_model(Validation.DOCKERFILE),
    output_type=RegressionResult,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
