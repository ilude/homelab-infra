"""Authenticated dashboard API for guarded homelab-infra actions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _bridge(action: str, *extra: str) -> dict[str, Any]:
    repo_value = os.environ.get("HERMES_OPERATOR_REPO_PATH", "").strip()
    if not repo_value:
        raise HTTPException(status_code=503, detail="operator repository is not configured")
    repo = Path(repo_value).expanduser().resolve()
    script = repo / "scripts" / "hermes-operator.py"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="operator bridge is not installed")
    result = subprocess.run(
        [sys.executable, str(script), action, "--repo", str(repo), "--json", *extra],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=502, detail="operator bridge returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="operator bridge returned invalid data")
    return payload


@router.get("/status")
def get_status() -> dict[str, Any]:
    return _bridge("status")


@router.post("/validate")
def validate() -> dict[str, Any]:
    return _bridge("validate")


@router.post("/plan")
def plan() -> dict[str, Any]:
    return _bridge("plan")


@router.post("/apply")
async def apply(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="request body must be JSON") from error
    if not isinstance(body, dict) or body.get("confirm") != "APPLY":
        raise HTTPException(status_code=400, detail="explicit APPLY confirmation is required")
    extra = ["--approve"]
    for key, flag in (
        ("allow_destructive", "--allow-destructive"),
        ("allow_stateful_batch", "--allow-stateful-batch"),
    ):
        if body.get(key) is True:
            extra.append(flag)
    return _bridge("apply", *extra)
