"""Resolve the private values context selected for an infrastructure run."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SITE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ValuesContextError(ValueError):
    """Raised when the selected private values context is unsafe or missing."""


@dataclass(frozen=True)
class ValuesContext:
    repo: Path
    values_root: Path
    values_dir: Path
    site: str | None = None

    def path(self, relative: str | Path) -> Path:
        """Return a path inside the selected site values directory."""
        candidate = (self.values_dir / relative).resolve()
        root = self.values_dir.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValuesContextError(f"values path escapes selected site: {relative}")
        return candidate

    @property
    def metadata_path(self) -> Path | None:
        if self.site is None:
            return None
        for name in ("site.json", "settings.json", "settings.local.json"):
            candidate = self.values_dir / name
            if candidate.is_file():
                return candidate
        return None


def _site_name(raw: str | None) -> str | None:
    if raw is None or raw.strip() == "":
        return None
    value = raw.strip()
    if not SITE_NAME_RE.fullmatch(value) or value in {".", ".."} or ".." in value:
        raise ValuesContextError("VALUES_SITE must be a simple site identifier")
    return value


def _path_from_env(repo: Path, raw: str | None) -> Path:
    if not raw:
        return repo / "values"
    value = Path(raw).expanduser()
    return value if value.is_absolute() else repo / value


def from_environment(repo: Path | None = None) -> ValuesContext:
    repository = (repo or Path(__file__).resolve().parents[1]).resolve()
    values_root = _path_from_env(repository, os.environ.get("VALUES_DIR"))
    site = _site_name(os.environ.get("VALUES_SITE"))
    values_dir = values_root

    if site is not None:
        if values_root.name == site and (values_root / "terraform.tfvars").is_file():
            values_dir = values_root
        else:
            candidates = (values_root / "sites" / site, values_root / site)
            values_dir = next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])
            if not values_dir.is_dir():
                raise ValuesContextError(f"selected values site does not exist: {site}")

    return ValuesContext(repository, values_root, values_dir, site)


def load_metadata(context: ValuesContext) -> dict[str, Any]:
    """Load and minimally validate selected site metadata."""
    path = context.metadata_path
    if context.site is None or path is None:
        return {}
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValuesContextError(f"invalid site metadata: {path}") from error
    if not isinstance(data, dict):
        raise ValuesContextError(f"site metadata must be an object: {path}")
    declared = data.get("name", context.site)
    if declared != context.site:
        raise ValuesContextError(f"site metadata name does not match VALUES_SITE: {path}")
    return data
