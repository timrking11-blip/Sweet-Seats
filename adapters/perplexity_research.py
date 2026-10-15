"""Perplexity Agent API adapter for web research."""
from __future__ import annotations

import asyncio
from typing import Callable

INSTRUCTIONS = (
    "Perform web research. Prefer primary and authoritative sources. Include inline "
    "citations and a source list. Clearly separate facts from interpretation."
)

# Label -> preset routing. "research-quick" is the simple automated flow; "research" is deep.
LABEL_PRESETS = {"research-quick": "low", "research": "medium"}


def preset_for_labels(labels: list[str]) -> str | None:
    # Deep research wins when both labels are present.
    for label in ("research", "research-quick"):
        if label in labels:
            return LABEL_PRESETS[label]
    return None


def build_prompt(issue: dict) -> str:
    labels = ", ".join(l["name"] for l in issue["labels"]["nodes"]) or "none"
    return (
        f"Linear issue: {issue['identifier']} - {issue['title']}\nLabels: {labels}\n\n"
        f"Issue description:\n{issue.get('description') or 'No additional description provided.'}\n\n"
        "Return: 1. Executive summary 2. Key findings 3. Options 4. Risks and unknowns "
        "5. Recommended next actions 6. Sources"
    )


async def run_research(prompt: str, preset: str, client_factory: Callable | None = None) -> str:
    if client_factory is None:
        from perplexity import Perplexity  # imported lazily so tests need no API key
        client_factory = Perplexity
    client = client_factory()
    # SDK call is synchronous; keep the event loop free.
    response = await asyncio.to_thread(
        client.responses.create, preset=preset, input=prompt, instructions=INSTRUCTIONS
    )
    return response.output_text
