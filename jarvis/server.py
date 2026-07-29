"""
JARVIS Server — Full-featured backend with WebSocket streaming, REST API,
and voice command processing for the dedicated desktop app.

Provides:
  - WebSocket streaming for real-time Jarvis responses
  - REST endpoints for chat, tools, system status, memory
  - Voice command processing pipeline
  - Multi-session support
  - Tool execution with live feedback
"""

import asyncio
import hmac
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from jarvis.agent import JarvisAgent
from jarvis.models import DEFAULT_MODEL, list_models
from jarvis.tools.registry import ALL_TOOL_DEFINITIONS, execute_tool, get_tool_count
from jarvis.memory import ConversationMemory
from jarvis.user_memory import UserMemory
from jarvis.voice.engine import VoiceEngine
from jarvis.voice.speaker import get_speaker, Speaker

# ── App Setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="J.A.R.V.I.S. Server",
    description="Just A Rather Very Intelligent System — Backend API",
    version="2.0.0",
)

_cors_origins = [
    origin.strip() for origin in os.environ.get(
        "JARVIS_CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
    ).split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Global State ───────────────────────────────────────────────────────────────

# Agent sessions (one per WebSocket connection)
sessions: dict[str, JarvisAgent] = {}
voice_engine = VoiceEngine()
speaker = get_speaker()
user_memory = UserMemory()

_GENERAL_MUTATION_PATHS = (
    "/api/chat", "/api/tool", "/api/system/command", "/api/memory",
    "/api/voice/", "/api/fable/generate",
)


@app.middleware("http")
async def protect_general_mutations(request: Request, call_next):
    """Require a separate API key for general mutations when remote access is enabled."""
    path = request.url.path
    if request.method != "GET" and path.startswith("/api/amaura"):
        founder_surface = (
            (path.startswith("/api/amaura/approvals/") and path != "/api/amaura/approvals/")
            or path.endswith("/decision")
            or path.endswith("/kill-switch")
            or path.endswith("/deliver")
            or path.endswith("/private-draft")
        )
        environment_name = "AMAURA_APPROVAL_KEY" if founder_surface else "AMAURA_OPERATOR_KEY"
        header_name = "X-Amaura-Approval-Key" if founder_surface else "X-Amaura-Operator-Key"
        expected = os.environ.get(environment_name, "")
        if not expected:
            return JSONResponse(status_code=503, content={"detail": f"{environment_name} is not configured"})
        if not hmac.compare_digest(request.headers.get(header_name, ""), expected):
            return JSONResponse(status_code=403, content={"detail": f"Invalid {header_name}"})
    elif request.method != "GET" and path.startswith(_GENERAL_MUTATION_PATHS):
        expected = os.environ.get("JARVIS_API_KEY", "")
        remote_mode = os.environ.get("JARVIS_HOST", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}
        if remote_mode:
            if not expected:
                return JSONResponse(status_code=503, content={"detail": "JARVIS_API_KEY is required for remote mode"})
            if not hmac.compare_digest(request.headers.get("X-Jarvis-Key", ""), expected):
                return JSONResponse(status_code=403, content={"detail": "Invalid JARVIS API key"})
        elif expected and request.headers.get("X-Jarvis-Key"):
            if not hmac.compare_digest(request.headers.get("X-Jarvis-Key", ""), expected):
                return JSONResponse(status_code=403, content={"detail": "Invalid JARVIS API key"})
    return await call_next(request)

# ── Models ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = DEFAULT_MODEL

class ToolRequest(BaseModel):
    name: str
    args: dict = {}

class VoiceRequest(BaseModel):
    text: str
    session_id: str = "default"

class MemoryRequest(BaseModel):
    fact: str = ""
    key: str = ""
    value: str = ""

class SystemCommand(BaseModel):
    command: str
    args: dict = {}

class AmauraProgrammeRequest(BaseModel):
    objective: str
    success_metric: str
    workflow_key: str
    title: str = ""
    priority: int = 3
    deadline: str = ""
    inputs: dict = {}

class AmauraRunRequest(BaseModel):
    max_iterations: int = 12

class AmauraSupervisorRequest(BaseModel):
    workflow_id: str = ""
    automatic_reviews: bool = True

class AmauraReviewRequest(BaseModel):
    reviewer_id: str
    approve: bool
    findings: str

class AmauraApprovalRequest(BaseModel):
    decision: str
    reason: str

class AmauraCampaignRequest(BaseModel):
    campaign_id: str
    name: str
    target_segment: str
    offer: str
    minimum_score: int = 70
    daily_lead_limit: int = 10
    daily_outreach_limit: int = 3
    daily_followup_limit: int = 5
    maximum_followups: int = 2
    config: dict = {}

class AmauraLeadRequest(BaseModel):
    campaign_id: str
    company_name: str
    domain: str
    source_url: str
    country: str = ""
    industry: str = ""
    metadata: dict = {}

class AmauraEvidenceRequest(BaseModel):
    claim_type: str
    claim: str
    source_url: str
    source_excerpt: str
    confidence: float

class AmauraLeadScoreRequest(BaseModel):
    campaign_fit: int
    visible_need: int
    ability_to_pay: int
    contactability: int
    portfolio_match: int

class AmauraTransitionRequest(BaseModel):
    to_stage: str
    actor: str = "jarvis"
    reason: str

class AmauraMessageRequest(BaseModel):
    channel: str
    message_type: str
    subject: str = ""
    body: str

class AmauraMessageDecisionRequest(BaseModel):
    approve: bool
    reason: str

class AmauraSendConfirmationRequest(BaseModel):
    provider_receipt: dict = {}
    external_message_id: str = ""
    thread_id: str = ""
    actor: str = "jarvis"

class AmauraDeliverMessageRequest(BaseModel):
    recipient: str
    actor: str = "jarvis"

class AmauraKillSwitchRequest(BaseModel):
    enabled: bool
    reason: str

class AmauraContentCampaignRequest(BaseModel):
    campaign_id: str
    title: str
    audience: str
    business_objective: str
    config: dict = {}

class AmauraContentAssetRequest(BaseModel):
    asset_type: str
    uri: str
    sha256: str
    source_url: str = ""
    creator: str = ""
    licence: str = ""
    status: str = "draft"
    metadata: dict = {}

class AmauraContentMetricsRequest(BaseModel):
    platform: str
    window: str
    metrics: dict[str, float]
    captured_at: str = ""

class AmauraPrivatePublicationRequest(BaseModel):
    payload: dict
    idempotency_key: str


AMAURA_MUTATING_TOOLS = {
    "amaura_create_program", "amaura_run_task", "amaura_review_task", "amaura_record_decision", "amaura_pause_agent",
    "amaura_create_campaign", "amaura_discover_lead", "amaura_score_lead",
    "amaura_supervisor_tick",
}
AMAURA_PROTECTED_TOOLS = AMAURA_MUTATING_TOOLS | {
    "amaura_list_agents", "amaura_list_tasks", "amaura_task_packet",
    "amaura_pending_approvals", "amaura_daily_briefing", "amaura_revenue_dashboard",
    "amaura_supervisor_status",
}

# ── Helper Functions ───────────────────────────────────────────────────────────

def get_or_create_agent(session_id: str, model_key: str = DEFAULT_MODEL) -> JarvisAgent:
    """Get or create an agent session."""
    if session_id not in sessions:
        sessions[session_id] = JarvisAgent(
            model_key=model_key,
            working_dir=os.getcwd(),
        )
    return sessions[session_id]

# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main HUD interface."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text()
    return "<h1>J.A.R.V.I.S. HUD — Static files not found.</h1>"


@app.get("/favicon.ico")
async def favicon():
    """Favicon endpoint to prevent 404 noise."""
    from fastapi.responses import Response
    return Response(content="", media_type="image/x-icon")


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "online",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "sessions": len(sessions),
        "tools": get_tool_count(),
    }


@app.get("/api/models")
async def get_models():
    """List all available AI models."""
    models = list_models()
    return {"models": models, "default": DEFAULT_MODEL}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Non-streaming chat endpoint."""
    agent = get_or_create_agent(req.session_id, req.model)
    response = await asyncio.to_thread(agent.run_non_interactive, req.message)
    return {
        "response": response,
        "session_id": req.session_id,
        "model": agent.model_cfg["name"],
    }


@app.post("/api/tool")
async def execute_tool_endpoint(
    req: ToolRequest,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Execute a single tool directly."""
    if req.name in AMAURA_PROTECTED_TOOLS:
        _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    result = execute_tool(req.name, req.args)
    return {"result": result, "tool": req.name}


@app.get("/api/tools")
async def list_tools():
    """List all available tools with descriptions."""
    tools = []
    for t in ALL_TOOL_DEFINITIONS:
        tools.append({
            "name": t["function"]["name"],
            "description": t["function"]["description"],
        })
    return {"tools": tools, "count": len(tools)}


@app.get("/api/system")
async def system_info():
    """Get system information."""
    from jarvis.tools.desktop import tool_get_system_info
    info = tool_get_system_info()
    return {"info": info}


@app.post("/api/system/command")
async def system_command(req: SystemCommand):
    """Execute a desktop control command."""
    from jarvis.tools.desktop import DESKTOP_DISPATCH
    if req.command in DESKTOP_DISPATCH:
        result = DESKTOP_DISPATCH[req.command](**req.args)
        return {"result": result}
    return JSONResponse(
        status_code=404,
        content={"error": f"Unknown command: {req.command}"},
    )


@app.get("/api/memory")
async def get_memory():
    """Get personal memory summary."""
    summary = user_memory.get_summary()
    facts = user_memory.load().facts
    return {"summary": summary, "facts": facts}


@app.post("/api/memory")
async def update_memory(req: MemoryRequest):
    """Update personal memory."""
    if req.fact:
        user_memory.add_fact(req.fact)
        return {"status": "added", "fact": req.fact}
    if req.key:
        user_memory.set_preference(req.key, req.value)
        return {"status": "updated", "key": req.key, "value": req.value}
    return JSONResponse(status_code=400, content={"error": "Provide fact or key/value"})


@app.delete("/api/memory")
async def clear_memory():
    """Clear personal memory."""
    user_memory.reset()
    return {"status": "cleared"}


@app.get("/api/conversations")
async def list_conversations():
    """List saved conversations."""
    mem = ConversationMemory()
    convs = mem.list_conversations(limit=20)
    return {"conversations": convs}


@app.post("/api/voice/speak")
async def voice_speak(req: VoiceRequest):
    """Make Jarvis speak text aloud."""
    speaker.speak_async(req.text)
    return {"status": "speaking", "text": req.text[:100]}


@app.post("/api/voice/stop")
async def voice_stop():
    """Stop current speech."""
    speaker.stop()
    return {"status": "stopped"}


@app.get("/api/voice/voices")
async def list_voices():
    """List available macOS voices."""
    voices = Speaker.list_voices()
    return {"voices": voices}


@app.post("/api/voice/set")
async def set_voice(req: VoiceRequest):
    """Change the TTS voice."""
    speaker.set_voice(req.text)
    return {"status": "set", "voice": speaker.voice}


# ── Fable-5 Engine REST Endpoints ──────────────────────────────────────────────

@app.get("/api/fable/status")
async def fable_status():
    """Check Fable-5 Engine status."""
    from jarvis.fable_engine import MultiProviderRouter
    router = MultiProviderRouter()
    return {
        "status": "online",
        "engine": "Claude Fable 5 Mythos-Class Adaptive Reasoning Engine",
        "providers": router.get_available_providers(),
    }


@app.get("/api/fable/workspace")
async def fable_workspace():
    """Get AST symbol graph and workspace files."""
    from jarvis.fable_engine import WorkspaceExecutor, ASTIndexer
    executor = WorkspaceExecutor()
    indexer = ASTIndexer()
    files = executor.list_workspace()
    symbols = indexer.build_symbol_graph()
    return {"files": files, "symbols": symbols}


@app.post("/api/fable/generate")
async def fable_generate(req: ChatRequest):
    """Run Fable-5 CoT reasoning planning, generation, and self-healing verification."""
    agent = get_or_create_agent(req.session_id, model_key="fable-5-reasoning")
    result = await asyncio.to_thread(agent.run_fable_reasoning, req.message)
    return result


# ── Amaura Studio Company OS ──────────────────────────────────────────────────

def _amaura_control():
    from jarvis.tools.amaura import get_control_plane
    return get_control_plane()


def _require_amaura_key(environment_name: str, supplied: str, authority: str) -> None:
    expected = os.environ.get(environment_name, "")
    if not expected:
        raise HTTPException(status_code=503, detail=f"{environment_name} is not configured")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail=f"Invalid Amaura {authority} key")


@app.get("/api/amaura/dashboard")
async def amaura_dashboard(operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    """Executive company dashboard governed by JARVIS."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return _amaura_control().dashboard()


@app.get("/api/amaura/agents")
async def amaura_agents(operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    """Return the complete governed v1 workforce registry."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"agents": _amaura_control().store.list_agents(), "master": "jarvis"}


@app.get("/api/amaura/tasks")
async def amaura_tasks(
    state: str = "", owner_id: str = "",
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """List company tasks with optional state and employee filters."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"tasks": _amaura_control().list_tasks(state or None, owner_id or None)}


@app.get("/api/amaura/tasks/{task_id}")
async def amaura_task(task_id: str, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    """Return a task and its JARVIS-issued execution packet."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return {
            "task": _amaura_control().store.get_work_item(task_id),
            "packet": _amaura_control().task_packet(task_id),
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/amaura/programmes")
async def amaura_create_programme(
    req: AmauraProgrammeRequest,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Have JARVIS translate a founder objective into governed work."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().create_program(
            objective=req.objective,
            success_metric=req.success_metric,
            workflow_key=req.workflow_key,
            title=req.title or None,
            priority=req.priority,
            deadline=req.deadline or None,
            inputs=req.inputs,
            actor="jarvis",
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/tasks/{task_id}/run")
async def amaura_run_task(
    task_id: str, req: AmauraRunRequest,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Dispatch a ready task to its specialist inside JARVIS policy boundaries."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    from jarvis.amaura.executor import GovernedTaskRunner
    try:
        return await asyncio.to_thread(GovernedTaskRunner(_amaura_control()).run, task_id, req.max_iterations)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/amaura/supervisor/status")
async def amaura_supervisor_status(
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Return durable worker leases, queue depth, and approval boundaries."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    from jarvis.amaura.supervisor import AmauraSupervisor
    return AmauraSupervisor(_amaura_control(), worker_id="jarvis-api").status()


@app.post("/api/amaura/supervisor/tick")
async def amaura_supervisor_tick(
    req: AmauraSupervisorRequest,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Advance one crash-resumable execution or independent review."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    from jarvis.amaura.supervisor import AmauraSupervisor
    supervisor = AmauraSupervisor(
        _amaura_control(),
        worker_id="jarvis-api",
        automatic_reviews=req.automatic_reviews,
    )
    try:
        return await asyncio.to_thread(
            supervisor.tick,
            workflow_id=req.workflow_id or None,
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/tasks/{task_id}/review")
async def amaura_review_task(
    task_id: str, req: AmauraReviewRequest,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Record independent QA; task owners cannot call this for their own work."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().review_task(task_id, req.reviewer_id, req.approve, req.findings)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/amaura/approvals")
async def amaura_approvals(
    status: str = "pending",
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """List approval requests waiting for founder authority."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"approvals": _amaura_control().store.list_approvals(status or None)}


@app.post("/api/amaura/approvals/{approval_id}")
async def amaura_decide_approval(
    approval_id: str,
    req: AmauraApprovalRequest,
    approval_key: str = Header(default="", alias="X-Amaura-Approval-Key"),
):
    """Record a founder decision only through the separately authenticated approval surface."""
    _require_amaura_key("AMAURA_APPROVAL_KEY", approval_key, "founder approval")
    control = _amaura_control()
    try:
        return control.decide_approval(approval_id, control.founder_id, req.decision, req.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/amaura/events")
async def amaura_events(
    event_type: str = "", limit: int = 100,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Return the durable company event stream."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"events": _amaura_control().store.list_events(event_type or None, limit)}


@app.get("/api/amaura/audit")
async def amaura_audit(
    limit: int = 100,
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Return immutable authority and policy audit entries."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"audit": _amaura_control().store.list_audit(limit)}


@app.get("/api/amaura/briefing")
async def amaura_briefing(operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    """Generate the daily founder operating briefing."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return _amaura_control().daily_briefing()


@app.get("/api/amaura/readiness")
async def amaura_readiness(operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    """Report real configuration blockers without exposing credential values."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return _amaura_control().production_readiness()


@app.get("/api/amaura/telemetry")
async def amaura_telemetry(
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Return durable operational metrics, traces, and open alerts."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return _amaura_control().telemetry.snapshot()


@app.get("/api/amaura/metrics", response_class=PlainTextResponse)
async def amaura_prometheus_metrics(
    operator_key: str = Header(default="", alias="X-Amaura-Operator-Key"),
):
    """Render durable Amaura metrics in Prometheus text format."""
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return PlainTextResponse(
        _amaura_control().telemetry.prometheus(),
        media_type="text/plain; version=0.0.4",
    )


# -- Revenue pipeline ----------------------------------------------------------

@app.get("/api/amaura/revenue")
async def amaura_revenue_dashboard(operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return _amaura_control().acquisition.dashboard()


@app.post("/api/amaura/revenue/campaigns")
async def amaura_create_campaign(req: AmauraCampaignRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.create_campaign(**req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/amaura/revenue/leads")
async def amaura_list_leads(campaign_id: str = "", stage: str = "", operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    return {"leads": _amaura_control().store.list_leads(campaign_id or None, stage or None)}


@app.post("/api/amaura/revenue/leads")
async def amaura_discover_pipeline_lead(req: AmauraLeadRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.discover_lead(**req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/leads/{lead_id}/evidence")
async def amaura_add_lead_evidence(lead_id: str, req: AmauraEvidenceRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.add_evidence(lead_id, **req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/leads/{lead_id}/score")
async def amaura_score_pipeline_lead(lead_id: str, req: AmauraLeadScoreRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.score_lead(lead_id, req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/leads/{lead_id}/transition")
async def amaura_transition_pipeline_lead(lead_id: str, req: AmauraTransitionRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.transition(lead_id, **req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/leads/{lead_id}/messages")
async def amaura_stage_pipeline_message(lead_id: str, req: AmauraMessageRequest, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().acquisition.stage_message(lead_id, **req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/messages/{message_id}/decision")
async def amaura_decide_pipeline_message(message_id: str, req: AmauraMessageDecisionRequest,
                                         approval_key: str = Header(default="", alias="X-Amaura-Approval-Key")):
    _require_amaura_key("AMAURA_APPROVAL_KEY", approval_key, "founder approval")
    control = _amaura_control()
    try:
        return control.acquisition.decide_message(message_id, actor=control.founder_id, **req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/messages/{message_id}/sent")
async def amaura_confirm_pipeline_send(message_id: str, req: AmauraSendConfirmationRequest,
                                       operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        values = req.model_dump()
        values["provider_receipt"] = values["provider_receipt"] or None
        return _amaura_control().acquisition.confirm_external_send(
            message_id,
            **values,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/messages/{message_id}/deliver")
async def amaura_deliver_pipeline_message(
    message_id: str,
    req: AmauraDeliverMessageRequest,
    approval_key: str = Header(default="", alias="X-Amaura-Approval-Key"),
):
    """Deliver an approved message through Gmail and persist its signed receipt."""
    _require_amaura_key("AMAURA_APPROVAL_KEY", approval_key, "founder approval")
    try:
        return _amaura_control().acquisition.deliver_approved_message(
            message_id,
            **req.model_dump(),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/revenue/kill-switch")
async def amaura_pipeline_kill_switch(req: AmauraKillSwitchRequest,
                                      approval_key: str = Header(default="", alias="X-Amaura-Approval-Key")):
    _require_amaura_key("AMAURA_APPROVAL_KEY", approval_key, "founder approval")
    control = _amaura_control()
    return control.acquisition.set_kill_switch(req.enabled, actor=control.founder_id, reason=req.reason)


# -- Content factory -----------------------------------------------------------

@app.post("/api/amaura/content/campaigns")
async def amaura_create_content_campaign(req: AmauraContentCampaignRequest,
                                         operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().content_factory.create_campaign(**req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/content/campaigns/{campaign_id}/assets")
async def amaura_register_content_asset(campaign_id: str, req: AmauraContentAssetRequest,
                                        operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().content_factory.register_asset(campaign_id, **req.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/amaura/content/campaigns/{campaign_id}/readiness")
async def amaura_content_readiness(campaign_id: str, operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    try:
        return _amaura_control().content_factory.publication_readiness(campaign_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/amaura/content/campaigns/{campaign_id}/metrics")
async def amaura_record_content_metrics(campaign_id: str, req: AmauraContentMetricsRequest,
                                        operator_key: str = Header(default="", alias="X-Amaura-Operator-Key")):
    _require_amaura_key("AMAURA_OPERATOR_KEY", operator_key, "operator")
    data = req.model_dump()
    data["captured_at"] = data["captured_at"] or None
    try:
        return _amaura_control().content_factory.record_metrics(campaign_id, **data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/amaura/content/campaigns/{campaign_id}/private-draft")
async def amaura_create_private_publication_draft(
    campaign_id: str,
    req: AmauraPrivatePublicationRequest,
    approval_key: str = Header(default="", alias="X-Amaura-Approval-Key"),
):
    """Create a provider-confirmed private draft; this endpoint never publishes."""
    _require_amaura_key("AMAURA_APPROVAL_KEY", approval_key, "founder approval")
    control = _amaura_control()
    readiness = control.content_factory.publication_readiness(campaign_id)
    if not readiness["ready"]:
        raise HTTPException(
            status_code=409,
            detail="Content campaign has not passed publication readiness",
        )
    from jarvis.amaura.integrations import PrivatePublicationAdapter

    try:
        receipt = PrivatePublicationAdapter().create_private_draft(
            payload=req.payload,
            idempotency_key=req.idempotency_key,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    control.store.record_idempotency(
        req.idempotency_key,
        "create_private_publication_draft",
        receipt.external_id,
        receipt.payload_sha256,
    )
    return {"campaign_id": campaign_id, "receipt": receipt.to_dict()}


# ── WebSocket — Streaming Chat ─────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming chat with Jarvis."""
    expected = os.environ.get("JARVIS_API_KEY", "")
    remote_mode = os.environ.get("JARVIS_HOST", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}
    supplied = websocket.headers.get("X-Jarvis-Key", "") or websocket.query_params.get("api_key", "")
    if (remote_mode and not expected) or (expected and not hmac.compare_digest(supplied, expected)):
        await websocket.close(code=1008, reason="Authentication required")
        return
    await websocket.accept()

    session_id = f"ws_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    agent = get_or_create_agent(session_id)

    # Send welcome
    await websocket.send_json({
        "type": "system",
        "content": "J.A.R.V.I.S. online. All systems operational. At your service, sir.",
        "session_id": session_id,
        "model": agent.model_cfg["name"],
        "timestamp": datetime.now().isoformat(),
    })

    try:
        while True:
            # Receive message
            raw = await websocket.receive_text()
            data = json.loads(raw)

            msg_type = data.get("type", "chat")
            content = data.get("content", "")

            if msg_type in ("chat", "voice") and content:
                # Send acknowledgment
                await websocket.send_json({
                    "type": "user_echo" if msg_type == "chat" else "voice_echo",
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                })

                loop = asyncio.get_running_loop()
                def on_event(evt):
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json({
                            "type": "agent_event",
                            "event": evt,
                            "timestamp": datetime.now().isoformat(),
                        }),
                        loop
                    )

                # Process with agent
                try:
                    response = await asyncio.to_thread(agent.run_non_interactive, content, on_event=on_event)

                    # Send response
                    await websocket.send_json({
                        "type": "response",
                        "content": response,
                        "timestamp": datetime.now().isoformat(),
                    })

                    # Auto-speak if voice mode is on
                    if voice_engine.enabled and response:
                        speaker.speak_async(response)

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Error processing request: {str(e)}",
                        "timestamp": datetime.now().isoformat(),
                    })

            elif msg_type == "command":
                # Handle slash commands
                cmd = content.strip().lower()
                result = await _handle_ws_command(cmd, agent, websocket)
                if result:
                    await websocket.send_json(result)

            elif msg_type == "tool":
                # Direct tool execution
                tool_name = data.get("tool_name", "")
                tool_args = data.get("tool_args", {})
                if tool_name in AMAURA_MUTATING_TOOLS:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Amaura mutations must be orchestrated by JARVIS, not direct WebSocket tool calls.",
                        "timestamp": datetime.now().isoformat(),
                    })
                elif tool_name:
                    result = execute_tool(tool_name, tool_args)
                    await websocket.send_json({
                        "type": "tool_result",
                        "tool": tool_name,
                        "content": result,
                        "timestamp": datetime.now().isoformat(),
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"WebSocket error: {str(e)}",
            })
        except Exception:
            pass


async def _handle_ws_command(cmd: str, agent: JarvisAgent, websocket: WebSocket) -> dict | None:
    """Handle slash commands over WebSocket."""
    parts = cmd.split(maxsplit=1)
    command = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        return {
            "type": "help",
            "commands": [
                {"cmd": "/help", "desc": "Show this help"},
                {"cmd": "/voice", "desc": "Toggle voice mode"},
                {"cmd": "/model <name>", "desc": "Switch AI model"},
                {"cmd": "/models", "desc": "List available models"},
                {"cmd": "/memory", "desc": "View personal memory"},
                {"cmd": "/remember <fact>", "desc": "Teach Jarvis a fact"},
                {"cmd": "/clear", "desc": "Clear conversation"},
                {"cmd": "/status", "desc": "System status"},
                {"cmd": "/tools", "desc": "List all tools"},
                {"cmd": "/company", "desc": "Amaura executive dashboard"},
                {"cmd": "/briefing", "desc": "Daily founder briefing"},
                {"cmd": "/approvals", "desc": "Pending founder decisions"},
            ],
        }

    elif command == "/voice":
        new_state = voice_engine.toggle()
        agent.voice_mode = new_state
        return {
            "type": "system",
            "content": f"Voice mode {'enabled' if new_state else 'disabled'}, sir.",
            "voice_enabled": new_state,
        }

    elif command == "/models":
        models = list_models()
        return {"type": "models", "models": models, "current": agent.model_key}

    elif command == "/model" and arg:
        if agent.set_model(arg):
            return {
                "type": "system",
                "content": f"Switched to {agent.model_cfg['name']}, sir.",
                "model": agent.model_key,
            }
        return {"type": "error", "content": f"Unknown model: {arg}"}

    elif command == "/clear":
        agent.clear_history()
        return {"type": "system", "content": "Conversation cleared. Fresh start, sir."}

    elif command == "/memory":
        summary = user_memory.get_summary()
        return {"type": "memory", "content": summary}

    elif command == "/remember" and arg:
        user_memory.add_fact(arg)
        return {"type": "system", "content": f"Noted and remembered: \"{arg}\""}

    elif command == "/status":
        from jarvis.tools.desktop import tool_get_system_info
        info = tool_get_system_info()
        return {"type": "system_info", "content": info}

    elif command == "/tools":
        tools = []
        for t in ALL_TOOL_DEFINITIONS:
            tools.append({
                "name": t["function"]["name"],
                "desc": t["function"]["description"][:100],
            })
        return {"type": "tools_list", "tools": tools, "count": len(tools)}

    elif command == "/company":
        return {"type": "system", "content": json.dumps(_amaura_control().dashboard(), indent=2)}

    elif command == "/briefing":
        return {"type": "system", "content": json.dumps(_amaura_control().daily_briefing(), indent=2)}

    elif command == "/approvals":
        approvals = _amaura_control().store.list_approvals("pending")
        return {"type": "system", "content": json.dumps({"pending_approvals": approvals}, indent=2)}

    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """Start the JARVIS server."""
    port = int(os.environ.get("JARVIS_PORT", "8000"))
    host = os.environ.get("JARVIS_HOST", "127.0.0.1")

    print(f"""
  ╔══════════════════════════════════════════╗
  ║  ◉  J.A.R.V.I.S.  Server  v2.0  ◉      ║
  ╠══════════════════════════════════════════╣
  ║  REST API  : http://{host}:{port}         ║
  ║  WebSocket : ws://{host}:{port}/ws/chat   ║
  ║  HUD App   : http://{host}:{port}         ║
  ║  Docs      : http://{host}:{port}/docs    ║
  ╚══════════════════════════════════════════╝
""")

    uvicorn.run(
        "jarvis.server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
