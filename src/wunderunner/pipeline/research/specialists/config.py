"""Config-finder specialist agent.

Identifies: environment variables, secrets, config files.
Documentarian framing: reports what exists, does NOT suggest improvements.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import ConfigFindings
from wunderunner.settings import Analysis, get_model

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its configuration requirements.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest different configuration approaches
- Recommend secrets management solutions
- Critique env var naming
- Add editorial commentary

Focus on facts only.

<env_var_detection>
Sources to check:
- .env.example, .env.sample, .env.template
- Code patterns: os.environ["VAR"], os.getenv("VAR"), process.env.VAR
- Config files: config.py, settings.py, config.ts, config.js

For each variable, determine:
- name: The variable name
- required: Does the code crash without it? (environ["X"] = required, getenv("X") = optional)
- secret: Does it contain sensitive data? (passwords, API keys, tokens, connection strings)
- default: Is there a default value?
- service: Is it related to a backing service? (DATABASE_URL → postgres, REDIS_URL → redis)
</env_var_detection>

<secret_patterns>
Variables that are ALWAYS secrets:
- *_API_KEY, *_SECRET, *_TOKEN, *_PASSWORD
- DATABASE_URL, REDIS_URL, *_CONNECTION_STRING
- AWS_*, STRIPE_*, GITHUB_TOKEN

Variables that are NOT secrets:
- PORT, HOST, NODE_ENV, DEBUG, LOG_LEVEL
- PUBLIC_*, NEXT_PUBLIC_*
</secret_patterns>

<config_files>
Report these if they exist:
- .env.example, .env.sample
- config.yaml, config.json
- settings.py, config.py
</config_files>

<workflow>
TURN 1 - Check for config files (batch these):
- check_files_exist([".env.example", ".env.sample", ".env.template"])
- list_dir(".")
- read_file(".env.example") if exists

TURN 2 - Search code for env var usage (batch these):
- grep("environ\\[|getenv\\(|process\\.env\\.", ".")
- read_file("src/config.py") or read_file("config.ts") if exists

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = (
    "Find all environment variables, secrets, and configuration files in this project."
)

agent = Agent(
    model=get_model(Analysis.ENV_VARS),  # Reuse existing model tier
    output_type=ConfigFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def find_config(project_dir: Path) -> ConfigFindings:
    """Run the config-finder specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ConfigFindings with env vars, secrets, config files.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.ENV_VARS),
    )
    return result.output
