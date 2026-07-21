"""
Tool Registry — unifies all tool categories into a single dispatch system.
Combines: Coding (14) + Advanced Coding (16) + Agent Factory (8) + Desktop (12) + Research (4) + Documents (3) + Communication (4) = 61 tools.
"""

from jarvis.tools.coding import CODING_TOOL_DEFINITIONS, CODING_DISPATCH
from jarvis.tools.advanced_coding import ADVANCED_CODING_TOOL_DEFINITIONS, ADVANCED_CODING_DISPATCH
from jarvis.tools.agent_factory import AGENT_FACTORY_TOOL_DEFINITIONS, AGENT_FACTORY_DISPATCH
from jarvis.tools.desktop import DESKTOP_TOOL_DEFINITIONS, DESKTOP_DISPATCH
from jarvis.tools.research import RESEARCH_TOOL_DEFINITIONS, RESEARCH_DISPATCH
from jarvis.tools.documents import DOCUMENT_TOOL_DEFINITIONS, DOCUMENT_DISPATCH
from jarvis.tools.communication import COMMUNICATION_TOOL_DEFINITIONS, COMMUNICATION_DISPATCH


# ── Combined Tool Definitions (for OpenAI function calling) ──────────────────

ALL_TOOL_DEFINITIONS = (
    CODING_TOOL_DEFINITIONS
    + ADVANCED_CODING_TOOL_DEFINITIONS
    + AGENT_FACTORY_TOOL_DEFINITIONS
    + DESKTOP_TOOL_DEFINITIONS
    + RESEARCH_TOOL_DEFINITIONS
    + DOCUMENT_TOOL_DEFINITIONS
    + COMMUNICATION_TOOL_DEFINITIONS
)


# ── Combined Dispatch ────────────────────────────────────────────────────────

ALL_DISPATCH = {
    **CODING_DISPATCH,
    **ADVANCED_CODING_DISPATCH,
    **AGENT_FACTORY_DISPATCH,
    **DESKTOP_DISPATCH,
    **RESEARCH_DISPATCH,
    **DOCUMENT_DISPATCH,
    **COMMUNICATION_DISPATCH,
}


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool by name with the given arguments."""
    if name in ALL_DISPATCH:
        try:
            return ALL_DISPATCH[name](**args)
        except Exception as e:
            return f"❌ Tool error ({name}): {e}"
    return f"❌ Unknown tool: {name}"


def get_tool_count() -> dict:
    """Return tool counts by category."""
    return {
        "coding": len(CODING_TOOL_DEFINITIONS),
        "advanced_coding": len(ADVANCED_CODING_TOOL_DEFINITIONS),
        "agent_factory": len(AGENT_FACTORY_TOOL_DEFINITIONS),
        "desktop": len(DESKTOP_TOOL_DEFINITIONS),
        "research": len(RESEARCH_TOOL_DEFINITIONS),
        "documents": len(DOCUMENT_TOOL_DEFINITIONS),
        "communication": len(COMMUNICATION_TOOL_DEFINITIONS),
        "total": len(ALL_TOOL_DEFINITIONS),
    }
