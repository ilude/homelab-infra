#!/usr/bin/env python3
"""Check tracked files for public-safe examples and secret-looking content."""
from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_SCAFFOLD = (
    "scaffold/.env.example",
    "scaffold/terraform.tfvars",
    "scaffold/dns-records.local.json",
    "scaffold/ansible/inventory/local.yml",
    "settings.example.json",
)

ALLOWED_IPS = {
    ipaddress.ip_address(value)
    for value in (
        "1.1.1.1",
        "1.0.0.2",
        "1.1.1.2",
        "9.9.9.9",
        "149.112.112.112",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
    )
}

IPV4_RE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
IPV6_RE = re.compile(r"(?<![0-9A-Za-z_:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z_:])")
SECRET_ASSIGN_RE = re.compile(
    r"\b([A-Z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|PASS)[A-Z0-9_]*)\s*[=:]\s*([^\s#]+)"
)
TOKEN_PREFIX_RE = re.compile(r"\b(ghp_|github_pat_|glpat-|xoxb-|sk-)[A-Za-z0-9_\-]{10,}")
PRIVATE_KEY_RE = re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY")

PLACEHOLDER_MARKERS = (
    "REPLACE",
    "example.",
    "{{",
    "}}",
    "<redacted>",
    "<secret>",
    "...",
    "var.",
    "os.environ",
    "os.getenv",
    "$",
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )


def tracked_files(cwd: Path, tracked_file_list: Path | None = None) -> list[Path]:
    if tracked_file_list is None:
        result = run_git(["ls-files", "-z"], cwd)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git ls-files failed")
        raw_files = result.stdout.split("\0")
    else:
        raw_files = tracked_file_list.read_text(encoding="utf-8").splitlines()
    return [
        cwd / raw
        for raw in raw_files
        if raw and not raw.startswith("values/") and (cwd / raw).exists()
    ]


def load_path_set(path: Path | None) -> set[str]:
    if path is None:
        return set()
    return set(path.read_text(encoding="utf-8").splitlines())


def is_ignored(path: str, cwd: Path, ignored_paths: set[str] | None = None) -> bool:
    if ignored_paths is not None:
        return path in ignored_paths
    result = run_git(["check-ignore", "-q", "--", path], cwd)
    return result.returncode == 0


def validate_scaffold_contract(cwd: Path, ignored_paths: set[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in REQUIRED_SCAFFOLD:
        if not (cwd / path).is_file():
            findings.append(Finding(path, 0, "required scaffold file is missing"))
            continue
        if is_ignored(path, cwd, ignored_paths):
            findings.append(Finding(path, 0, "required scaffold file is ignored"))
    return findings


def ip_is_allowed(address: ipaddress._BaseAddress) -> bool:
    if address in ALLOWED_IPS:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(
            address in ipaddress.ip_network(network)
            for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
        )
    return address in ipaddress.ip_network("2001:db8::/32")


def scan_ips(path: str, line_number: int, line: str) -> list[Finding]:
    if "public-safety: allow-ip" in line:
        return []
    findings: list[Finding] = []
    candidates = [*IPV4_RE.findall(line), *IPV6_RE.findall(line)]
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not ip_is_allowed(address):
            findings.append(Finding(path, line_number, f"non-example IP literal {address}"))
    return findings


def secret_value_is_placeholder(value: str) -> bool:
    stripped = value.strip().strip('"\'')
    return not stripped or any(marker in stripped for marker in PLACEHOLDER_MARKERS)


def scan_secrets(path: str, line_number: int, line: str) -> list[Finding]:
    if "public-safety: allow-secret" in line:
        return []
    if re.match(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+$", line.strip()):
        return []
    findings: list[Finding] = []
    if PRIVATE_KEY_RE.search(line):
        findings.append(Finding(path, line_number, "private key material"))
    if TOKEN_PREFIX_RE.search(line):
        findings.append(Finding(path, line_number, "token-like literal"))
    for match in SECRET_ASSIGN_RE.finditer(line):
        key, value = match.groups()
        if key.upper().endswith("_RE") or key.lower().startswith("old_"):
            continue
        normalized_value = value.strip().strip('"\') ,:')
        if key in {"SECRET_KEYS"} or normalized_value in {"str", "None", "{"}:
            continue
        if not secret_value_is_placeholder(value):
            findings.append(Finding(path, line_number, f"secret-like assignment {key}=<redacted>"))
    return findings


def scan_file(path: Path, cwd: Path) -> list[Finding]:
    rel = path.relative_to(cwd).as_posix()
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings
    for line_number, line in enumerate(text.splitlines(), 1):
        sensitive_ref = "private" + "/"
        if sensitive_ref in line:
            findings.append(
                Finding(rel, line_number, "repo-local sensitive directory reference")
            )
        findings.extend(scan_ips(rel, line_number, line))
        findings.extend(scan_secrets(rel, line_number, line))
    return findings


def scan(
    cwd: Path,
    tracked_file_list: Path | None = None,
    ignored_file_list: Path | None = None,
) -> list[Finding]:
    ignored_paths = load_path_set(ignored_file_list) if ignored_file_list else None
    findings = validate_scaffold_contract(cwd, ignored_paths)
    if (cwd / "private").exists():
        findings.append(
            Finding(
                "private", 0, "repo-local private directory is not allowed; use values/"
            )
        )
    for path in tracked_files(cwd, tracked_file_list):
        findings.extend(scan_file(path, cwd))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--tracked-files", type=Path, default=None)
    parser.add_argument("--ignored-files", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        findings = scan(args.repo.resolve(), args.tracked_files, args.ignored_files)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    if findings:
        for finding in findings:
            print(finding.format(), file=sys.stderr)
        print("Public safety checks failed.", file=sys.stderr)
        return 1

    print("Public safety checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
