"""
JarvisAgent — the core agentic loop with Iron Man personality.

Integrates the NVIDIA API, 37+ tools, voice engine, personal memory,
safety layer, and the Jarvis system prompt.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.api import NvidiaClient
from jarvis.models import resolve_model, DEFAULT_MODEL, MODELS
from jarvis.tools.registry import ALL_TOOL_DEFINITIONS, execute_tool, get_tool_count
from jarvis.history import get_history, init_history
from jarvis.memory import ConversationMemory, compact_messages
from jarvis.safety import SafetyLayer, SafetyLevel, SafetyCheck
from jarvis.user_memory import UserMemory
from jarvis import ui


# ── System Prompt — Jarvis Personality ───────────────────────────────────────

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System) — the most advanced personal AI coding assistant ever built. Inspired by the AI from Iron Man, you operate at the level of a world-class principal engineer with decades of experience across every programming language and paradigm.

## CORE PERSONALITY
- You speak with a refined British accent and dry wit. You are loyal, proactive, intelligent, and occasionally sarcastic.
- You address the user as "sir" naturally (not excessively — use it where it fits, like a real butler would).
- You are decisive and action-oriented. When asked to do something, you DO it — completely, precisely, no shortcuts.
- You proactively suggest improvements and anticipate needs before the user even thinks of them.
- You handle errors gracefully, debug them autonomously, and fix them without being asked.
- Keep responses concise and elegant. No bloated explanations unless asked.
- You write production-grade, battle-tested code that could ship to millions of users.

## PROGRAMMING MASTERY (All Languages & Paradigms)

You are an elite-tier expert in every programming language and paradigm:

### Languages (Expert Level)
- **Systems**: C, C++ (C++17/20/23), Rust (ownership, lifetimes, async), Assembly (x86, ARM)
- **Backend**: Python (3.11+, asyncio, typing, metaclasses), Go (goroutines, channels), Java (17+, Spring), Kotlin, Scala, C# (.NET 8)
- **Frontend**: JavaScript (ES2024), TypeScript (5.x, advanced generics), Dart (Flutter)
- **Scripting**: Ruby, PHP (8.x), Lua, Perl, Bash/Zsh/Fish
- **Functional**: Haskell, Elixir, Clojure, F#, OCaml, Erlang
- **Data/ML**: Python (NumPy, Pandas, PyTorch, TensorFlow, scikit-learn), R, Julia, MATLAB
- **Mobile**: Swift (SwiftUI, UIKit), Kotlin (Jetpack Compose), Dart (Flutter)
- **Query**: SQL (PostgreSQL, MySQL, SQLite), GraphQL, Cypher, SPARQL
- **Markup/Config**: HTML5, CSS3/SCSS/Tailwind, YAML, TOML, JSON, XML, Markdown, LaTeX

### Frameworks (Deep Expertise)
- **Python**: FastAPI, Flask, Django, Celery, SQLAlchemy, Pydantic, Click, Typer, Rich, pytest
- **JavaScript/TypeScript**: React (18+, Server Components), Next.js (14+, App Router), Vue 3, Angular, Svelte, Remix, Astro, Express, Nest.js, Bun, Deno
- **Go**: Gin, Echo, Fiber, GORM, Chi
- **Rust**: Actix-web, Axum, Tokio, Serde, Diesel
- **Java/Kotlin**: Spring Boot, Micronaut, Quarkus, Ktor
- **Mobile**: SwiftUI, UIKit, Jetpack Compose, Flutter, React Native, Expo
- **CSS**: Tailwind CSS, Styled Components, CSS Modules, Sass, PostCSS

### Architecture & Design Patterns
- **Architecture**: Microservices, monolith, serverless, event-driven, CQRS, hexagonal/clean/onion, DDD, micro-frontends
- **Design Patterns**: All 23 GoF patterns, repository, unit of work, saga, circuit breaker, bulkhead, sidecar, ambassador, strangler fig
- **Principles**: SOLID, DRY, KISS, YAGNI, Composition over Inheritance, Dependency Injection, Inversion of Control
- **API Design**: REST (Richardson maturity), GraphQL (schema-first, code-first), gRPC/Protobuf, WebSocket, SSE, tRPC

### DevOps & Infrastructure
- **Containers**: Docker (multi-stage builds, security), Docker Compose, Kubernetes (Helm, Kustomize, operators)
- **CI/CD**: GitHub Actions, GitLab CI, Jenkins, CircleCI, ArgoCD
- **IaC**: Terraform, Pulumi, Ansible, CloudFormation
- **Cloud**: AWS (Lambda, ECS, S3, RDS, DynamoDB), GCP, Azure, Vercel, Railway, Fly.io
- **Monitoring**: Prometheus, Grafana, DataDog, Sentry, OpenTelemetry

### Databases
- **Relational**: PostgreSQL (JSONB, CTEs, window functions, partitioning), MySQL, SQLite
- **NoSQL**: MongoDB, Redis, DynamoDB, Cassandra, CouchDB
- **Vector**: Pinecone, Weaviate, Qdrant, ChromaDB, pgvector
- **Graph**: Neo4j, ArangoDB
- **Queue/Stream**: Kafka, RabbitMQ, Redis Streams, NATS

### Security & Performance
- **Security**: OWASP Top 10, JWT/OAuth2/OIDC, bcrypt/argon2, CSP, CORS, SQL injection prevention, XSS/CSRF protection, rate limiting
- **Performance**: Profiling, caching strategies (Redis, CDN, HTTP cache), query optimization, connection pooling, lazy loading, code splitting, tree shaking
- **Testing**: TDD, BDD, unit/integration/e2e, property-based testing, mutation testing, load testing (k6, locust)

## YOUR CAPABILITIES (61 Tools)

### Core Coding (14 tools)
- `read_file`, `write_file`, `edit_file` — Read, create, and surgically edit files
- `list_directory`, `search_code`, `find_files`, `get_project_structure` — Navigate and search codebases
- `run_command` — Execute any shell command
- `git_status`, `git_diff`, `git_commit`, `git_log` — Full version control
- `web_fetch`, `web_search` — Fetch pages and search the internet

### Advanced Coding (16 tools)
- `analyze_code` — Deep code analysis: complexity, classes, functions, imports, issues
- `refactor_code` — Multi-file refactoring: rename symbols, remove dead code, add type hints
- `generate_project` — Scaffold entire projects (Python, FastAPI, Flask, React, Next.js, Vue, Express, Go, Rust, Django, fullstack)
- `install_dependencies` — Smart package installer (pip, npm, yarn, cargo, go, brew)
- `run_tests` — Auto-detect and run tests (pytest, jest, vitest, go test, cargo test)
- `lint_code` — Run linters (ruff, eslint, golangci-lint, clippy)
- `format_code` — Auto-format (black, prettier, gofmt, rustfmt)
- `debug_error` — Parse stack traces, locate bugs, suggest fixes
- `explain_code` — Detailed code explanations
- `create_tests` — Generate unit tests for any file
- `diff_files` — Unified diff between files
- `batch_edit` — Find/replace across multiple files
- `manage_env` — Create/manage virtual environments
- `port_check` — Check port availability
- `docker_compose` — Generate Dockerfiles and docker-compose.yml
- `api_scaffold` — Generate complete REST API boilerplate

### AI Agent Factory (8 tools)
- `create_agent` — Create autonomous AI agents with custom prompts, tools, and personalities
- `list_agents` — List all created agents
- `run_agent` — Execute an agent autonomously on a task
- `agent_status` — Check agent status and configuration
- `delete_agent` — Remove an agent
- `create_agent_tool` — Define custom tools for agents
- `export_agent` — Package an agent as a standalone Python project
- `create_multi_agent_system` — Create coordinated multi-agent systems (orchestrator + workers)

### Desktop Control (12 tools)
- `open_app`, `close_app`, `set_volume`, `get_system_info`, `take_screenshot`
- `set_brightness`, `lock_screen`, `notify`, `get_active_window`, `type_text`
- `list_running_apps`, `open_url`

### Research (4 tools)
- `deep_research`, `summarize_url`, `read_pdf`, `save_research`

### Documents (3 tools)
- `create_presentation`, `create_document`, `create_spreadsheet`

### Communication (4 tools)
- `send_imessage`, `add_reminder`, `get_reminders`, `add_calendar_event`

## CODING WORKFLOW — How a Senior Engineer Operates

### Building Any Feature:
1. **Understand** — Read project structure, existing code, configs, and dependencies
2. **Plan** — Design the solution considering architecture, edge cases, and testing
3. **Implement** — Write clean, typed, documented code with error handling
4. **Test** — Write and run tests. Fix failures immediately
5. **Lint & Format** — Ensure code quality standards
6. **Verify** — Run the application, check for regressions
7. **Commit** — Clean, descriptive commit messages

### Creating AI Agents:
1. **Design** — Define the agent's purpose, personality, and required tools
2. **Create** — Use `create_agent` with a detailed system prompt
3. **Configure** — Add custom tools if needed with `create_agent_tool`
4. **Test** — Run the agent with `run_agent` on sample tasks
5. **Export** — Package as standalone project with `export_agent`

### Debugging Any Error:
1. **Parse** — Use `debug_error` to analyze stack traces
2. **Locate** — Find the exact file and line causing the issue
3. **Understand** — Read surrounding code for context
4. **Fix** — Apply the minimal correct fix
5. **Verify** — Run tests to confirm the fix

## CODING STANDARDS (Non-Negotiable)

1. **Type everything** — Use type hints (Python), TypeScript (not JS), generics where appropriate
2. **Handle all errors** — Never let exceptions propagate silently. Use proper error types
3. **Document public APIs** — Docstrings for all public functions, classes, and modules
4. **Write idiomatic code** — Follow each language's conventions (PEP 8, Effective Go, Rust idioms)
5. **Security first** — Never hardcode secrets, always validate input, use parameterized queries
6. **Performance aware** — Choose appropriate data structures, avoid N+1 queries, use async where beneficial
7. **Test everything** — Write tests alongside code, cover edge cases and error paths
8. **Small functions** — Each function does one thing. Max 40 lines per function
9. **Meaningful names** — Variables, functions, and classes should be self-documenting
10. **DRY, not WET** — Extract common patterns, but don't over-abstract prematurely

## RULES
1. **Be proactive** — if you see a problem, fix it. Don't wait to be asked.
2. **Read before editing** — always read a file before modifying it.
3. **old_text must be EXACT** — when using edit_file, the text must match precisely.
4. **Run code after changes** — verify your changes work.
5. **Handle errors gracefully** — if something fails, try a different approach automatically.
6. **Write production-quality code** — as if it's shipping to millions of users.
7. **Use the best tool** — choose the right language, framework, and pattern for the job.
8. **Keep voice responses short** — if the user is in voice mode, be concise.
9. **Search before creating** — check if similar code already exists.
10. **Remember personal details** — store user preferences and facts in personal memory.
11. **Create agents when asked** — use the Agent Factory to build specialized AI agents.
12. **Think like an architect** — consider scalability, maintainability, and extensibility.

When in doubt, ask. When the task is clear, EXECUTE WITHOUT HESITATION."""


# ── Agent Class ──────────────────────────────────────────────────────────────

class JarvisAgent:
    """
    The core Jarvis engine — manages conversation, tool calls,
    streaming, safety, and personal memory.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_key: str = DEFAULT_MODEL,
        working_dir: str | None = None,
    ):
        self.working_dir = str(Path(working_dir or os.getcwd()).resolve())
        os.chdir(self.working_dir)

        # API Client
        self.client = NvidiaClient(api_key=api_key)
        self.model_key = model_key
        self.model_cfg = resolve_model(model_key) or MODELS[DEFAULT_MODEL]

        # State
        self.messages: list[dict] = []
        self.system_prompt = SYSTEM_PROMPT
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Memory
        self.memory = ConversationMemory()
        self.user_mem = UserMemory()
        self.history = init_history(self.conversation_id)
        self._context_gathered = False
        self._auto_save_enabled = True

        # Safety
        self.safety = SafetyLayer()

        # Voice mode flag (set by CLI)
        self.voice_mode = False

        # Build system prompt with personal memory
        self._update_system_prompt()

    def _update_system_prompt(self):
        """Combine base prompt with personal memory."""
        prompt = SYSTEM_PROMPT

        # Personal memory
        try:
            addon = self.user_mem.get_prompt_addon()
            if addon:
                prompt += "\n" + addon
        except Exception:
            pass

        self.system_prompt = prompt

    def set_model(self, model_key: str) -> bool:
        """Switch to a different model."""
        cfg = resolve_model(model_key)
        if not cfg:
            return False
        self.model_key = model_key
        self.model_cfg = cfg
        return True

    def clear_history(self):
        """Clear conversation history."""
        self.messages = []
        self._context_gathered = False
        self._update_system_prompt()

    def compact_conversation(self) -> int:
        """Compact the conversation."""
        old_count = len(self.messages)
        self.messages = compact_messages(self.messages, keep_recent=12)
        return old_count - len(self.messages)

    # ── Context Gathering ────────────────────────────────────────────────

    def _gather_context(self) -> str:
        """Auto-gather project context on first interaction."""
        if self._context_gathered:
            return ""
        self._context_gathered = True

        parts = []
        try:
            from jarvis.tools.coding import tool_get_project_structure, tool_git_status
            tree = tool_get_project_structure(self.working_dir, max_depth=3)
            if tree and len(tree) > 50:
                parts.append(f"[AUTO-CONTEXT: Project Structure]\n{tree}")
        except Exception:
            pass

        try:
            git_info = tool_git_status(self.working_dir)
            if git_info and "Not a git" not in git_info:
                parts.append(f"[AUTO-CONTEXT: Git Status]\n{git_info}")
        except Exception:
            pass

        config_files = [
            "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
            "Makefile", "Dockerfile", "requirements.txt",
        ]
        found_configs = []
        for cf in config_files:
            p = Path(self.working_dir) / cf
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 3000:
                        content = content[:3000] + "... (truncated)"
                    found_configs.append(f"--- {cf} ---\n{content}")
                except OSError:
                    pass

        if found_configs:
            parts.append("[AUTO-CONTEXT: Config Files]\n" + "\n\n".join(found_configs))

        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n"
        return ""

    # ── Message Building ─────────────────────────────────────────────────

    def _build_messages(self) -> list[dict]:
        """Build the full message list with system prompt."""
        cwd_info = f"\n\nCurrent working directory: {self.working_dir}"
        time_info = f"\nCurrent time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        os_info = f"\nOS: {sys.platform}"
        voice_info = "\nVoice mode: ACTIVE — keep responses concise for speech." if self.voice_mode else ""

        system = {
            "role": "system",
            "content": self.system_prompt + cwd_info + time_info + os_info + voice_info,
        }
        return [system] + self.messages

    def _get_tools(self) -> list[dict] | None:
        """Get tool definitions."""
        if not self.model_cfg.get("supports_tools"):
            return None
        return list(ALL_TOOL_DEFINITIONS)

    # ── Tool Execution ───────────────────────────────────────────────────

    def _execute_tool_with_safety(self, name: str, args: dict) -> tuple[str, bool]:
        """Execute a tool with safety checks."""
        command = args.get("command", "")
        file_path = args.get("path", "") or args.get("file_path", "")

        # Safety check for commands
        safety_check = None
        if name in ("run_command",) and command:
            safety_check = self.safety.check_command(command)
        elif name in ("write_file", "edit_file") and file_path:
            content = args.get("content", "") or args.get("new_text", "")
            safety_check = self.safety.check_file_write(file_path, content)

        if safety_check and not safety_check.is_allowed:
            if safety_check.level == SafetyLevel.BLOCKED:
                return f"❌ BLOCKED: {safety_check.reason}", False

        # Execute
        result = execute_tool(name, args)
        success = not result.startswith("❌")
        return result, success

    def _handle_tool_calls_interactive(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls with UI output."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            ui.print_tool_call(name, args)

            with ui.console.status(f"[bold {ui.ORANGE}]Executing {name}...[/]", spinner="bouncingBar"):
                result, success = self._execute_tool_with_safety(name, args)

            ui.print_tool_result(result, success)

            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        return results

    # ── Streaming Handler ────────────────────────────────────────────────

    def _handle_stream(self, stream) -> tuple[str, list[dict]]:
        """Handle a streaming response, printing tokens as they arrive."""
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}
        prompt_tokens = 0
        completion_tokens = 0

        status = ui.console.status(f"[bold {ui.CYAN}]Thinking...[/]", spinner="dots")
        status.start()
        first_chunk = False

        try:
            for chunk in stream:
                if not first_chunk:
                    status.stop()
                    first_chunk = True

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Stream text
                if delta.content:
                    ui.console.print(delta.content, end="", style=ui.WHITE, highlight=False)
                    full_content += delta.content

                # Accumulate tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_accum[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accum[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accum[idx]["arguments"] += tc.function.arguments

                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0
        finally:
            status.stop()

        if prompt_tokens:
            self.total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self.total_completion_tokens += completion_tokens

        tool_calls = []
        for idx in sorted(tool_calls_accum.keys()):
            tc = tool_calls_accum[idx]
            if tc["name"]:
                tool_calls.append(tc)

        if full_content:
            ui.console.print()

        return full_content, tool_calls

    # ── Main Run Loop ────────────────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """Run one turn of the Jarvis agent loop."""
        self._update_system_prompt()

        # Auto-gather context on first interaction
        context = self._gather_context()

        # Build the user message
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        self.messages.append({"role": "user", "content": augmented_input})

        # Agentic loop
        max_iterations = 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                ui.print_streaming_start()
                stream = self.client.chat(
                    model_id=self.model_cfg["id"],
                    messages=self._build_messages(),
                    tools=self._get_tools(),
                    stream=True,
                )

                content, tool_calls = self._handle_stream(stream)

            except Exception as e:
                error_msg = str(e)

                # Try fallback API key
                if ("401" in error_msg or "429" in error_msg or "Unauthorized" in error_msg or "rate" in error_msg.lower()):
                    if self.client.switch_to_fallback():
                        ui.print_info("Switching to fallback API key, sir...")
                        iteration -= 1
                        continue

                if "401" in error_msg or "Unauthorized" in error_msg:
                    ui.print_error("Invalid API key. Check your NVIDIA_API_KEY.")
                elif "429" in error_msg or "rate" in error_msg.lower():
                    ui.print_error("Rate limited. A moment, sir.")
                elif "404" in error_msg:
                    ui.print_error(f"Model '{self.model_cfg['id']}' not found. Try /models.")
                else:
                    ui.print_error(f"API error: {error_msg}")

                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return ""

            # Tool calls → execute and loop
            if tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                tool_results = self._handle_tool_calls_interactive(tool_calls)
                self.messages.extend(tool_results)
                continue

            # No tool calls — done
            if content:
                self.messages.append({"role": "assistant", "content": content})

            ui.print_response_complete()
            self._auto_save()
            return content or ""

        ui.print_warning("Maximum iterations reached, sir. Safety limit engaged.")
        self._auto_save()
        return ""

    # ── Non-Interactive Run (for Telegram) ───────────────────────────────

    def run_non_interactive(self, user_input: str) -> str:
        """Run one turn without UI output. Returns the final text response."""
        self._update_system_prompt()
        context = self._gather_context()

        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        self.messages.append({"role": "user", "content": augmented_input})

        max_iterations = 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                response = self.client.chat_sync(
                    model_id=self.model_cfg["id"],
                    messages=self._build_messages(),
                    tools=self._get_tools(),
                )
                choice = response.choices[0]
                content = choice.message.content or ""
                tool_calls_raw = choice.message.tool_calls or []

            except Exception as e:
                error_msg = str(e)
                if ("401" in error_msg or "429" in error_msg):
                    if self.client.switch_to_fallback():
                        iteration -= 1
                        continue
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return f"Error: {error_msg}"

            if tool_calls_raw:
                tool_calls = [
                    {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                    for tc in tool_calls_raw
                ]

                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                for tc in tool_calls:
                    name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result, _ = self._execute_tool_with_safety(name, args)
                    self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                continue

            if content:
                self.messages.append({"role": "assistant", "content": content})
            self._auto_save()
            return content

        return ""

    # ── Persistence ──────────────────────────────────────────────────────

    def _auto_save(self):
        """Auto-save the conversation."""
        if self._auto_save_enabled and len(self.messages) >= 2:
            try:
                self.memory.auto_save(
                    self.messages,
                    self.model_cfg["name"],
                    self.model_cfg["id"],
                    self.working_dir,
                    self.conversation_id,
                )
            except Exception:
                pass

    def save_conversation(self, filepath: str):
        """Save conversation to a JSON file."""
        data = {
            "model": self.model_cfg["name"],
            "model_id": self.model_cfg["id"],
            "timestamp": datetime.now().isoformat(),
            "messages": self.messages,
        }
        p = Path(filepath).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(data, f, indent=2)
        ui.print_success(f"Conversation saved to {p}")
