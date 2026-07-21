"""
Desktop Tools — macOS system control via AppleScript and shell commands.
Gives Jarvis the ability to control the Mac like Iron Man controls his lab.
"""

import os
import subprocess
import platform
import json
from pathlib import Path


# ── Tool Definitions ─────────────────────────────────────────────────────────

DESKTOP_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a macOS application by name (e.g., 'Safari', 'Finder', 'Spotify').",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Application name to open."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Close/quit a running macOS application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Application name to close."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the system volume (0-100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Volume level from 0 (mute) to 100 (max)."},
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get system information: CPU usage, memory, disk, battery, active apps.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot and save it to a specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output_path": {"type": "string", "description": "Path to save the screenshot (default: ~/Desktop/screenshot.png)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Set the screen brightness (0.0-1.0).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "number", "description": "Brightness level from 0.0 (dark) to 1.0 (max)."},
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_screen",
            "description": "Lock the Mac screen immediately.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify",
            "description": "Show a macOS desktop notification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title."},
                    "message": {"type": "string", "description": "Notification body text."},
                },
                "required": ["title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_window",
            "description": "Get the name and window title of the currently focused application.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently active application window using keyboard simulation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to type."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_apps",
            "description": "List all currently running applications on the Mac.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a URL in the default web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open."},
                },
                "required": ["url"],
            },
        },
    },
]


# ── Tool Implementations ─────────────────────────────────────────────────────

def _run_applescript(script: str) -> str:
    """Execute an AppleScript and return the result."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return f"❌ AppleScript error: {result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "❌ AppleScript timed out."
    except Exception as e:
        return f"❌ Error: {e}"


def tool_open_app(name: str) -> str:
    """Open a macOS application."""
    result = _run_applescript(f'tell application "{name}" to activate')
    if result.startswith("❌"):
        return result
    return f"✅ Opened {name}"


def tool_close_app(name: str) -> str:
    """Close a macOS application."""
    result = _run_applescript(f'tell application "{name}" to quit')
    if result.startswith("❌"):
        return result
    return f"✅ Closed {name}"


def tool_set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    # macOS volume is 0-7 in osascript, but we can use 0-100 directly
    osascript_level = int(level * 7 / 100)
    _run_applescript(f"set volume output volume {level}")
    return f"✅ Volume set to {level}%"


def tool_get_system_info() -> str:
    """Get comprehensive system information."""
    info = []

    # OS info
    info.append(f"🖥  System: {platform.system()} {platform.release()} ({platform.machine()})")

    # CPU usage
    try:
        cpu = subprocess.run(
            "top -l 1 -n 0 | grep 'CPU usage'",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if cpu.stdout.strip():
            info.append(f"⚡ {cpu.stdout.strip()}")
    except Exception:
        pass

    # Memory
    try:
        mem = subprocess.run(
            "vm_stat | head -5",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        # Parse page size and free pages
        lines = mem.stdout.strip().split("\n")
        if len(lines) > 1:
            info.append(f"🧠 Memory (from vm_stat):")
            for line in lines[1:4]:
                info.append(f"   {line.strip()}")
    except Exception:
        pass

    # Disk
    try:
        disk = subprocess.run(
            "df -h / | tail -1",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if disk.stdout.strip():
            parts = disk.stdout.strip().split()
            if len(parts) >= 5:
                info.append(f"💾 Disk: {parts[3]} free of {parts[1]} ({parts[4]} used)")
    except Exception:
        pass

    # Battery
    try:
        battery = subprocess.run(
            "pmset -g batt",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if battery.stdout.strip():
            for line in battery.stdout.strip().split("\n"):
                if "%" in line:
                    info.append(f"🔋 Battery: {line.strip()}")
                    break
    except Exception:
        pass

    # Uptime
    try:
        uptime = subprocess.run(
            "uptime",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if uptime.stdout.strip():
            info.append(f"⏱  {uptime.stdout.strip()}")
    except Exception:
        pass

    return "\n".join(info) if info else "❌ Could not retrieve system info."


def tool_take_screenshot(output_path: str = "") -> str:
    """Take a screenshot."""
    if not output_path:
        output_path = str(Path.home() / "Desktop" / f"screenshot_{int(__import__('time').time())}.png")

    p = Path(output_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["screencapture", "-x", str(p)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"❌ Screenshot failed: {result.stderr}"
        return f"✅ Screenshot saved to {p}"
    except Exception as e:
        return f"❌ Screenshot error: {e}"


def tool_set_brightness(level: float) -> str:
    """Set screen brightness (0.0-1.0)."""
    level = max(0.0, min(1.0, level))
    try:
        # Try using brightness command if available
        result = subprocess.run(
            f"brightness {level}",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return f"✅ Brightness set to {int(level * 100)}%"
        # Fallback: AppleScript (limited support)
        return f"⚠️ brightness command not found. Install with: brew install brightness"
    except Exception as e:
        return f"❌ Brightness error: {e}"


def tool_lock_screen() -> str:
    """Lock the Mac screen."""
    try:
        subprocess.run(
            ["pmset", "displaysleepnow"],
            capture_output=True, timeout=5,
        )
        return "✅ Screen locked."
    except Exception as e:
        return f"❌ Lock screen error: {e}"


def tool_notify(title: str, message: str) -> str:
    """Show a macOS notification."""
    script = f'display notification "{message}" with title "{title}"'
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    return f"✅ Notification sent: {title}"


def tool_get_active_window() -> str:
    """Get the currently focused application and window."""
    script = """
    tell application "System Events"
        set frontApp to name of first process whose frontmost is true
    end tell
    return frontApp
    """
    app_name = _run_applescript(script)
    if app_name.startswith("❌"):
        return app_name
    return f"Active application: {app_name}"


def tool_type_text(text: str) -> str:
    """Type text into the active application."""
    # Escape special characters for AppleScript
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    return f"✅ Typed {len(text)} characters"


def tool_list_running_apps() -> str:
    """List running applications."""
    script = """
    tell application "System Events"
        set appList to name of every process whose background only is false
    end tell
    return appList
    """
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    apps = [a.strip() for a in result.split(",")]
    return f"Running applications ({len(apps)}):\n" + "\n".join(f"  • {app}" for app in apps)


def tool_open_url(url: str) -> str:
    """Open a URL in the default browser."""
    try:
        subprocess.run(["open", url], timeout=10)
        return f"✅ Opened {url} in browser"
    except Exception as e:
        return f"❌ Error opening URL: {e}"


# ── Dispatch ─────────────────────────────────────────────────────────────────

DESKTOP_DISPATCH = {
    "open_app": lambda **kw: tool_open_app(kw.get("name", "")),
    "close_app": lambda **kw: tool_close_app(kw.get("name", "")),
    "set_volume": lambda **kw: tool_set_volume(kw.get("level", 50)),
    "get_system_info": lambda **kw: tool_get_system_info(),
    "take_screenshot": lambda **kw: tool_take_screenshot(kw.get("output_path", "")),
    "set_brightness": lambda **kw: tool_set_brightness(kw.get("level", 0.5)),
    "lock_screen": lambda **kw: tool_lock_screen(),
    "notify": lambda **kw: tool_notify(kw.get("title", "Jarvis"), kw.get("message", "")),
    "get_active_window": lambda **kw: tool_get_active_window(),
    "type_text": lambda **kw: tool_type_text(kw.get("text", "")),
    "list_running_apps": lambda **kw: tool_list_running_apps(),
    "open_url": lambda **kw: tool_open_url(kw.get("url", "")),
}
