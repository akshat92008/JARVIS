"""
Tool Registry — unifies all tool categories into a single dispatch system.
Combines Coding, Advanced Coding, Agent Factory, Desktop, Research, Documents, Communication,
App Builder, TDD Loop, AST Indexer, Vision, Vector Memory, Fleet, Browser, HUD, and Duplex Voice tools.
"""

from jarvis.tools.coding import CODING_TOOL_DEFINITIONS, CODING_DISPATCH
from jarvis.tools.advanced_coding import ADVANCED_CODING_TOOL_DEFINITIONS, ADVANCED_CODING_DISPATCH
from jarvis.tools.agent_factory import AGENT_FACTORY_TOOL_DEFINITIONS, AGENT_FACTORY_DISPATCH
from jarvis.tools.desktop import DESKTOP_TOOL_DEFINITIONS, DESKTOP_DISPATCH
from jarvis.tools.research import RESEARCH_TOOL_DEFINITIONS, RESEARCH_DISPATCH
from jarvis.tools.documents import DOCUMENT_TOOL_DEFINITIONS, DOCUMENT_DISPATCH
from jarvis.tools.communication import COMMUNICATION_TOOL_DEFINITIONS, COMMUNICATION_DISPATCH

# ── New Master Modules ────────────────────────────────────────────────────────
from jarvis.tools.app_builder import APP_BUILDER_TOOL_DEFINITIONS, APP_BUILDER_DISPATCH
from jarvis.tools.tdd_loop import TDD_TOOL_DEFINITIONS, TDD_DISPATCH
from jarvis.tools.ast_indexer import AST_TOOL_DEFINITIONS, AST_DISPATCH
from jarvis.tools.vision import VISION_TOOL_DEFINITIONS, VISION_DISPATCH
from jarvis.tools.vector_memory import VECTOR_MEMORY_TOOL_DEFINITIONS, VECTOR_MEMORY_DISPATCH
from jarvis.fleet import FLEET_TOOL_DEFINITIONS, FLEET_DISPATCH
from jarvis.tools.browser import BROWSER_TOOL_DEFINITIONS, BROWSER_DISPATCH
from jarvis.hud import HUD_TOOL_DEFINITIONS, HUD_DISPATCH
from jarvis.voice.duplex_voice import VOICE_TOOL_DEFINITIONS, VOICE_DISPATCH
from jarvis.tools.amaura import AMAURA_TOOL_DEFINITIONS, AMAURA_DISPATCH


# ── Combined Tool Definitions ──────────────────────────────────────────────────

ALL_TOOL_DEFINITIONS = (
    CODING_TOOL_DEFINITIONS
    + ADVANCED_CODING_TOOL_DEFINITIONS
    + AGENT_FACTORY_TOOL_DEFINITIONS
    + DESKTOP_TOOL_DEFINITIONS
    + RESEARCH_TOOL_DEFINITIONS
    + DOCUMENT_TOOL_DEFINITIONS
    + COMMUNICATION_TOOL_DEFINITIONS
    + APP_BUILDER_TOOL_DEFINITIONS
    + TDD_TOOL_DEFINITIONS
    + AST_TOOL_DEFINITIONS
    + VISION_TOOL_DEFINITIONS
    + VECTOR_MEMORY_TOOL_DEFINITIONS
    + FLEET_TOOL_DEFINITIONS
    + BROWSER_TOOL_DEFINITIONS
    + HUD_TOOL_DEFINITIONS
    + VOICE_TOOL_DEFINITIONS
    + AMAURA_TOOL_DEFINITIONS
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
    **APP_BUILDER_DISPATCH,
    **TDD_DISPATCH,
    **AST_DISPATCH,
    **VISION_DISPATCH,
    **VECTOR_MEMORY_DISPATCH,
    **FLEET_DISPATCH,
    **BROWSER_DISPATCH,
    **HUD_DISPATCH,
    **VOICE_DISPATCH,
    **AMAURA_DISPATCH,
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
        "app_builder": len(APP_BUILDER_TOOL_DEFINITIONS),
        "tdd_loop": len(TDD_TOOL_DEFINITIONS),
        "ast_indexer": len(AST_TOOL_DEFINITIONS),
        "vision": len(VISION_TOOL_DEFINITIONS),
        "vector_memory": len(VECTOR_MEMORY_TOOL_DEFINITIONS),
        "fleet": len(FLEET_TOOL_DEFINITIONS),
        "browser": len(BROWSER_TOOL_DEFINITIONS),
        "hud": len(HUD_TOOL_DEFINITIONS),
        "duplex_voice": len(VOICE_TOOL_DEFINITIONS),
        "amaura_company_os": len(AMAURA_TOOL_DEFINITIONS),
        "total": len(ALL_TOOL_DEFINITIONS),
    }
