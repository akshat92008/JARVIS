#!/usr/bin/env python3
"""Fail the release when tracked source contains credential-shaped material."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

SECRET_PATTERNS = {
    "nvidia_api_key": re.compile(rb"\bnvapi-[A-Za-z0-9_-]{32,}\b"),
    "openai_api_key": re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{30,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}


def tracked_files(root: Path) -> Iterable[Path]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        yield from (
            path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts
        )
        return
    for item in completed.stdout.split(b"\0"):
        if item:
            yield root / item.decode("utf-8", errors="surrogateescape")


def scan_repository(root: Path) -> dict[str, object]:
    findings: list[dict[str, str]] = []
    scanned = 0
    for path in tracked_files(root):
        if not path.is_file() or path.stat().st_size > 10_000_000:
            continue
        scanned += 1
        content = path.read_bytes()
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append(
                    {"path": str(path.relative_to(root)), "kind": kind}
                )
    return {
        "ok": not findings,
        "files_scanned": scanned,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    report = scan_repository(args.root.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
