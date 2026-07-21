"""
Voice Speaker — Text-to-Speech using macOS `say` command.
British voice (Daniel) for the authentic Jarvis experience.
"""

import os
import subprocess
import threading


# Available macOS voices that sound good for Jarvis
VOICES = {
    "daniel": "Daniel",        # British English (default Jarvis voice)
    "alex": "Alex",            # American English
    "samantha": "Samantha",    # American English (female)
    "karen": "Karen",          # Australian English
    "moira": "Moira",          # Irish English
    "rishi": "Rishi",          # Indian English
    "tessa": "Tessa",          # South African English
}

DEFAULT_VOICE = "Daniel"
DEFAULT_RATE = 180  # Words per minute


class Speaker:
    """Text-to-Speech engine using macOS say command."""

    def __init__(self, voice: str = DEFAULT_VOICE, rate: int = DEFAULT_RATE):
        self.voice = voice
        self.rate = rate
        self._current_process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def speak(self, text: str, blocking: bool = True):
        """Speak the given text."""
        if not text or not text.strip():
            return

        # Clean text for speech (remove markdown, code, etc.)
        clean = self._clean_for_speech(text)
        if not clean:
            return

        self.stop()  # Stop any current speech

        cmd = ["say", "-v", self.voice, "-r", str(self.rate), clean]

        with self._lock:
            if blocking:
                try:
                    subprocess.run(cmd, timeout=120)
                except (subprocess.TimeoutExpired, Exception):
                    pass
            else:
                try:
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

    def speak_async(self, text: str):
        """Speak in a background thread (non-blocking)."""
        thread = threading.Thread(target=self.speak, args=(text, True), daemon=True)
        thread.start()

    def stop(self):
        """Stop any currently playing speech."""
        with self._lock:
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()
                self._current_process = None

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        with self._lock:
            if self._current_process:
                return self._current_process.poll() is None
            return False

    def set_voice(self, voice: str):
        """Change the voice."""
        if voice.lower() in VOICES:
            self.voice = VOICES[voice.lower()]
        else:
            self.voice = voice

    def set_rate(self, rate: int):
        """Change the speech rate (words per minute)."""
        self.rate = max(100, min(300, rate))

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Clean text for natural speech output."""
        import re

        # Remove markdown formatting
        text = re.sub(r'```[\s\S]*?```', 'code block omitted', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'#+\s*', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'[─═╔╗╚╝╠╣║┌┐└┘├┤│┬┴┼▓▲▼◄►◈●◉⬜🔄✅❌⏭️🔒⚡🛑🚫⚠️📋📁📄🔍🧠💾🔋⏱🖥️🎤📝🔊✓✗ℹ]', '', text)

        # Remove file paths
        text = re.sub(r'/[\w/.-]+', '', text)

        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)

        # Remove excess whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Limit length for speech
        if len(text) > 1000:
            text = text[:1000] + ". I'll stop here. Check the terminal for the full response."

        return text


    @staticmethod
    def list_voices() -> list[str]:
        """List available macOS voices."""
        try:
            result = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                voices = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        name = line.split()[0]
                        voices.append(name)
                return voices
        except Exception:
            pass
        return list(VOICES.values())


# Global speaker instance
_speaker: Speaker | None = None


def get_speaker() -> Speaker:
    """Get or create the global speaker."""
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
    return _speaker
