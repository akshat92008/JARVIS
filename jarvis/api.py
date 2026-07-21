"""
NVIDIA API client — OpenAI-compatible wrapper for integrate.api.nvidia.com
Adapted from Nexus for Jarvis.
"""

import os
import json
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _load_env_file():
    """Load environment variables from .env if present."""
    if "NVIDIA_API_KEY" in os.environ:
        return
    
    possible_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.expanduser("~/Desktop/jarvis/.env"),
        os.path.expanduser("~/Desktop/JARVIS/.env"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass


class NvidiaClient:
    """Thin wrapper around the OpenAI SDK pointed at NVIDIA's endpoint."""

    def __init__(self, api_key: str | None = None):
        _load_env_file()
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")


        # Load all fallback keys from environment
        self.fallback_keys = []
        for k in sorted(os.environ.keys()):
            if k.startswith("NVIDIA_FALLBACK_API_KEY") and os.environ[k]:
                self.fallback_keys.append(os.environ[k])

        # Deduplicate and remove the primary key if it's in fallbacks
        self.fallback_keys = [k for k in dict.fromkeys(self.fallback_keys) if k != self.api_key]

        if not self.api_key:
            raise ValueError(
                "No NVIDIA API key found. Set NVIDIA_API_KEY env var or pass --api-key."
            )
        self.client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=self.api_key,
            timeout=15.0,
        )

    def switch_to_fallback(self) -> bool:
        """Switch to the next fallback API key if available."""
        if self.fallback_keys:
            self.api_key = self.fallback_keys.pop(0)
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=self.api_key,
                timeout=15.0,
            )
            return True
        return False

    def chat(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
        stream: bool = True,
    ):
        """Send a chat completion request. Returns a stream or a response."""
        kwargs = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self.client.chat.completions.create(**kwargs)

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
    ):
        """Non-streaming chat completion."""
        return self.chat(
            model_id=model_id,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
