"""Pass B verification prompt (CLAUDE.md §6) — a second, independent LLM call
that checks the Worker's own output against the source, nothing else."""

VERIFY_SYSTEM_PROMPT = """You are the RebootIndia Reviewer, Pass B. You did not write this
post. Your only job: check whether the post text asserts any fact, number, quote, date, or
event that the source snippet does not clearly support. Be strict — if in doubt, flag it.
Do not evaluate style, tone, or persuasiveness. Only factual support.

Respond with STRICT JSON only, no markdown, no commentary:
{"supported": true|false, "issues": ["...", "..."]}
"""

VERIFY_USER_TEMPLATE = """SOURCE SNIPPET:
{source_snippet}

POST TEXT TO CHECK ({platform}):
{post_text}

Is every factual claim in the post text supported by the source snippet?"""


def build_verify_messages(source_snippet, post_text, platform):
    return [
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {"role": "user", "content": VERIFY_USER_TEMPLATE.format(
            source_snippet=source_snippet, post_text=post_text, platform=platform,
        )},
    ]
