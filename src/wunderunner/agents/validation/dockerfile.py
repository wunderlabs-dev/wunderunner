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
You are a senior DevOps engineer grading a Dockerfile using a strict rubric.
Your goal is to provide an objective grade (0-110 points) with detailed breakdown.
</task>

<grading_rubric>
Total: 100 points (+ up to 10 bonus)

## Critical Rules (50 points)

### Build-Time Secrets (30 points)
- **30 points**: All required secrets properly declared with ARG and ENV
  - Correct format: `ARG SECRET_NAME` and `ENV SECRET_NAME=$SECRET_NAME`
  - Declared before any RUN command that needs them
  - No hardcoded secret values
  - **If no secrets required: automatic 30 points** (check env_vars for secret=true)
- **15 points**: Secrets declared but some issues (wrong order, formatting)
- **0 points**: Missing required secrets or hardcoded values

**CRITICAL**: Check project_analysis.env_vars to see which vars have secret=true.
If NO env_vars have secret=true, give full 30 points - no secrets section needed.

**Important**: Only grade ACTUAL secrets that grant access (API keys, credentials).
Public identifiers (tracking IDs, publishable keys) are NOT secrets:
- NEXT_PUBLIC_*, VITE_*, REACT_APP_* prefixed vars are intentionally public
- Google Analytics IDs (G-*, UA-*), Stripe publishable keys (pk_*) are NOT secrets
- Firebase public config, Sentry DSNs are NOT secrets

**Deductions** (only if secrets ARE required):
- -5 points per secret with wrong format
- -10 points per missing required secret

### Runtime Configuration (20 points)
- **10 points**: Correct ENV settings for the runtime mode (production/development)
- **5 points**: EXPOSE instruction for the application port
- **5 points**: WORKDIR set appropriately

## High Priority Rules (30 points)

### Package Manager (15 points)
Grade INTERNAL CONSISTENCY only:
- **15 points**: Package manager internally consistent
  - Has lockfile copy (package-lock.json, yarn.lock, pnpm-lock.yaml, uv.lock, etc.)
  - Install command matches lockfile type
  - Dependencies installed BEFORE source code copy (for layer caching)
- **10 points**: Consistent but wrong order (deps after source)
- **5 points**: Minor inconsistencies but should work
- **0 points**: INCONSISTENT (e.g., bun.lock + npm install) or missing lockfile

### Source Code Copying (10 points)
- **10 points**: Single `COPY . .` command (trusts .dockerignore)
- **5 points**: Multiple COPY commands but functionally correct
- **0 points**: Complex filtering logic or missing source copy

### Base Image (5 points)
- **5 points**: Appropriate image for the runtime (slim/alpine variants preferred)
- **3 points**: Standard image (larger but functional)
- **0 points**: No FROM instruction or wrong runtime

## Medium Priority Rules (20 points)

### Build Mode (10 points)
- **10 points**: Correctly configured for intended mode:
  - Production: NODE_ENV=production, optimized build, minimal deps
  - Development: NODE_ENV=development, dev deps included
- **5 points**: Mode configured but some inefficiencies
- **0 points**: Wrong mode or misconfigured

### Simplicity (5 points)
- **5 points**: 10-20 instructions, no complex bash
- **3 points**: >20 instructions or some complex logic
- **0 points**: Excessive complexity, hacks, or workarounds

### System Dependencies (5 points)
- **5 points**: Correct system deps (only when needed for native modules)
- **3 points**: Unnecessary deps installed but doesn't break anything
- **0 points**: Missing required deps or broken package installation

## Bonus Points (up to 10 points)

### Error Resolution
- **+10 points**: Dockerfile demonstrably fixes the previous build error
- **+5 points**: Attempts to fix the error but may be incomplete
- **0 points**: Doesn't address the previous error

## Grading Scale
- **90-100**: EXCELLENT - Ready for build, proceed
- **75-89**: GOOD - Minor issues but should work, proceed to build
- **60-74**: ACCEPTABLE - Has issues but worth trying
- **Below 60**: FAIL - Critical issues, regenerate
</grading_rubric>

<validation_philosophy>
Trust the generator, validate internal consistency.

**Grade strictly**:
- Critical rules (secrets, runtime config) - these are objective
- Internal consistency (lockfile matches install command)

**Grade leniently**:
- Package manager choice - generator may have found different lockfile
- File references - if generator copies a file, assume it exists
- Build patterns - multiple valid approaches exist

**Never fail for**:
- Package manager mismatch with hints (npm hint vs bun reality)
- Files that "shouldn't exist" - generator sees filesystem, you don't
- CMD format (array vs string) - both work
</validation_philosophy>

<output_format>
Return a ValidationResult with:
- is_valid: true if grade >= 80
- grade: 0-110
- breakdown: points per category
- feedback: concise summary
- issues: empty if valid, else list of problems
- recommendations: specific actionable improvements
</output_format>
"""

agent = Agent(
    model=get_model(Validation.DOCKERFILE),
    output_type=ValidationResult,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
