"""
Research Tools — deep web research, page summarization, and study aids.
Gives Jarvis the ability to research topics autonomously.
"""

import os
import re
import json
import html
import urllib.request
from pathlib import Path
from datetime import datetime


# ── Tool Definitions ─────────────────────────────────────────────────────────

RESEARCH_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Perform deep web research on a topic. Searches multiple queries, fetches top results, and compiles a structured research report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to research."},
                    "num_queries": {"type": "integer", "description": "Number of search queries to generate (default: 3)."},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_url",
            "description": "Fetch a web page and extract the key information in a concise summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch and summarize."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "Extract text content from a PDF file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the PDF file."},
                    "max_pages": {"type": "integer", "description": "Maximum number of pages to read (default: all)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_research",
            "description": "Save research notes or findings to a markdown file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the research document."},
                    "content": {"type": "string", "description": "Research content in markdown format."},
                    "output_path": {"type": "string", "description": "Where to save the file (default: ~/Desktop/research/)."},
                },
                "required": ["title", "content"],
            },
        },
    },
]


# ── Tool Implementations ─────────────────────────────────────────────────────

def _fetch_url_text(url: str, max_length: int = 8000) -> str:
    """Fetch a URL and extract text content."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")

        # Strip HTML
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_length:
            text = text[:max_length] + "..."
        return text
    except Exception as e:
        return f"(failed to fetch: {e})"


def tool_deep_research(topic: str, num_queries: int = 3) -> str:
    """Perform deep web research by running multiple searches and compiling results."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "❌ duckduckgo_search not installed. Run: pip install duckduckgo_search"

    # Generate search variations
    queries = [topic]
    if num_queries >= 2:
        queries.append(f"{topic} explained")
    if num_queries >= 3:
        queries.append(f"{topic} latest developments 2025 2026")

    all_results = []
    seen_urls = set()

    for query in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for r in results:
                url = r.get("href", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "snippet": r.get("body", ""),
                        "query": query,
                    })
        except Exception as e:
            continue

    if not all_results:
        return f"❌ No results found for: {topic}"

    # Fetch content from top results (limit to 5 to avoid timeout)
    detailed = []
    for r in all_results[:5]:
        url = r["url"]
        content = _fetch_url_text(url, max_length=3000)
        detailed.append({
            **r,
            "content": content,
        })

    # Compile research report
    report_lines = [
        f"# Research Report: {topic}",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Sources examined:** {len(detailed)}",
        f"**Search queries used:** {', '.join(queries)}",
        "",
        "---",
        "",
    ]

    for i, item in enumerate(detailed, 1):
        report_lines.append(f"## Source {i}: {item['title']}")
        report_lines.append(f"**URL:** {item['url']}")
        report_lines.append(f"**Snippet:** {item['snippet']}")
        report_lines.append("")
        report_lines.append("### Extracted Content")
        report_lines.append(item['content'][:2000])
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

    return "\n".join(report_lines)


def tool_summarize_url(url: str) -> str:
    """Fetch and return the main content of a URL."""
    text = _fetch_url_text(url, max_length=10000)
    if text.startswith("(failed"):
        return f"❌ {text}"
    return f"Content from {url}:\n\n{text}"


def tool_read_pdf(path: str, max_pages: int | None = None) -> str:
    """Extract text from a PDF file."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"❌ PDF not found: {path}"

    # Try pdftotext (poppler) first
    try:
        import subprocess
        cmd = ["pdftotext", str(p), "-"]
        if max_pages:
            cmd = ["pdftotext", "-l", str(max_pages), str(p), "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            if len(text) > 20000:
                text = text[:20000] + "\n... (truncated)"
            return f"PDF Content ({p.name}):\n\n{text}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback message
    return f"❌ Cannot read PDF. Install poppler: brew install poppler"


def tool_save_research(title: str, content: str, output_path: str = "") -> str:
    """Save research to a markdown file."""
    if not output_path:
        research_dir = Path.home() / "Desktop" / "research"
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50]
        output_path = str(research_dir / f"{safe_title}_{datetime.now().strftime('%Y%m%d')}.md")

    p = Path(output_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

    return f"✅ Research saved to {p}"


# ── Dispatch ─────────────────────────────────────────────────────────────────

RESEARCH_DISPATCH = {
    "deep_research": lambda **kw: tool_deep_research(kw.get("topic", ""), kw.get("num_queries", 3)),
    "summarize_url": lambda **kw: tool_summarize_url(kw.get("url", "")),
    "read_pdf": lambda **kw: tool_read_pdf(kw.get("path", ""), kw.get("max_pages")),
    "save_research": lambda **kw: tool_save_research(kw.get("title", ""), kw.get("content", ""), kw.get("output_path", "")),
}
