"""
Model registry — all top-tier models available on NVIDIA's free API catalog.
Adapted from Nexus for Jarvis.
"""

MODELS = {
    # ── Flagship Reasoning & Coding ──────────────────────────────────
    "deepseek-v4": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "category": "reasoning",
        "context": 131072,
        "description": "MoE flagship — 1M context, top-tier reasoning & code",
        "supports_tools": True,
    },
    "deepseek-r1": {
        "id": "deepseek-ai/deepseek-r1",
        "name": "DeepSeek R1",
        "category": "reasoning",
        "context": 131072,
        "description": "Deep reasoning model with chain-of-thought",
        "supports_tools": False,
    },
    "glm-5.2": {
        "id": "thudm/glm-5.2",
        "name": "GLM 5.2",
        "category": "reasoning",
        "context": 131072,
        "description": "Flagship agentic & reasoning LLM by Zhipu AI",
        "supports_tools": True,
    },
    "kimi-k2.6": {
        "id": "moonshotai/kimi-k2.6",
        "name": "Kimi K2.6",
        "category": "coding",
        "context": 131072,
        "description": "Multimodal MoE — optimized for coding & tool use",
        "supports_tools": True,
    },
    "kimi-k3": {
        "id": "moonshotai/kimi-k3",
        "name": "Kimi K3",
        "category": "reasoning",
        "context": 131072,
        "description": "Moonshot AI's next-gen reasoning and coding model",
        "supports_tools": True,
    },
    "glm-5": {
        "id": "thudm/glm-5",
        "name": "GLM 5",
        "category": "reasoning",
        "context": 131072,
        "description": "Zhipu AI's flagship multi-modal reasoning and agentic model",
        "supports_tools": True,
    },
    "deepseek-r1-distill-llama-70b": {
        "id": "nvidia/deepseek-r1-distill-llama-70b",
        "name": "DeepSeek R1 Distill Llama 70B",
        "category": "reasoning",
        "context": 131072,
        "description": "DeepSeek R1 reasoning style distilled on Llama 70B by NVIDIA",
        "supports_tools": True,
    },
    "minimax-m3": {
        "id": "minimax/minimax-m3",
        "name": "MiniMax M3",
        "category": "general",
        "context": 131072,
        "description": "High-performance Mixture-of-Experts model by MiniMax",
        "supports_tools": True,
    },
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "category": "general",
        "context": 131072,
        "description": "Meta's state-of-the-art 70B instruction-tuned model",
        "supports_tools": True,
    },
    "llama-3.1-70b": {
        "id": "meta/llama-3.1-70b-instruct",
        "name": "Llama 3.1 70B",
        "category": "general",
        "context": 131072,
        "description": "Meta's highly capable 70B instruction-tuned model",
        "supports_tools": True,
    },
    # ── NVIDIA Nemotron Family ───────────────────────────────────────
    "nemotron-ultra": {
        "id": "nvidia/nemotron-3-ultra-550b-a55b",
        "name": "Nemotron Ultra 550B",
        "category": "reasoning",
        "context": 131072,
        "description": "NVIDIA flagship — agentic reasoning, 550B params",
        "supports_tools": True,
    },
    "nemotron-super": {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct",
        "name": "Nemotron 70B",
        "category": "general",
        "context": 131072,
        "description": "Fine-tuned Llama 3.1 70B by NVIDIA",
        "supports_tools": True,
    },
    # ── Qwen Family ─────────────────────────────────────────────────
    "qwen-2.5-72b": {
        "id": "qwen/qwen2.5-72b-instruct",
        "name": "Qwen 2.5 72B",
        "category": "general",
        "context": 131072,
        "description": "Alibaba's 72B flagship — strong code & math",
        "supports_tools": True,
    },
    "qwen-coder": {
        "id": "qwen/qwen2.5-coder-32b-instruct",
        "name": "Qwen 2.5 Coder 32B",
        "category": "coding",
        "context": 65536,
        "description": "Specialized coding model by Alibaba",
        "supports_tools": True,
    },
}

# Aliases for convenience
ALIASES = {
    "deepseek": "deepseek-v4",
    "ds": "deepseek-v4",
    "r1": "deepseek-r1",
    "glm": "glm-5.2",
    "kimi": "kimi-k3",
    "minimax": "minimax-m3",
    "llama": "llama-3.3-70b",
    "nemotron": "nemotron-ultra",
    "qwen": "qwen-2.5-72b",
}

DEFAULT_MODEL = "llama-3.1-70b"


def resolve_model(key: str) -> dict | None:
    """Resolve a model key or alias to its config dict."""
    key = key.lower().strip()
    if key in MODELS:
        return MODELS[key]
    if key in ALIASES:
        return MODELS[ALIASES[key]]
    # Fuzzy match
    for name, cfg in MODELS.items():
        if key in name or key in cfg["name"].lower():
            return cfg
    return None


def list_models() -> list[dict]:
    """Return all models as a list of dicts with key included."""
    result = []
    for key, cfg in MODELS.items():
        entry = dict(cfg)
        entry["key"] = key
        result.append(entry)
    return result
