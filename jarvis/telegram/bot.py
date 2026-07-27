"""
Telegram Bot — allows controlling Jarvis from your phone via Telegram.
Supports text messages, voice notes, and file sharing.
"""

import os
import asyncio
import tempfile
from pathlib import Path

from jarvis import ui


def start_telegram_bot(agent):
    """Start the Telegram bot (blocking)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        ui.print_error(
            "TELEGRAM_BOT_TOKEN not set.\n"
            "  1. Open Telegram and message @BotFather\n"
            "  2. Send /newbot and follow the steps\n"
            "  3. Copy the token and run:\n"
            "     export TELEGRAM_BOT_TOKEN='your-token-here'"
        )
        return

    allowed_user_id = os.environ.get("TELEGRAM_USER_ID", "")

    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
        from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
    except ImportError:
        ui.print_error("Install python-telegram-bot: pip install python-telegram-bot")
        return

    # ── Handlers ─────────────────────────────────────────────────────

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not _is_authorized(update, allowed_user_id):
            await update.message.reply_text("⛔ Unauthorized. This is a private assistant.")
            return
        await update.message.reply_text(
            "🤖 *J.A.R.V.I.S. Online*\n\n"
            "I'm connected to your Mac and ready to assist.\n\n"
            "Send me:\n"
            "• 💬 Text messages for any request\n"
            "• 🎤 Voice notes (I'll transcribe and process)\n"
            "• 📎 Files (I'll save them to your Mac)\n\n"
            "Company controls: /briefing, /approvals, /resume\n\n"
            "At your service, sir.",
            parse_mode="Markdown",
        )

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        if not _is_authorized(update, allowed_user_id):
            return

        user_text = update.message.text
        ui.print_info(f"[Telegram] Received: {user_text[:80]}...")

        # Run agent in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, agent.run_non_interactive, user_text)

        if response:
            # Split long messages (Telegram limit is 4096 chars)
            for chunk in _split_message(response):
                await update.message.reply_text(chunk)

            # Check if any files were generated
            await _send_generated_files(update, response)
        else:
            await update.message.reply_text("I processed your request but have no text response.")

    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice notes — download, transcribe, process."""
        if not _is_authorized(update, allowed_user_id):
            return

        ui.print_info("[Telegram] Received voice note...")

        # Download voice file
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            voice_path = tmp.name

        # Transcribe
        transcription = _transcribe_voice(voice_path)
        os.unlink(voice_path)

        if not transcription:
            await update.message.reply_text("Sorry, I couldn't understand that voice note.")
            return

        await update.message.reply_text(f"🎤 *Heard:* _{transcription}_", parse_mode="Markdown")

        # Process with agent
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, agent.run_non_interactive, transcription)

        if response:
            for chunk in _split_message(response):
                await update.message.reply_text(chunk)
            await _send_generated_files(update, response)

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads — save to Mac."""
        if not _is_authorized(update, allowed_user_id):
            return

        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)

        save_dir = Path.home() / "Desktop" / "jarvis_uploads"
        save_dir.mkdir(exist_ok=True)
        save_path = save_dir / doc.file_name

        await file.download_to_drive(str(save_path))
        ui.print_info(f"[Telegram] Saved file: {save_path}")

        await update.message.reply_text(
            f"📎 File saved to your Mac:\n`{save_path}`\n\n"
            f"What would you like me to do with it?",
            parse_mode="Markdown",
        )

    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not _is_authorized(update, allowed_user_id):
            return
        from jarvis.tools.desktop import tool_get_system_info
        info = tool_get_system_info()
        await update.message.reply_text(f"```\n{info}\n```", parse_mode="Markdown")

    async def approvals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show founder-only approval cards with explicit action buttons."""
        if not allowed_user_id:
            await update.message.reply_text("Founder approvals are disabled until TELEGRAM_USER_ID is configured.")
            return
        if not _is_authorized(update, allowed_user_id):
            return
        from jarvis.tools.amaura import get_control_plane
        approvals = get_control_plane().store.list_approvals("pending")
        if not approvals:
            await update.message.reply_text("✅ No founder approvals are pending.")
            return
        for item in approvals:
            payload = item.get("payload", {})
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"amaura:approved:{item['id']}"),
                InlineKeyboardButton("✏️ Revise", callback_data=f"amaura:changes_requested:{item['id']}"),
                InlineKeyboardButton("⛔ Reject", callback_data=f"amaura:rejected:{item['id']}"),
            ]])
            await update.message.reply_text(
                f"🛡️ AMAURA APPROVAL\n\n"
                f"{payload.get('title', 'Company action')}\n"
                f"Risk: {item['risk'].upper()}\n"
                f"Action: {item['action_type']}\n"
                f"Cost: {payload.get('spent_cents', 0)} / {payload.get('budget_cents', 0)} cents\n\n"
                f"{payload.get('summary', '')[:1200]}",
                reply_markup=keyboard,
            )

    async def amaura_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Apply an authenticated founder decision from a Telegram inline button."""
        query = update.callback_query
        if not allowed_user_id or str(query.from_user.id) != allowed_user_id:
            await query.answer("Founder authority required.", show_alert=True)
            return
        await query.answer()
        try:
            _, decision, approval_id = query.data.split(":", 2)
            from jarvis.tools.amaura import get_control_plane
            control = get_control_plane()
            reason = f"{decision.replace('_', ' ').title()} by {control.founder_name} via authenticated Telegram"
            result = control.decide_approval(approval_id, control.founder_id, decision, reason)
            await query.edit_message_text(
                f"Decision recorded: {decision.upper()}\n"
                f"Task: {result['task']['title']}\n"
                f"Audit ID: {approval_id}"
            )
        except Exception as exc:
            await query.edit_message_text(f"Approval could not be recorded: {exc}")

    async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the daily JARVIS company operating briefing."""
        if not _is_authorized(update, allowed_user_id):
            return
        from jarvis.tools.amaura import get_control_plane
        briefing = get_control_plane().daily_briefing()
        status = briefing["company_status"]
        decisions = briefing["top_founder_decisions"]
        lines = [
            "📊 AMAURA DAILY BRIEFING",
            f"Active programmes: {status['active_programmes']}",
            f"Blocked tasks: {briefing['projects_blocked']}",
            f"Completed tasks: {briefing['projects_completed']}",
            f"Pending approvals: {status['pending_approvals']}",
            f"Recorded cost: {briefing['costs_incurred_cents']} cents",
            f"Critical risks: {briefing['critical_risks']}",
            "",
            "Top founder decisions:",
        ]
        lines.extend(f"• {item['title']} [{item['risk']}]" for item in decisions)
        if not decisions:
            lines.append("• None")
        await update.message.reply_text("\n".join(lines))

    async def resume_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restore a paused company employee using authenticated founder authority."""
        if not allowed_user_id:
            await update.message.reply_text("Founder controls are disabled until TELEGRAM_USER_ID is configured.")
            return
        if not _is_authorized(update, allowed_user_id):
            return
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /resume <agent_id> <reviewed reason>")
            return
        agent_id, reason = context.args[0], " ".join(context.args[1:])
        try:
            from jarvis.tools.amaura import get_control_plane
            control = get_control_plane()
            restored = control.resume_agent(agent_id, reason, actor=control.founder_id)
            await update.message.reply_text(f"✅ {restored['name']} restored. The decision is in the audit log.")
        except Exception as exc:
            await update.message.reply_text(f"Employee could not be restored: {exc}")

    # ── Build and run the bot ────────────────────────────────────────

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("approvals", approvals_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("resume", resume_agent_command))
    app.add_handler(CallbackQueryHandler(amaura_approval_callback, pattern=r"^amaura:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    ui.print_success("Telegram bot started! Send me a message on Telegram.")
    ui.print_info("Press Ctrl+C to stop.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


# ── Helper Functions ─────────────────────────────────────────────────────────

def _is_authorized(update, allowed_user_id: str) -> bool:
    """Check if the message sender is authorized."""
    if not allowed_user_id:
        return True  # No restriction set
    return str(update.message.from_user.id) == allowed_user_id


def _split_message(text: str, max_length: int = 4000) -> list[str]:
    """Split a long message into chunks for Telegram."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        # Find a good split point
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


def _transcribe_voice(audio_path: str) -> str | None:
    """Transcribe a voice file using SpeechRecognition."""
    try:
        import speech_recognition as sr
        import subprocess

        # Convert OGG to WAV
        wav_path = audio_path.replace(".ogg", ".wav")
        subprocess.run(
            ["ffmpeg", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path, "-y"],
            capture_output=True, timeout=30,
        )

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)

        text = recognizer.recognize_google(audio)
        os.unlink(wav_path)
        return text.strip()
    except Exception:
        return None


async def _send_generated_files(update, response: str):
    """Check response for generated file paths and send them."""
    import re
    import os
    # Look for file paths in the response
    paths = re.findall(r'(?:saved to|created:|wrote to)\s+([/~][\w/._-]+)', response, re.IGNORECASE)
    for p in paths:
        path = os.path.expanduser(p.strip())
        if os.path.exists(path) and os.path.isfile(path):
            try:
                await update.message.reply_document(document=open(path, 'rb'))
            except Exception as e:
                import logging
                logging.error(f"Failed to send file {path}: {e}")
