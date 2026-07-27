"""
Voice Speaker — Streaming Text-to-Speech using macOS `say` command.
British voice (Daniel) for the authentic Jarvis experience.
Supports sentence-level streaming TTS and instant barge-in interruption.
"""

import re
import queue
import subprocess
import threading
from typing import Optional, List

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
    """Text-to-Speech engine using macOS say command with streaming & interruption support."""

    def __init__(self, voice: str = DEFAULT_VOICE, rate: int = DEFAULT_RATE):
        self.voice = voice
        self.rate = rate
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._interrupt_event = threading.Event()
        self._speech_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None

    def speak(self, text: str, blocking: bool = True):
        """Speak the given text."""
        if not text or not text.strip():
            return

        clean = self._clean_for_speech(text)
        if not clean:
            return

        self.stop()
        self._interrupt_event.clear()

        cmd = ["say", "-v", self.voice, "-r", str(self.rate), clean]

        with self._lock:
            if blocking:
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self._current_process = p
                    while p.poll() is None:
                        if self._interrupt_event.is_set():
                            p.terminate()
                            break
                        p.wait(timeout=0.1)
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

    def speak_stream(self, text_generator):
        """Stream sentence chunks to speech as text is being generated."""
        self.stop()
        self._interrupt_event.clear()

        def stream_worker():
            buffer = ""
            for chunk in text_generator:
                if self._interrupt_event.is_set():
                    break
                buffer += chunk
                sentences = re.split(r'([.!?\n]+)', buffer)
                while len(sentences) > 2:
                    sentence = sentences.pop(0) + sentences.pop(0)
                    clean_s = self._clean_for_speech(sentence)
                    if clean_s and not self._interrupt_event.is_set():
                        self.speak(clean_s, blocking=True)
                    buffer = "".join(sentences)

            if buffer.strip() and not self._interrupt_event.is_set():
                clean_s = self._clean_for_speech(buffer)
                if clean_s:
                    self.speak(clean_s, blocking=True)

        t = threading.Thread(target=stream_worker, daemon=True)
        t.start()

    def stop(self):
        """Stop any currently playing speech immediately (barge-in)."""
        self._interrupt_event.set()
        with self._lock:
            if self._current_process and self._current_process.poll() is None:
                try:
                    self._current_process.terminate()
                except Exception:
                    pass
                self._current_process = None

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        with self._lock:
            if self._current_process:
                return self._current_process.poll() is None
            return False

    def set_voice(self, voice: str):
        if voice.lower() in VOICES:
            self.voice = VOICES[voice.lower()]
        else:
            self.voice = voice

    def set_rate(self, rate: int):
        self.rate = max(100, min(300, rate))

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Clean text for natural speech output."""
        text = re.sub(r'```[\s\S]*?```', 'code block omitted', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'#+\s*', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'[─═╔╗╚╝╠╣║┌┐└┘├┤│┬┴┼▓▲▼◄►◈●◉⬜🔄✅❌⏭️🔒⚡🛑🚫⚠️📋📁📄🔍🧠💾🔋⏱🖥️🎤📝🔊✓✗ℹ]', '', text)
        text = re.sub(r'/[\w/.-]+', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 1000:
            text = text[:1000] + ". I'll stop here. Check the output for full response."
        return text

    @staticmethod
    def list_voices() -> List[str]:
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


_speaker: Optional[Speaker] = None


def get_speaker() -> Speaker:
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
    return _speaker
