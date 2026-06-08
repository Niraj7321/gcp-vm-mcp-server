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


def _vm_with_metadata(items):
    return SimpleNamespace(
        metadata=SimpleNamespace(fingerprint="fp", items=items)
    )


def test_list_ssh_keys_none(server):
    srv, client = server
    client.get.return_value = _vm_with_metadata([])
    assert "No SSH keys" in srv.list_ssh_keys("web-1", "us-central1-a")


def test_add_ssh_key_new(server, monkeypatch):
    srv, client = server
    client.get.return_value = _vm_with_metadata([])
    # set_metadata returns an operation whose .result() we stub via _wait
    monkeypatch.setattr(srv, "_wait", lambda *a, **k: "DONE")
    out = srv.add_ssh_key("web-1", "us-central1-a", "niraj", "ssh-ed25519 AAA test")
    assert "Added SSH key" in out
    assert client.set_metadata.called


def test_add_ssh_key_duplicate(server):
    srv, client = server
    existing = SimpleNamespace(key="ssh-keys", value="niraj:ssh-ed25519 AAA test")
    client.get.return_value = _vm_with_metadata([existing])
    out = srv.add_ssh_key("web-1", "us-central1-a", "niraj", "ssh-ed25519 AAA test")
    assert "already present" in out
    assert not client.set_metadata.called


def test_create_firewall_rule(server, monkeypatch):
    srv, _ = server
    fw_client = mock.MagicMock()
    monkeypatch.setattr(srv, "_get_firewall_client", lambda: fw_client)
    monkeypatch.setattr(srv, "_wait", lambda *a, **k: "DONE")
    out = srv.create_firewall_rule("web-fw", ["80", "443"])
    assert "web-fw" in out
    assert fw_client.insert.called


def test_list_firewall_rules_empty(server, monkeypatch):
    srv, _ = server
    fw_client = mock.MagicMock()
    fw_client.list.return_value = []
    monkeypatch.setattr(srv, "_get_firewall_client", lambda: fw_client)
    assert "No firewall rules" in srv.list_firewall_rules()
