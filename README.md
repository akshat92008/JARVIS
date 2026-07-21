# 🤖 J.A.R.V.I.S.
### Just A Rather Very Intelligent System

A full-fledged personal AI assistant inspired by Iron Man's J.A.R.V.I.S. — powered by NVIDIA's free API.
Control your Mac with voice, generate documents, research the web, write code, and manage your digital life from the terminal or your phone via Telegram.

---

## ⚡ Quick Start

```bash
# 1. Set your NVIDIA API key (free from build.nvidia.com)
export NVIDIA_API_KEY="your-key-here"

# 2. Launch Jarvis
./jarvis.sh

# Or with Python directly:
python -m jarvis
```

## 🎙️ Voice Mode

```bash
# Start with voice enabled
python -m jarvis --voice

# Or toggle inside the CLI
/voice
```

## 📱 Telegram Bot (Mobile Access)

```bash
# 1. Message @BotFather on Telegram → /newbot → copy the token
export TELEGRAM_BOT_TOKEN="your-token"
export TELEGRAM_USER_ID="your-telegram-id"   # optional, for security

# 2. Start the bot
python -m jarvis --telegram
```

## 🛠️ 37+ Tools

| Category | Tools | Examples |
| :--- | :--- | :--- |
| **File & Code** | 14 tools | Read, write, edit files, search code, run commands, git |
| **Desktop Control** | 12 tools | Open/close apps, volume, brightness, screenshots, notifications |
| **Research** | 4 tools | Deep web research, URL summarization, PDF reading |
| **Documents** | 3 tools | PowerPoint generation, Markdown docs, CSV spreadsheets |
| **Communication** | 4 tools | iMessage, Reminders, Calendar events |

## 💬 Slash Commands

| Command | Description |
| :--- | :--- |
| `/help` | Show all commands |
| `/voice` | Toggle voice mode |
| `/model <name>` | Switch AI model |
| `/models` | List available models |
| `/memory` | View personal memory |
| `/remember <fact>` | Teach Jarvis about you |
| `/status` | System info (CPU, RAM, battery) |
| `/telegram` | Start Telegram bot |
| `/undo` | Undo last file change |
| `/clear` | Clear conversation |

## 🏗️ Project Structure

```
jarvis/
├── jarvis.sh              # Launch script
├── requirements.txt       # Dependencies
├── jarvis/
│   ├── agent.py           # Core Jarvis brain (agentic loop)
│   ├── api.py             # NVIDIA API client
│   ├── cli.py             # Interactive CLI
│   ├── ui.py              # Iron Man-styled terminal UI
│   ├── models.py          # Model registry
│   ├── memory.py          # Conversation persistence
│   ├── safety.py          # Safety layer
│   ├── user_memory.py     # Personal knowledge storage
│   ├── history.py         # File change tracking
│   ├── tools/
│   │   ├── coding.py      # File, shell, git, web tools
│   │   ├── desktop.py     # macOS system control
│   │   ├── research.py    # Web research & synthesis
│   │   ├── documents.py   # PPT, PDF, CSV generation
│   │   ├── communication.py # iMessage, Reminders
│   │   └── registry.py    # Unified tool dispatch
│   ├── voice/
│   │   ├── listener.py    # Speech-to-Text
│   │   ├── speaker.py     # Text-to-Speech (British voice)
│   │   └── engine.py      # Voice loop orchestrator
│   └── telegram/
│       └── bot.py         # Telegram bot for mobile
```

## 📋 Requirements

- Python 3.11+
- macOS (for desktop control & voice)
- NVIDIA API key (free from [build.nvidia.com](https://build.nvidia.com))

## License

MIT
