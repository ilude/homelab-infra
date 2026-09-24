#!/usr/bin/env python3
"""Redact likely credentials from bounded Onclave core logs."""

from __future__ import annotations

import re
import sys

PATTERNS = (
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)(?:basic|bearer)?\s*[^\s,}]+"),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"""(?i)((?:["']?)(?:password|passwd|secret|token|api[_-]?key|"""
            r"""access[_-]?key|private[_-]?key)["']?\s*[:=]\s*["']?)"""
            r"""[^\s,}"']+"""
        ),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"(?i)\b(?:amqp|postgres(?:ql)?|redis|https?)://"
            r"[^\s/@:]+:[^\s/@]+@"
        ),
        "<redacted-credentials>@",
    ),
    (
        re.compile(
            r"(?i)(https?://[^\s/?]+[^\s]*[?&]"
            r"(?:token|key|secret|password)=[^&\s]+)"
        ),
        "<redacted-url>",
    ),
    (
        re.compile(
            r"\beyJ[a-zA-Z0-9_-]{20,}\."
            r"[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"
        ),
        "<redacted-jwt>",
    ),
)
MAX_LINES = 200
MAX_LINE_LENGTH = 4096


def redact(text: str) -> str:
    result = text[: MAX_LINES * MAX_LINE_LENGTH]
    for pattern, replacement in PATTERNS:
        result = pattern.sub(replacement, result)
    lines = result.splitlines()[:MAX_LINES]
    return "\n".join(line[:MAX_LINE_LENGTH] for line in lines)


if __name__ == "__main__":
    sys.stdout.write(redact(sys.stdin.read()))
    if not sys.stdin.closed:
        sys.stdout.write("\n")
