"""Versioned system-prompt catalogue for the Amaura workforce."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "2026.07.27"
_SOURCE = Path(__file__).with_name("revenue_workforce.md")
_HEADING_TO_KEY = {
    "Amaura Chief Revenue Officer Agent": "chief_revenue_officer",
    "Free Lead Discovery and Outreach Agent": "lead_discovery_outreach",
    "Aggressive Sales Closer Agent": "sales_closer",
    "Amaura Marketing and Demand-Generation Agent": "marketing_demand_generation",
    "Master Revenue Workforce Orchestrator": "revenue_orchestrator",
}


@lru_cache(maxsize=1)
def load_prompt_catalogue() -> dict[str, str]:
    """Load the founder-approved fenced prompts from the packaged source document."""
    if not _SOURCE.exists():
        return {}
    text = _SOURCE.read_text(encoding="utf-8")
    headings = list(re.finditer(r"^#\s+(?:\d+\.\s+)?(.+?)\s*$", text, re.MULTILINE))
    catalogue: dict[str, str] = {}
    for index, heading in enumerate(headings):
        title = heading.group(1).strip()
        key = _HEADING_TO_KEY.get(title)
        if not key:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end():end]
        fenced = re.search(r"```text\s*\n(.*?)\n```", section, re.DOTALL)
        if fenced:
            catalogue[key] = fenced.group(1).strip()
    return catalogue


def get_system_prompt(key: str, fallback: str) -> str:
    """Return a versioned founder prompt, or a safe role fallback."""
    return load_prompt_catalogue().get(key, fallback)


__all__ = ["PROMPT_VERSION", "get_system_prompt", "load_prompt_catalogue"]
