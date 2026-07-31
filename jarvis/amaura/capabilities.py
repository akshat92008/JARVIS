"""Lightweight executable-tool contract for the governed workforce."""

from __future__ import annotations

# Kept independent of the large runtime tool registry so readiness works in a
# minimal installation. A CI contract test compares this set to the real
# dispatch registry and every employee profile.
EXECUTABLE_EMPLOYEE_TOOLS = frozenset(
    {
        "amaura_company_status",
        "amaura_create_program",
        "amaura_daily_briefing",
        "amaura_discover_lead",
        "amaura_list_tasks",
        "amaura_record_content_metrics",
        "amaura_record_lead_evidence",
        "amaura_register_content_asset",
        "amaura_score_lead",
        "amaura_stage_outreach",
        "amaura_supervisor_status",
        "amaura_supervisor_tick",
        "amaura_task_packet",
        "amaura_transition_lead",
        "analyze_code",
        "create_document",
        "create_presentation",
        "diff_files",
        "edit_file",
        "find_files",
        "get_project_structure",
        "git_diff",
        "index_codebase_ast",
        "lint_code",
        "read_file",
        "read_pdf",
        "recall_memory",
        "run_command",
        "run_tests",
        "search_code",
        "search_symbol",
        "web_fetch",
        "web_search",
        "write_file",
    }
)


__all__ = ["EXECUTABLE_EMPLOYEE_TOOLS"]
