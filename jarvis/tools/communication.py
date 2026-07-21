"""
Communication Tools — iMessage, Reminders, and email integration via AppleScript.
"""

import subprocess
from datetime import datetime


# ── Tool Definitions ─────────────────────────────────────────────────────────

COMMUNICATION_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "send_imessage",
            "description": "Send an iMessage to a contact (phone number or email).",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient phone number or email."},
                    "message": {"type": "string", "description": "Message text to send."},
                },
                "required": ["to", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Add a reminder to Apple Reminders app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Reminder title."},
                    "notes": {"type": "string", "description": "Additional notes."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reminders",
            "description": "Get the list of current reminders from Apple Reminders.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Add an event to Apple Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "date": {"type": "string", "description": "Event date (e.g., 'tomorrow at 3pm', '2026-07-25 14:00')."},
                    "duration_hours": {"type": "number", "description": "Event duration in hours (default: 1)."},
                    "notes": {"type": "string", "description": "Event notes."},
                },
                "required": ["title", "date"],
            },
        },
    },
]


# ── Implementations ──────────────────────────────────────────────────────────

def _run_applescript(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return f"❌ AppleScript error: {result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"❌ Error: {e}"


def tool_send_imessage(to: str, message: str) -> str:
    """Send an iMessage."""
    escaped_msg = message.replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{to}" of targetService
        send "{escaped_msg}" to targetBuddy
    end tell
    '''
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    return f"✅ iMessage sent to {to}"


def tool_add_reminder(title: str, notes: str = "") -> str:
    """Add a reminder to Apple Reminders."""
    escaped_title = title.replace('"', '\\"')
    script = f'''
    tell application "Reminders"
        tell list "Reminders"
            make new reminder with properties {{name:"{escaped_title}"}}
        end tell
    end tell
    '''
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    return f"✅ Reminder added: {title}"


def tool_get_reminders() -> str:
    """Get current reminders."""
    script = '''
    tell application "Reminders"
        set reminderList to {}
        repeat with r in (reminders of list "Reminders" whose completed is false)
            set end of reminderList to name of r
        end repeat
        return reminderList
    end tell
    '''
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    if not result:
        return "No pending reminders."
    items = [r.strip() for r in result.split(",")]
    return f"Pending reminders ({len(items)}):\n" + "\n".join(f"  • {r}" for r in items)


def tool_add_calendar_event(title: str, date: str, duration_hours: float = 1, notes: str = "") -> str:
    """Add a calendar event."""
    escaped_title = title.replace('"', '\\"')
    escaped_notes = notes.replace('"', '\\"')
    script = f'''
    tell application "Calendar"
        tell calendar "Calendar"
            make new event with properties {{summary:"{escaped_title}", description:"{escaped_notes}"}}
        end tell
    end tell
    '''
    result = _run_applescript(script)
    if result.startswith("❌"):
        return result
    return f"✅ Calendar event added: {title} on {date}"


# ── Dispatch ─────────────────────────────────────────────────────────────────

COMMUNICATION_DISPATCH = {
    "send_imessage": lambda **kw: tool_send_imessage(kw.get("to", ""), kw.get("message", "")),
    "add_reminder": lambda **kw: tool_add_reminder(kw.get("title", ""), kw.get("notes", "")),
    "get_reminders": lambda **kw: tool_get_reminders(),
    "add_calendar_event": lambda **kw: tool_add_calendar_event(
        kw.get("title", ""), kw.get("date", ""), kw.get("duration_hours", 1), kw.get("notes", "")),
}
