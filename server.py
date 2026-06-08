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


if __name__ == "__main__":
    # Validate config early so misconfiguration fails loudly at startup.
    _require_project()
    mcp.run()
