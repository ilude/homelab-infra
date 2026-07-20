#!/usr/bin/env python3
"""Normalize legacy string relationship references in a SurrealDB export."""

from __future__ import annotations

import argparse
import mmap
import re
import shutil
from pathlib import Path

REFERENCE_PATTERNS = {
    "content_id": re.compile(rb"\bcontent_id: '(content:[A-Za-z0-9_-]+)'"),
    "entity_id": re.compile(rb"\bentity_id: '(entity:[A-Za-z0-9_-]+)'"),
}


def normalize(source: Path, destination: Path, expected_relationships: int) -> dict[str, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ")
    if expected_relationships < 0:
        raise ValueError("expected relationship count must be non-negative")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    counts: dict[str, int] = {}
    with destination.open("r+b") as output:
        with mmap.mmap(output.fileno(), 0, access=mmap.ACCESS_WRITE) as data:
            for field, pattern in REFERENCE_PATTERNS.items():
                matches = list(pattern.finditer(data))
                counts[field] = len(matches)
                if len(matches) != expected_relationships:
                    raise ValueError(
                        f"{field} legacy reference count {len(matches)} does not match "
                        f"expected content_entity count {expected_relationships}"
                    )
                for match in matches:
                    opening_quote = match.start(1) - 1
                    closing_quote = match.end(1)
                    data[opening_quote] = ord(" ")
                    data[closing_quote] = ord(" ")
            data.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expected-relationships", type=int, required=True)
    args = parser.parse_args()

    counts = normalize(args.source, args.destination, args.expected_relationships)
    print(
        "normalized_surreal_relationships="
        f"content_id:{counts['content_id']},entity_id:{counts['entity_id']}"
    )


if __name__ == "__main__":
    main()
