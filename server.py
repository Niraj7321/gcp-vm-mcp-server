"""GCP VM MCP Server.

A small Model Context Protocol server exposing Google Compute Engine VM
lifecycle operations as tools. Configuration is read entirely from the
environment so the code carries no project-, zone-, or host-specific values.

Auth uses Application Default Credentials. Provide them by setting
GOOGLE_APPLICATION_CREDENTIALS to a service-account key file, or by running
`gcloud auth application-default login` for local development.
"""

from __future__ import annotations

import logging
import os

from google.api_core.exceptions import GoogleAPICallError, NotFound
from google.cloud import compute_v1
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("gcp-vm-mcp")


def _require_project() -> str:
    """Return the configured GCP project id or raise a clear error."""
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        raise RuntimeError(
            "GCP_PROJECT_ID is not set. Export it (and your credentials) "
            "before starting the server."
        )
    return project


mcp = FastMCP("gcp-vm-mcp")

# The client is built lazily on first use so that importing this module (for
# tests, or to inspect tools) never requires credentials. It picks up ADC
# automatically and is reused across requests once created.
_client: compute_v1.InstancesClient | None = None


def _get_client() -> compute_v1.InstancesClient:
    global _client
    if _client is None:
        _client = compute_v1.InstancesClient()
    return _client


_firewall_client: compute_v1.FirewallsClient | None = None


def _get_firewall_client() -> compute_v1.FirewallsClient:
    global _firewall_client
    if _firewall_client is None:
        _firewall_client = compute_v1.FirewallsClient()
    return _firewall_client


def _wait(operation, project: str, zone: str | None = None) -> str:
    """Block until a Compute Engine operation finishes, returning its status."""
    try:
        operation.result(timeout=120)
    except Exception as exc:  # surfaced to the caller as a tool error string
        logger.warning("Operation did not complete cleanly: %s", exc)
        return "PENDING"
    return "DONE"


@mcp.tool()
def list_instances() -> str:
    """List every VM in the project across all zones with status and IPs."""
    project = _require_project()
    request = compute_v1.AggregatedListInstancesRequest(
        project=project, max_results=500
    )

    rows: list[str] = []
    try:
        for zone_scope, scoped in _get_client().aggregated_list(request=request):
            for vm in scoped.instances or []:
                zone = zone_scope.split("/")[-1]
                machine = vm.machine_type.split("/")[-1]
                external_ip = "none"
                for nic in vm.network_interfaces:
                    for cfg in nic.access_configs:
                        if cfg.nat_i_p:
                            external_ip = cfg.nat_i_p
                rows.append(
                    f"{vm.name}\t{vm.status}\t{zone}\t{machine}\tip={external_ip}"
                )
    except GoogleAPICallError as exc:
        return f"Error listing instances: {exc}"

    if not rows:
        return "No instances found in this project."
    return f"{len(rows)} instance(s):\n" + "\n".join(rows)


@mcp.tool()
def get_instance(name: str, zone: str) -> str:
    """Return detailed information about a single instance."""
    project = _require_project()
    try:
        vm = _get_client().get(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error fetching instance: {exc}"

    internal_ip = vm.network_interfaces[0].network_i_p if vm.network_interfaces else "none"
    external_ip = "none"
    for nic in vm.network_interfaces:
        for cfg in nic.access_configs:
            if cfg.nat_i_p:
                external_ip = cfg.nat_i_p

    return (
        f"Name: {vm.name}\n"
        f"Zone: {zone}\n"
        f"Status: {vm.status}\n"
        f"Machine type: {vm.machine_type.split('/')[-1]}\n"
        f"Internal IP: {internal_ip}\n"
        f"External IP: {external_ip}\n"
        f"Created: {vm.creation_timestamp}"
    )


@mcp.tool()
def start_instance(name: str, zone: str) -> str:
    """Start a stopped instance."""
    project = _require_project()
    try:
        op = _get_client().start(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error starting instance: {exc}"
    status = _wait(op, project, zone)
    return f"Start requested for '{name}' in '{zone}' (operation {status})."


@mcp.tool()
def stop_instance(name: str, zone: str) -> str:
    """Stop a running instance."""
    project = _require_project()
    try:
        op = _get_client().stop(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error stopping instance: {exc}"
    status = _wait(op, project, zone)
    return f"Stop requested for '{name}' in '{zone}' (operation {status})."


@mcp.tool()
def delete_instance(name: str, zone: str) -> str:
    """Permanently delete an instance. This cannot be undone."""
    project = _require_project()
    try:
        op = _get_client().delete(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error deleting instance: {exc}"
    status = _wait(op, project, zone)
    return f"Delete requested for '{name}' in '{zone}' (operation {status})."


@mcp.tool()
def list_ssh_keys(name: str, zone: str) -> str:
    """List the SSH keys currently set in an instance's metadata."""
    project = _require_project()
    try:
        vm = _get_client().get(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error fetching instance: {exc}"

    for item in vm.metadata.items:
        if item.key == "ssh-keys" and item.value:
            return f"SSH keys on '{name}':\n{item.value}"
    return f"No SSH keys set on '{name}'."


@mcp.tool()
def add_ssh_key(name: str, zone: str, username: str, public_key: str) -> str:
    """Add an SSH public key for a user to an instance.

    `public_key` is the full key line (e.g. 'ssh-ed25519 AAAA... comment').
    Existing keys are preserved; duplicates are ignored.
    """
    project = _require_project()
    client = _get_client()
    try:
        vm = client.get(project=project, zone=zone, instance=name)
    except NotFound:
        return f"Instance '{name}' not found in zone '{zone}'."
    except GoogleAPICallError as exc:
        return f"Error fetching instance: {exc}"

    entry = f"{username}:{public_key}"
    items = list(vm.metadata.items)
    ssh_item = next((i for i in items if i.key == "ssh-keys"), None)

    if ssh_item is None:
        items.append(compute_v1.Items(key="ssh-keys", value=entry))
    else:
        existing = ssh_item.value.split("\n") if ssh_item.value else []
        if entry in existing:
            return f"Key for '{username}' is already present on '{name}'."
        ssh_item.value = "\n".join([*existing, entry]) if ssh_item.value else entry

    metadata = compute_v1.Metadata(fingerprint=vm.metadata.fingerprint, items=items)
    try:
        op = client.set_metadata(
            project=project, zone=zone, instance=name, metadata_resource=metadata
        )
    except GoogleAPICallError as exc:
        return f"Error setting metadata: {exc}"
    status = _wait(op, project, zone)
    return f"Added SSH key for '{username}' to '{name}' (operation {status})."


@mcp.tool()
def list_firewall_rules() -> str:
    """List all firewall rules in the project."""
    project = _require_project()
    rows: list[str] = []
    try:
        for fw in _get_firewall_client().list(project=project):
            allowed = ",".join(
                f"{a.I_p_protocol}:{'/'.join(a.ports) if a.ports else 'all'}"
                for a in fw.allowed
            )
            sources = ",".join(fw.source_ranges) or "none"
            rows.append(f"{fw.name}\tallow={allowed}\tfrom={sources}")
    except GoogleAPICallError as exc:
        return f"Error listing firewall rules: {exc}"

    if not rows:
        return "No firewall rules found."
    return f"{len(rows)} firewall rule(s):\n" + "\n".join(rows)


@mcp.tool()
def create_firewall_rule(
    name: str, ports: list[str], source_range: str = "0.0.0.0/0"
) -> str:
    """Create a TCP-allow firewall rule for the given ports.

    `source_range` defaults to 0.0.0.0/0 (open to the internet) — narrow it for
    anything other than public services. The rule is tagged with `name` so it
    applies to instances carrying that network tag.
    """
    project = _require_project()
    firewall = compute_v1.Firewall(
        name=name,
        allowed=[compute_v1.Allowed(I_p_protocol="tcp", ports=ports)],
        source_ranges=[source_range],
        target_tags=[name],
    )
    try:
        op = _get_firewall_client().insert(
            project=project, firewall_resource=firewall
        )
    except GoogleAPICallError as exc:
        return f"Error creating firewall rule: {exc}"
    status = _wait(op, project)
    return f"Firewall rule '{name}' for ports {', '.join(ports)} (operation {status})."


@mcp.tool()
def delete_firewall_rule(name: str) -> str:
    """Delete a firewall rule by name."""
    project = _require_project()
    try:
        op = _get_firewall_client().delete(project=project, firewall=name)
    except NotFound:
        return f"Firewall rule '{name}' not found."
    except GoogleAPICallError as exc:
        return f"Error deleting firewall rule: {exc}"
    status = _wait(op, project)
    return f"Delete requested for firewall rule '{name}' (operation {status})."


if __name__ == "__main__":
    # Validate config early so misconfiguration fails loudly at startup.
    _require_project()
    mcp.run()
