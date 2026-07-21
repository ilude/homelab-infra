#!/usr/bin/env python3
"""Normalize legacy string relationship references in a SurrealDB export."""

from __future__ import annotations

import argparse
import json
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
SCHEMA_PATTERN = re.compile(rb"(?m)^DEFINE [^\r\n]*;\r?$")
RELATIONSHIP_OBJECT_PATTERN = re.compile(rb"\{[^{}]+\}")
RELATIONSHIP_FIELD_PATTERNS = {
    "id": re.compile(rb"\bid: (content_entity:[A-Za-z0-9_-]+)"),
    "content_id": re.compile(rb"\bcontent_id: '(content:[A-Za-z0-9_-]+)'"),
    "entity_id": re.compile(rb"\bentity_id: '(entity:[A-Za-z0-9_-]+)'"),
    "edge_type": re.compile(rb"\bedge_type: '([^']+)'"),
    "created_at": CREATED_AT_PATTERN,
    "confidence": re.compile(rb"\bconfidence: ([0-9.]+)f"),
}


def blank_non_newline(data: mmap.mmap, start: int, end: int) -> None:
    section = data[start:end]
    data[start:end] = bytes(byte if byte in (10, 13) else 32 for byte in section)


def parse_relationship_rows(
    data: mmap.mmap, section_start: int, section_end: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in RELATIONSHIP_OBJECT_PATTERN.finditer(data, section_start, section_end):
        raw = match.group()
        fields: dict[str, str] = {}
        for name, pattern in RELATIONSHIP_FIELD_PATTERNS.items():
            field_match = pattern.search(raw)
            if field_match is None:
                raise ValueError(f"content_entity row is missing {name}")
            fields[name] = field_match.group(1).decode("utf-8")
        rows.append({"start": match.start(), "end": match.end(), **fields})
    return rows


def select_duplicate_rows(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (
            str(row["content_id"]),
            str(row["entity_id"]),
            str(row["edge_type"]),
        )
        grouped.setdefault(key, []).append(row)

    dropped_rows: list[dict[str, object]] = []
    audit: list[dict[str, str]] = []
    for key, candidates in grouped.items():
        ranked = sorted(
            candidates,
            key=lambda row: (
                -float(str(row["confidence"])),
                str(row["created_at"]),
                str(row["id"]),
            ),
        )
        kept = ranked[0]
        for dropped in ranked[1:]:
            dropped_rows.append(dropped)
            audit.append(
                {
                    "content_id": key[0],
                    "entity_id": key[1],
                    "edge_type": key[2],
                    "kept_id": str(kept["id"]),
                    "dropped_id": str(dropped["id"]),
                }
            )
    return dropped_rows, audit


def blank_array_object(data: mmap.mmap, start: int, end: int, section_end: int) -> None:
    following = end
    while following < section_end and data[following] in b" \t\r\n":
        following += 1
    if following < section_end and data[following] == ord(","):
        blank_non_newline(data, start, following + 1)
        return

    preceding = start - 1
    while preceding >= 0 and data[preceding] in b" \t\r\n":
        preceding -= 1
    if preceding < 0 or data[preceding] != ord(","):
        raise ValueError("cannot locate content_entity row delimiter")
    blank_non_newline(data, preceding, end)


def normalize(source: Path, destination: Path, expected_relationships: int) -> dict[str, object]:
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ")
    if expected_relationships < 0:
        raise ValueError("expected relationship count must be non-negative")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    counts: dict[str, int] = {}
    with destination.open("r+b") as output:
        with mmap.mmap(output.fileno(), 0, access=mmap.ACCESS_WRITE) as data:
            schema_matches = list(SCHEMA_PATTERN.finditer(data))
            if not schema_matches:
                raise ValueError("Surreal export contains no schema definitions")
            for match in schema_matches:
                blank_non_newline(data, match.start(), match.end())
            counts["schema_definitions_removed"] = len(schema_matches)

            migrations_start = data.find(LEGACY_MIGRATIONS_MARKER)
            if migrations_start < 0:
                raise ValueError("legacy _migrations table section is missing")
            migrations_end = data.find(
                NEXT_TABLE_MARKER,
                migrations_start + len(LEGACY_MIGRATIONS_MARKER),
            )
            if migrations_end < 0:
                raise ValueError("legacy _migrations table is not followed by another table")
            blank_non_newline(data, migrations_start, migrations_end)
            counts["legacy_migrations_sections"] = 1

            section_start = data.find(CONTENT_ENTITY_DATA_MARKER)
            if section_start < 0:
                raise ValueError("content_entity data section is missing")
            section_end = data.find(NEXT_TABLE_MARKER, section_start + len(CONTENT_ENTITY_DATA_MARKER))
            if section_end < 0:
                section_end = len(data)

            relationship_rows = parse_relationship_rows(data, section_start, section_end)
            if len(relationship_rows) != expected_relationships:
                raise ValueError(
                    f"content_entity row count {len(relationship_rows)} does not match "
                    f"expected count {expected_relationships}"
                )
            dropped_rows, duplicate_audit = select_duplicate_rows(relationship_rows)
            counts["content_entity_raw"] = len(relationship_rows)
            counts["content_entity_unique"] = len(relationship_rows) - len(dropped_rows)
            counts["content_entity_dropped"] = len(dropped_rows)
            counts["duplicate_audit"] = duplicate_audit

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
            for row in dropped_rows:
                blank_array_object(
                    data,
                    int(row["start"]),
                    int(row["end"]),
                    section_end,
                )
            data.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expected-relationships", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    counts = normalize(args.source, args.destination, args.expected_relationships)
    report = {
        "policy": "highest_confidence_then_earliest_created_at_then_lowest_id",
        "content_entity": {
            "raw_count": counts["content_entity_raw"],
            "unique_count": counts["content_entity_unique"],
            "dropped_count": counts["content_entity_dropped"],
            "dropped": counts["duplicate_audit"],
        },
        "schema_definitions_removed": counts["schema_definitions_removed"],
        "legacy_migrations_sections_removed": counts["legacy_migrations_sections"],
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.report.chmod(0o600)
    print(
        "normalized_surreal_relationships="
        f"content_id:{counts['content_id']},entity_id:{counts['entity_id']},"
        f"created_at:{counts['created_at']},"
        f"legacy_migrations_sections:{counts['legacy_migrations_sections']},"
        f"schema_definitions_removed:{counts['schema_definitions_removed']},"
        f"content_entity_unique:{counts['content_entity_unique']},"
        f"content_entity_dropped:{counts['content_entity_dropped']}"
    )


if __name__ == "__main__":
    main()
