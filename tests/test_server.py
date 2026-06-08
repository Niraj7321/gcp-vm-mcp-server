"""Tests for the GCP VM MCP server.

These mock the Compute Engine client so they run without GCP credentials
or network access.
"""

import os
from types import SimpleNamespace
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _project_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")


@pytest.fixture
def server(monkeypatch):
    # Patch the client before importing so module-level construction is mocked.
    fake_client = mock.MagicMock()
    monkeypatch.setattr(
        "google.cloud.compute_v1.InstancesClient", lambda *a, **k: fake_client
    )
    import importlib

    import server as srv

    importlib.reload(srv)
    srv._client = fake_client  # inject so _get_client() returns the mock
    return srv, fake_client


def test_require_project_missing(server, monkeypatch):
    srv, _ = server
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError):
        srv._require_project()


def test_list_instances_empty(server):
    srv, client = server
    client.aggregated_list.return_value = []
    assert "No instances found" in srv.list_instances()


def test_list_instances_formats_rows(server):
    srv, client = server
    vm = SimpleNamespace(
        name="web-1",
        status="RUNNING",
        machine_type="zones/z/machineTypes/e2-small",
        network_interfaces=[
            SimpleNamespace(
                network_i_p="10.0.0.2",
                access_configs=[SimpleNamespace(nat_i_p="34.1.2.3")],
            )
        ],
    )
    scoped = SimpleNamespace(instances=[vm])
    client.aggregated_list.return_value = [("zones/us-central1-a", scoped)]

    out = srv.list_instances()
    assert "web-1" in out
    assert "RUNNING" in out
    assert "us-central1-a" in out
    assert "34.1.2.3" in out


def test_get_instance_not_found(server):
    from google.api_core.exceptions import NotFound

    srv, client = server
    client.get.side_effect = NotFound("nope")
    assert "not found" in srv.get_instance("ghost", "us-central1-a")
