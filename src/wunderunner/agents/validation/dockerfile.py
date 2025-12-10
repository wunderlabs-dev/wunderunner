"""Dockerfile validation agent with grading rubric."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.models.validation import ValidationResult
from wunderunner.settings import Validation, get_model

USER_PROMPT = Template("""\
<dockerfile>
{{ dockerfile }}
</dockerfile>

<project_analysis>
{{ analysis | tojson(indent=2) }}
</project_analysis>

{% if learnings %}
<previous_errors>
{% for learning in learnings %}
- [{{ learning.phase }}] {{ learning.error_type }}: {{ learning.error_message }}
{%- if learning.context %}
  Context: {{ learning.context }}
{%- endif %}
{% endfor %}
</previous_errors>
{% endif %}

{% if hints %}
<user_hints>
{{ hints }}
</user_hints>
{% endif %}

Grade this Dockerfile according to the rubric.\
""")

SYSTEM_PROMPT = """\
<task>
Grade a development Dockerfile using the rubric below.
Provide an objective grade (0-110 points) with detailed breakdown.
</task>

<grading_rubric>
<section name="critical" points="50">
<category name="secrets" points="30">
Check project_analysis.env_vars for vars with secret=true.
If NO secrets required: automatic 30 points.

If secrets ARE required:
- 30 points: All secrets declared with ARG + ENV before RUN commands
- 15 points: Secrets declared but wrong order or format
- 0 points: Missing required secrets or hardcoded values

Deductions: -5 per wrong format, -10 per missing secret
</category>

<category name="runtime_config" points="20">
- 10 points: Port from project_analysis exposed correctly
- 5 points: EXPOSE instruction present
- 5 points: WORKDIR set appropriately
</category>
</section>

<section name="high_priority" points="30">
<category name="package_manager" points="15">
Grade INTERNAL CONSISTENCY only:
- 15 points: Lockfile copied, install command matches, deps installed before source
- 10 points: Consistent but wrong order (deps after source)
- 5 points: Minor inconsistencies but should work
- 0 points: Lockfile and install command mismatch
</category>

<category name="source_copy" points="10">
- 10 points: Single COPY . . command
- 5 points: Multiple COPY commands but correct
- 0 points: Missing source copy
</category>

<category name="base_image" points="5">
- 5 points: Matches runtime from project_analysis
- 3 points: Compatible but suboptimal
- 0 points: Wrong runtime or no FROM
</category>
</section>

<section name="medium_priority" points="20">
<category name="dev_mode" points="10">
This is a DEVELOPMENT container - should include dev dependencies.
- 10 points: Dev dependencies included (no --production, --no-dev flags)
- 5 points: Unclear but functional
- 0 points: Production flags present (wrong mode)
</category>

<category name="simplicity" points="5">
- 5 points: 10-20 instructions, no complex bash
- 3 points: >20 instructions or some complexity
- 0 points: Excessive complexity
</category>

<category name="system_deps" points="5">
- 5 points: System deps only when needed for native modules
- 3 points: Unnecessary deps but functional
- 0 points: Missing required deps
</category>
</section>

<section name="bonus" points="10">
<category name="error_resolution" points="10">
Only if previous_errors provided:
- +10 points: Fixes the previous error
- +5 points: Attempts to fix
- 0 points: Doesn't address error
</category>
</section>
</grading_rubric>

<grading_scale>
- 90-100: EXCELLENT - proceed to build
- 75-89: GOOD - minor issues, proceed
- 60-74: ACCEPTABLE - worth trying
- Below 60: FAIL - regenerate
</grading_scale>

<validation_philosophy>
Trust the generator, validate internal consistency.

Grade strictly: secrets, internal consistency
Grade leniently: package manager choice, file references, build patterns
Never fail for: CMD format, files generator may have seen
</validation_philosophy>

<output>
- is_valid: true if grade >= 80
- grade: 0-110
- breakdown: points per category
- feedback: concise summary
- issues: list of problems (empty if valid)
- recommendations: actionable improvements
</output>
"""

agent = Agent(
    model=get_model(Validation.DOCKERFILE),
    output_type=ValidationResult,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
