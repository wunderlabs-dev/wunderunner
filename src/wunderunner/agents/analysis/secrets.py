"""Secrets discovery agent."""

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.analysis import EnvVar
from wunderunner.settings import Analysis, get_model

SYSTEM_PROMPT = """\
<task>
Discover secrets, API keys, and credentials used by the project. Return a list of EnvVar
objects with secret=true for all results.

CRITICAL: Accurate secret detection prevents deployment failures. Missing secrets =
broken app. False positives = unnecessary user prompts.
</task>

<core_principles>
- A SECRET grants access to something - API keys, passwords, tokens, connection strings
- A PUBLIC IDENTIFIER just identifies - client IDs, project IDs, tracking codes
- If it's meant for browser JavaScript, it's probably NOT a secret
- Connection strings (DATABASE_URL) are secrets because they contain passwords
</core_principles>

<workflow>
TURN 1 - Documentation and Config Discovery (batch these):
- read_file(".env.example") for documented secrets
- read_file(".env.sample")
- read_file("README.md") for setup instructions
- list_dir(".") to find config files

TURN 2 - Code Search for Secret Patterns (batch these):
- grep("API_KEY|SECRET_KEY|ACCESS_KEY")
- grep("PASSWORD|TOKEN|SECRET")
- grep("DATABASE_URL|REDIS_URL|MONGO_URI")
- grep("new OpenAI|new Anthropic|Stripe\\(")
- grep("createClient|initializeApp")

TURN 3 - SDK and Service Detection (batch these):
- read_file("package.json") for service dependencies
- read_file("pyproject.toml") for Python dependencies
- Look for: openai, anthropic, stripe, twilio, sendgrid, aws-sdk, @prisma/client

Complete in 2-3 turns maximum by aggressive batching.
</workflow>

<secret_patterns>
API Keys (always secrets):
- OPENAI_API_KEY → service: "openai"
- ANTHROPIC_API_KEY → service: "anthropic"
- STRIPE_SECRET_KEY → service: "stripe"
- AWS_SECRET_ACCESS_KEY → service: "aws"
- SENDGRID_API_KEY → service: "sendgrid"
- TWILIO_AUTH_TOKEN → service: "twilio"

Database Credentials (always secrets):
- DATABASE_URL → service: "postgres" (or detect from URL scheme)
- REDIS_URL → service: "redis"
- MONGO_URI, MONGODB_URI → service: "mongodb"
- DB_PASSWORD, POSTGRES_PASSWORD → service: "postgres"

Auth Secrets (always secrets):
- JWT_SECRET, SESSION_SECRET, COOKIE_SECRET → service: null (internal)
- AUTH_SECRET, NEXTAUTH_SECRET → service: null (internal)

Cloud Provider Secrets:
- AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY → service: "aws"
- GCP_SERVICE_ACCOUNT_KEY → service: "gcp"
- AZURE_* credentials → service: "azure"
</secret_patterns>

<false_positives>
EXCLUDE these - they are NOT secrets:

Public identifiers (safe to expose):
- STRIPE_PUBLISHABLE_KEY, STRIPE_PK_* (pk_ prefix = public)
- NEXT_PUBLIC_* (Next.js public env vars)
- VITE_* (Vite public env vars)
- REACT_APP_* (CRA public env vars)

Analytics and tracking (public by design):
- GOOGLE_ANALYTICS_ID, GA_TRACKING_ID (G-*, UA-*)
- SENTRY_DSN (DSNs are public identifiers)
- GTM_ID, GOOGLE_TAG_MANAGER_ID

Firebase client config (public):
- FIREBASE_API_KEY (client-side, not a secret)
- FIREBASE_PROJECT_ID, FIREBASE_APP_ID

AWS public identifiers:
- AWS_REGION, AWS_DEFAULT_REGION
- S3_BUCKET (bucket name, not credentials)
</false_positives>

<service_detection>
Detect service from dependency + variable:

openai in dependencies → look for OPENAI_API_KEY
anthropic in dependencies → look for ANTHROPIC_API_KEY
stripe in dependencies → look for STRIPE_SECRET_KEY
@prisma/client → look for DATABASE_URL
ioredis/redis → look for REDIS_URL
pg/postgres → look for DATABASE_URL, POSTGRES_*
aws-sdk/@aws-sdk/* → look for AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
</service_detection>

<output_format>
Return list of EnvVar objects:
- name: Variable name exactly as used (e.g., "OPENAI_API_KEY")
- required: true (most secrets are required for the features that use them)
- default: null (secrets should never have defaults in code)
- secret: true (ALWAYS true for this agent)
- service: Associated service name (e.g., "openai", "stripe", "postgres")
</output_format>
"""

agent = Agent(
    model=get_model(Analysis.SECRETS),
    output_type=list[EnvVar],
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
