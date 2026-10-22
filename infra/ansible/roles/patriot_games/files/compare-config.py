#!/usr/bin/env python3
"""Compare complete rendered Zomboid configs without game-generated comments/spacing."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re
import sys


# Quoted strings precede comments so comment markers inside strings remain data.
LUA_LEXEMES = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|--[^\n]*|\s+|'
    r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[A-Za-z_][A-Za-z_0-9]*|.',
    re.DOTALL,
)


def normalized(content: str, suffix: str) -> object:
    if suffix == ".ini":
        return sorted(
            line.split("=", 1) for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    tokens = []
    for token in LUA_LEXEMES.findall(content):
        if token.isspace() or token.startswith("--"):
            continue
        if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', token):
            tokens.append(Decimal(token))
        else:
            tokens.append(token)
    return tokens


def differs(directory: Path, configs: dict[str, str]) -> bool:
    for filename, desired in configs.items():
        path = directory / filename
        if not path.exists() or normalized(path.read_text(), path.suffix) != normalized(desired, path.suffix):
            return True
    return False


if __name__ == "__main__":
    print("changed" if differs(Path(sys.argv[1]), json.load(sys.stdin)) else "unchanged")
