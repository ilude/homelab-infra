#!/usr/bin/env python3
"""Apply selected sandbox, spawn-region and PvP settings while Zomboid is stopped."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


def sandbox_config(original: str, options: dict[str, object]) -> str:
    """Replace named scalar fields, retaining all other generated Lua content."""
    replacements = {}
    for key, value in options.items():
        if not isinstance(value, (bool, int, float)):
            raise ValueError(f"sandbox option {key} must be a boolean or number")
        replacements[key] = json.dumps(value, allow_nan=False)
    found: dict[str, int] = {}
    sections: list[str] = []
    result = []
    for line in original.splitlines(keepends=True):
        table = re.match(r"^\s*(\w+)\s*=\s*\{\s*$", line)
        field = re.match(r"^([ \t]*)(\w+)([ \t]*=[ \t]*)([^,\r\n]+)(,.*)$", line.rstrip("\r\n"))
        if table:
            if table[1] != "SandboxVars":
                sections.append(table[1])
        elif re.match(r"^\s*}", line):
            if sections:
                sections.pop()
        elif field:
            key = ".".join([*sections, field[2]])
            if key in replacements:
                found[key] = found.get(key, 0) + 1
                ending = line[len(line.rstrip("\r\n")):]
                line = f"{field[1]}{field[2]}{field[3]}{replacements[key]}{field[5]}{ending}"
        result.append(line)
    if any(found.get(key) != 1 for key in replacements):
        raise ValueError("requested sandbox fields must each exist exactly once")
    return "".join(result)


def spawn_config(maps_dir: Path, regions: list[str]) -> str:
    if not regions or len(set(regions)) != len(regions):
        raise ValueError("spawn regions must be nonempty and unique")
    entries = []
    for name in regions:
        if Path(name).name != name or not (maps_dir / name / "spawnpoints.lua").is_file():
            raise ValueError("spawn region must have an installed built-in spawnpoints.lua")
        label = json.dumps(name, ensure_ascii=False)
        filename = json.dumps(f"media/maps/{name}/spawnpoints.lua", ensure_ascii=False)
        entries.append(f"\t\t{{ name = {label}, file = {filename} }},\n")
    return "function SpawnRegions()\n\treturn {\n" + "".join(entries) + "\t}\nend\n"


def configured_files(base: Path, server_name: str, settings: dict) -> dict[Path, str]:
    server = base / "server-data/Server"
    candidates = {}
    if "sandbox" in settings:
        path = server / f"{server_name}_SandboxVars.lua"
        candidates[path] = sandbox_config(path.read_text(), settings["sandbox"])
    if "spawn_regions" in settings:
        path = server / f"{server_name}_spawnregions.lua"
        candidates[path] = spawn_config(base / "server-files/media/maps", settings["spawn_regions"])
    if "pvp" in settings:
        if not isinstance(settings["pvp"], bool):
            raise ValueError("pvp must be a boolean")
        path = server / f"{server_name}.ini"
        value = str(settings["pvp"]).lower()
        candidate, count = re.subn(r"(?m)^PVP=(?:true|false)$", f"PVP={value}", path.read_text())
        if count != 1:
            raise ValueError("expected exactly one existing PVP setting")
        candidates[path] = candidate
    return {path: content for path, content in candidates.items() if path.read_text() != content}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("server_name")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changes = configured_files(args.base, args.server_name, json.load(sys.stdin))
    if args.apply:
        for path, content in changes.items():
            # Preserve the generated files' existing owner and permissions.
            path.write_text(content)
    print("changed" if changes else "unchanged")


if __name__ == "__main__":
    main()
