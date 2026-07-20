#!/usr/bin/env python3
"""Normalize legacy string relationship references in a SurrealDB export."""

from __future__ import annotations

import argparse
import mmap
import re
import shutil
from pathlib import Path

CONTENT_ENTITY_DATA_MARKER = b"-- TABLE DATA: content_entity"
LEGACY_MIGRATIONS_MARKER = b"-- TABLE: _migrations"
NEXT_TABLE_MARKER = b"-- TABLE:"
REFERENCE_PATTERNS = {
    "content_id": re.compile(rb"\bcontent_id: '(content:[A-Za-z0-9_-]+)'"),
    "entity_id": re.compile(rb"\bentity_id: '(entity:[A-Za-z0-9_-]+)'"),
}
CREATED_AT_PATTERN = re.compile(
    rb"\bcreated_at: '(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)'"
)


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
            migrations_start = data.find(LEGACY_MIGRATIONS_MARKER)
            if migrations_start < 0:
                raise ValueError("legacy _migrations table section is missing")
            migrations_end = data.find(
                NEXT_TABLE_MARKER,
                migrations_start + len(LEGACY_MIGRATIONS_MARKER),
            )
            if migrations_end < 0:
                raise ValueError("legacy _migrations table is not followed by another table")
            migrations_section = data[migrations_start:migrations_end]
            data[migrations_start:migrations_end] = bytes(
                byte if byte in (10, 13) else 32 for byte in migrations_section
            )
            counts["legacy_migrations_sections"] = 1

            section_start = data.find(CONTENT_ENTITY_DATA_MARKER)
            if section_start < 0:
                raise ValueError("content_entity data section is missing")
            section_end = data.find(NEXT_TABLE_MARKER, section_start + len(CONTENT_ENTITY_DATA_MARKER))
            if section_end < 0:
                section_end = len(data)

            for field, pattern in REFERENCE_PATTERNS.items():
                matches = list(pattern.finditer(data, section_start, section_end))
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

            created_at_matches = list(
                CREATED_AT_PATTERN.finditer(data, section_start, section_end)
            )
            counts["created_at"] = len(created_at_matches)
            if len(created_at_matches) != expected_relationships:
                raise ValueError(
                    f"created_at legacy value count {len(created_at_matches)} does not match "
                    f"expected content_entity count {expected_relationships}"
                )
            for match in created_at_matches:
                data[match.start(1) - 2] = ord("d")
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
        f"content_id:{counts['content_id']},entity_id:{counts['entity_id']},"
        f"created_at:{counts['created_at']},"
        f"legacy_migrations_sections:{counts['legacy_migrations_sections']}"
    )


if __name__ == "__main__":
    main()
