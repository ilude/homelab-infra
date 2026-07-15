#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ClusterError(RuntimeError):
    pass


def api_call(
    api_url: str,
    path: str,
    params: dict[str, str],
    token: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        data=urllib.parse.urlencode(params).encode(),
        headers=headers,
        method="POST",
    )
    context = ssl._create_unverified_context() if api_url.startswith("https://") else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ClusterError(f"Technitium API request failed for {path}") from error
    if result.get("status") != "ok":
        raise ClusterError(f"Technitium API returned {result.get('status', 'unknown')} for {path}")
    return result


def cluster_state(api_url: str, token: str) -> dict[str, Any]:
    return api_call(api_url, "/admin/cluster/state", {"includeServerIpAddresses": "true"}, token)["response"]


def login(api_url: str, username: str, password: str) -> str:
    result = api_call(api_url, "/user/login", {"user": username, "pass": password})
    token = result.get("token")
    if not isinstance(token, str) or not token:
        raise ClusterError("Technitium login returned no token")
    return token


def cluster_nodes(state: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = state.get("clusterNodes", state.get("nodes", []))
    if not isinstance(nodes, list):
        raise ClusterError("Technitium cluster state contains an invalid node list")
    return [node for node in nodes if isinstance(node, dict)]


def self_node(state: dict[str, Any]) -> dict[str, Any]:
    for node in cluster_nodes(state):
        if node.get("state") == "Self":
            return node
    raise ClusterError("Technitium cluster state contains no self node")


def normalized_addresses(node: dict[str, Any]) -> set[str]:
    addresses = node.get("ipAddresses")
    if isinstance(addresses, list):
        return {str(address) for address in addresses}
    address = node.get("ipAddress")
    return {str(address)} if address else set()


def ensure_node_address(
    api_url: str, token: str, state: dict[str, Any], address: str
) -> tuple[dict[str, Any], bool]:
    if normalized_addresses(self_node(state)) == {address}:
        return state, False
    updated = api_call(
        api_url, "/admin/cluster/updateIpAddress", {"ipAddresses": address}, token
    )["response"]
    return updated, True


def initialize_primary(
    api_url: str, token: str, domain: str, address: str
) -> tuple[dict[str, Any], bool]:
    state = cluster_state(api_url, token)
    if not state.get("clusterInitialized"):
        initialized = api_call(
            api_url,
            "/admin/cluster/init",
            {"clusterDomain": domain, "primaryNodeIpAddresses": address},
            token,
        )["response"]
        return initialized, True
    if state.get("clusterDomain") != domain:
        raise ClusterError("Existing Technitium cluster domain does not match requested domain")
    return ensure_node_address(api_url, token, state, address)


def secondary_token(api_url: str, shared_token: str) -> tuple[str, dict[str, Any] | None]:
    try:
        state = cluster_state(api_url, shared_token)
        return shared_token, state
    except ClusterError:
        token = login(api_url, "admin", "admin")
        return token, None


def ensure_secondary(
    secondary_api_url: str,
    shared_token: str,
    primary_state: dict[str, Any],
    primary_address: str,
    secondary_address: str,
    domain: str,
    primary_username: str,
    primary_password: str,
) -> bool:
    token, state = secondary_token(secondary_api_url, shared_token)
    if state is not None and state.get("clusterInitialized"):
        if state.get("clusterDomain") != domain:
            raise ClusterError("Secondary Technitium cluster domain does not match requested domain")
        _, changed = ensure_node_address(secondary_api_url, token, state, secondary_address)
        return changed

    primary_url = self_node(primary_state).get("url")
    if not isinstance(primary_url, str) or not primary_url.startswith("https://"):
        raise ClusterError("Primary Technitium cluster did not publish a native HTTPS URL")
    api_call(
        secondary_api_url,
        "/admin/cluster/initJoin",
        {
            "secondaryNodeIpAddresses": secondary_address,
            "primaryNodeUrl": primary_url,
            "primaryNodeIpAddress": primary_address,
            "ignoreCertificateErrors": "true",
            "primaryNodeUsername": primary_username,
            "primaryNodePassword": primary_password,
        },
        token,
        timeout=300,
    )
    return True


def verify_cluster(primary_api_url: str, secondary_api_url: str, token: str, domain: str) -> None:
    for _ in range(20):
        primary = cluster_state(primary_api_url, token)
        secondary = cluster_state(secondary_api_url, token)
        primary_nodes = cluster_nodes(primary)
        secondary_nodes = cluster_nodes(secondary)
        if (
            primary.get("clusterDomain") == domain
            and secondary.get("clusterDomain") == domain
            and len(primary_nodes) == 2
            and len(secondary_nodes) == 2
            and any(node.get("state") == "Connected" for node in primary_nodes)
            and any(node.get("state") == "Connected" for node in secondary_nodes)
        ):
            return
        time.sleep(3)
    raise ClusterError("Technitium cluster nodes did not reach connected state")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--primary-ip", required=True)
    parser.add_argument("--secondary-ip", required=True)
    args = parser.parse_args()

    token = os.environ["TECHNITIUM_API_TOKEN"]
    username = os.environ["TECHNITIUM_ADMIN_USER"]
    password = os.environ["TECHNITIUM_ADMIN_PASSWORD"]
    primary_api_url = f"http://{args.primary_ip}:5380/api"
    secondary_api_url = "http://127.0.0.1:5380/api"

    primary_state, primary_changed = initialize_primary(
        primary_api_url, token, args.domain, args.primary_ip
    )
    secondary_changed = ensure_secondary(
        secondary_api_url,
        token,
        primary_state,
        args.primary_ip,
        args.secondary_ip,
        args.domain,
        username,
        password,
    )
    verify_cluster(primary_api_url, secondary_api_url, token, args.domain)
    prefix = "changed" if primary_changed or secondary_changed else "unchanged"
    print(f"{prefix}: Technitium cluster is initialized and connected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
