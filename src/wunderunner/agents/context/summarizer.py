"""Context summarization agent."""

from pydantic_ai import Agent

from wunderunner.models.context import ContextEntry
from wunderunner.settings import Context, get_model

SYSTEM_PROMPT = """\
You are a concise summarizer of Docker containerization learnings.

Given a list of context entries (errors, fixes, and explanations from previous
Dockerfile generation attempts), produce a 2-3 sentence summary that captures:

1. Key patterns that failed (and why)
2. What fixes worked
3. Important constraints discovered about this project

Be specific and actionable. The summary will be used to guide future Dockerfile
generation, so focus on information that prevents repeating past mistakes.

Output ONLY the summary text, no preamble or formatting.
"""

agent = Agent(
    model=get_model(Context.SUMMARIZER),
    output_type=str,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def summarize(entries: list[ContextEntry], existing_summary: str | None) -> str:
    """Summarize context entries into a concise learning summary.

    Args:
        entries: List of context entries to summarize.
        existing_summary: Previous summary to incorporate (if any).

    Returns:
        A 2-3 sentence summary of learnings.
    """
    entries_text = "\n".join(
        f"- [{e.entry_type}] {e.error or 'OK'}: {e.fix or 'N/A'} - {e.explanation}" for e in entries
    )

    prompt = f"<entries>\n{entries_text}\n</entries>"

    if existing_summary:
        prompt = f"<previous_summary>\n{existing_summary}\n</previous_summary>\n\n{prompt}"
        prompt += "\n\nIncorporate the previous summary with the new entries."

    result = await agent.run(prompt)
    return result.output
