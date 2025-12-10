"""Project fixer agent - can modify project files to fix issues."""

import logging

from jinja2 import Template
from pydantic import BaseModel
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.settings import Generation, get_model

logger = logging.getLogger(__name__)

USER_PROMPT = Template("""\
<project_analysis>
{{ analysis | tojson(indent=2) }}
</project_analysis>

<error>
Phase: {{ phase }}
Error: {{ error_type }}
Message: {{ error_message }}
{% if context %}
Context: {{ context }}
{% endif %}
</error>

<dockerfile>
{{ dockerfile }}
</dockerfile>

{% if compose %}
<docker_compose>
{{ compose }}
</docker_compose>
{% endif %}

Based on the project analysis and error above, determine if the issue can be fixed
by modifying project files. If you can fix it, make the changes. If not, explain why.
""")

SYSTEM_PROMPT = """\
<task>
You are a project fixer agent. When containerization fails (build error, start error, etc.),
you investigate the root cause and fix project files if needed.

You have tools to:
- read_file: Read any project file
- list_dir: List directory contents
- grep: Search for patterns
- glob: Find files by pattern
- write_file: Create new files or overwrite existing ones
- edit_file: Replace old_string with new_string in a file (for surgical edits)

Your goal is to fix the PROJECT FILES (not Dockerfile) when the issue is in the project itself.
</task>

<when_to_fix>
Fix project files when:
- Missing required files (e.g., .env.example, config files)
- Wrong file permissions
- Missing scripts in package.json
- Missing dependencies that should be added
- Incorrect configuration

Do NOT fix:
- Issues that should be fixed in Dockerfile
- Issues requiring major code refactoring
- Security vulnerabilities (report them instead)
</when_to_fix>

<common_fixes>
1. Missing start script in package.json:
   - Add "start": "node dist/index.js" or similar

2. Missing .env.example:
   - Create from detected env vars

3. Missing health check endpoint:
   - Add /health route returning 200 OK

4. Wrong entry point path:
   - Check and fix main/bin in package.json
   - Check pyproject.toml scripts

5. Missing configuration:
   - Create default config files
</common_fixes>

<output_format>
Return a FixResult with:
- fixed: true if you made changes, false if no fix was possible/needed
- changes: list of files modified (empty if fixed=false)
- explanation: what you did or why you couldn't fix it
</output_format>

<safety>
NEVER:
- Delete files without explicit confirmation
- Modify sensitive files (.env with real secrets, credentials)
- Make changes outside the project directory
- Add malicious code
</safety>
"""


class FixResult(BaseModel):
    """Result of a fix attempt."""

    fixed: bool
    changes: list[str]
    explanation: str


agent = Agent(
    model=get_model(Generation.DOCKERFILE),  # Use same model as dockerfile gen
    output_type=FixResult,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
    max_result_retries=3,  # Limit retries on invalid output
)

register_tools(agent, include_write=True)
