"""
Jarvis UI — Iron Man-styled terminal interface using Rich.
Cyan/gold color scheme with animated boot sequence and HUD-style formatting.
"""

import os
import sys
import time
import platform
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import box

# ── Color Palette (Iron Man HUD) ────────────────────────────────────────────
CYAN = "#00d4ff"
GOLD = "#ffd700"
ARC_BLUE = "#4fc3f7"
ORANGE = "#ff6b35"
RED = "#ff3333"
GREEN = "#00ff88"
WHITE = "#e0e0e0"
DIM = "#666666"
DARK_BG = "#0a0a0a"
PANEL_BORDER = "#1a5276"

console = Console()

# ── ASCII Art ────────────────────────────────────────────────────────────────

ARC_REACTOR = """
[bold #4fc3f7]
              ╔══════════════╗
          ╔═══╣  ◉  J.A.R.V.I.S.  ◉  ╠═══╗
      ╔═══╝   ╚══════════════╝   ╚═══╗
      ║     ┌──────────────────┐     ║
      ║     │  ╔══╗  ▲▲  ╔══╗ │     ║
      ║     │  ║▓▓║◄═╬╬═►║▓▓║ │     ║
      ║     │  ╚══╝  ▼▼  ╚══╝ │     ║
      ║     └──────────────────┘     ║
      ╚═══╗   ╔══════════════╗   ╔═══╝
          ╚═══╣    ◉  ◉  ◉    ╠═══╝
              ╚══════════════╝
[/]
"""

JARVIS_BANNER = """[bold #ffd700]
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
[/]"""


# ── Boot Sequence ────────────────────────────────────────────────────────────

def print_boot_sequence(model_name: str = "", working_dir: str = ""):
    """Display the Iron Man-style boot sequence."""
    console.clear()

    # Arc Reactor
    console.print(ARC_REACTOR, justify="center")

    # Banner
    console.print(JARVIS_BANNER, justify="center")

    # Tagline
    console.print(
        "[bold #4fc3f7]Just A Rather Very Intelligent System[/]",
        justify="center",
    )
    console.print(
        f"[{DIM}]Powered by NVIDIA • v1.0.0[/]",
        justify="center",
    )
    console.print()

    # Boot steps
    boot_steps = [
        ("Initializing neural pathways", 0.15),
        ("Loading language models", 0.15),
        ("Calibrating safety protocols", 0.1),
        ("Connecting to NVIDIA API", 0.1),
        ("Activating tool subsystems", 0.1),
        ("Loading personal memory", 0.1),
        ("Systems online", 0.05),
    ]

    for step_text, delay in boot_steps:
        with console.status(f"[bold {CYAN}]  ◈ {step_text}...[/]", spinner="dots"):
            time.sleep(delay)
        console.print(f"  [{GREEN}]✓[/] [{WHITE}]{step_text}[/]")

    console.print()

    # System info panel
    info_items = []
    if model_name:
        info_items.append(f"[{GOLD}]Model:[/] [{WHITE}]{model_name}[/]")
    if working_dir:
        info_items.append(f"[{GOLD}]Directory:[/] [{WHITE}]{working_dir}[/]")
    info_items.append(f"[{GOLD}]Platform:[/] [{WHITE}]{platform.system()} {platform.machine()}[/]")
    info_items.append(f"[{GOLD}]Time:[/] [{WHITE}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]")

    info_panel = Panel(
        "\n".join(info_items),
        title=f"[bold {CYAN}]◈ SYSTEM STATUS ◈[/]",
        border_style=PANEL_BORDER,
        padding=(1, 2),
    )
    console.print(info_panel)
    console.print()

    # Ready message
    console.print(
        f"  [{GREEN}]●[/] [{WHITE}]All systems operational. At your service, sir.[/]",
    )
    console.print(
        f"  [{DIM}]Type your request, or use /help for commands. Press Ctrl+C to exit.[/]",
    )
    console.print()


# ── Prompt ───────────────────────────────────────────────────────────────────

def get_prompt_text(voice_mode: bool = False) -> str:
    """Get the prompt prefix text."""
    if voice_mode:
        return f"[bold {CYAN}]◈ JARVIS [voice] ›[/] "
    return f"[bold {CYAN}]◈ JARVIS ›[/] "


# ── Output Formatting ────────────────────────────────────────────────────────

def print_user_input(text: str):
    """Display formatted user input."""
    console.print(f"\n[bold {GOLD}]You:[/] [{WHITE}]{text}[/]")


def print_streaming_start():
    """Visual separator before streaming response."""
    console.print(f"\n[{DIM}]{'─' * 60}[/]")
    console.print(f"[bold {CYAN}]Jarvis:[/] ", end="")


def print_response_complete():
    """Visual separator after streaming response."""
    console.print(f"\n[{DIM}]{'─' * 60}[/]")


def print_tool_call(name: str, args: dict):
    """Display a tool call in HUD style."""
    # Format args for display
    display_args = {}
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 80:
            sv = sv[:77] + "..."
        display_args[k] = sv

    args_str = ", ".join(f"[{DIM}]{k}=[/][{WHITE}]{v}[/]" for k, v in display_args.items())

    console.print(f"\n  [{ORANGE}]⚡ {name}[/]({args_str})")


def print_tool_result(result: str, success: bool = True):
    """Display tool result."""
    if not result:
        return

    max_lines = 30
    lines = result.split("\n")
    truncated = len(lines) > max_lines

    display_text = "\n".join(lines[:max_lines])
    if truncated:
        display_text += f"\n... ({len(lines) - max_lines} more lines)"

    color = GREEN if success else RED
    icon = "✓" if success else "✗"

    if len(display_text) > 200:
        console.print(
            Panel(
                display_text,
                title=f"[{color}]{icon} Result[/]",
                border_style=DIM,
                padding=(0, 1),
            )
        )
    else:
        console.print(f"  [{color}]{icon}[/] [{DIM}]{display_text}[/]")


def print_info(message: str):
    """Print an info message."""
    console.print(f"  [{CYAN}]ℹ[/] [{WHITE}]{message}[/]")


def print_success(message: str):
    """Print a success message."""
    console.print(f"  [{GREEN}]✓[/] [{WHITE}]{message}[/]")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"  [{ORANGE}]⚠[/] [{WHITE}]{message}[/]")


def print_error(message: str):
    """Print an error message."""
    console.print(f"  [{RED}]✗[/] [{WHITE}]{message}[/]")


def print_voice_listening():
    """Indicate voice listening mode."""
    console.print(f"\n  [{CYAN}]🎤 Listening...[/] [{DIM}](speak now, press Enter when done)[/]")


def print_voice_transcription(text: str):
    """Show the transcribed voice input."""
    console.print(f"  [{GREEN}]📝[/] [{WHITE}]Heard: \"{text}\"[/]")


def print_jarvis_speaking(text: str):
    """Indicate Jarvis is speaking."""
    console.print(f"  [{CYAN}]🔊[/] [{DIM}]Speaking...[/]")


# ── Help & Status ────────────────────────────────────────────────────────────

def print_help():
    """Display the help panel."""
    help_table = Table(
        title=f"[bold {CYAN}]◈ JARVIS COMMANDS ◈[/]",
        border_style=PANEL_BORDER,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    help_table.add_column("Command", style=f"bold {GOLD}", width=20)
    help_table.add_column("Description", style=WHITE)

    commands = [
        ("/help", "Show this help panel"),
        ("/voice", "Toggle voice mode (speak instead of type)"),
        ("/model <name>", "Switch AI model (e.g., /model kimi-k3)"),
        ("/models", "List all available models"),
        ("/research <topic>", "Deep web research on a topic"),
        ("/ppt <topic>", "Generate a PowerPoint presentation"),
        ("/desktop", "Show desktop control commands"),
        ("/memory", "View what Jarvis remembers about you"),
        ("/remember <fact>", "Teach Jarvis a personal fact"),
        ("/forget", "Clear personal memory"),
        ("/history", "View conversation history"),
        ("/save <file>", "Save conversation to file"),
        ("/clear", "Clear conversation (start fresh)"),
        ("/compact", "Compact long conversation"),
        ("/undo", "Undo last file change"),
        ("/changes", "Show file changes in this session"),
        ("/telegram", "Start Telegram bot (for mobile access)"),
        ("/status", "System status (CPU, RAM, battery)"),
        ("/exit, /quit", "Exit Jarvis"),
    ]

    for cmd, desc in commands:
        help_table.add_row(cmd, desc)

    console.print()
    console.print(help_table)
    console.print()


def print_models(models: list[dict], current_model: str = ""):
    """Display available models in a table."""
    table = Table(
        title=f"[bold {CYAN}]◈ AVAILABLE MODELS ◈[/]",
        border_style=PANEL_BORDER,
        box=box.ROUNDED,
    )
    table.add_column("Key", style=f"bold {GOLD}", width=25)
    table.add_column("Name", style=WHITE, width=25)
    table.add_column("Category", style=CYAN, width=12)
    table.add_column("Tools", style=GREEN, width=6)
    table.add_column("Description", style=DIM, width=40)

    for m in models:
        key = m["key"]
        marker = " ◄" if key == current_model else ""
        tools = "✓" if m.get("supports_tools") else "✗"
        table.add_row(
            key + marker,
            m["name"],
            m.get("category", ""),
            tools,
            m.get("description", ""),
        )

    console.print()
    console.print(table)
    console.print()


def print_goodbye():
    """Display exit message."""
    console.print(f"\n  [{CYAN}]◈[/] [{WHITE}]Shutting down all systems. Until next time, sir.[/]")
    console.print(f"  [{DIM}]J.A.R.V.I.S. offline.[/]\n")
