<div align="center">

# ☁️ GCP VM MCP Server

**Manage your Google Compute Engine VMs in natural language — straight from Claude.**

A [Model Context Protocol](https://modelcontextprotocol.io) server that turns Google Cloud
VM operations into tools any MCP client can call. List, inspect, start, stop, and delete
instances, manage SSH keys, and configure firewall rules — without leaving your chat.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP-7c3aed)](https://modelcontextprotocol.io)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Compute%20Engine-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/compute)
[![Tests](https://img.shields.io/badge/tests-9%20passing-brightgreen)](tests/)
[![Code style](https://img.shields.io/badge/code%20style-PEP%208-000000)](https://peps.python.org/pep-0008/)

</div>

---

## ✨ Highlights

- 🚀 **10 ready-to-use tools** covering the full VM lifecycle, SSH keys, and firewalls
- 🔐 **Secure by default** — credentials via Application Default Credentials, nothing hardcoded
- 🧩 **Zero-config wiring** into Claude Desktop (or any MCP client)
- 🧪 **Fully tested** — 9 mocked unit tests, no GCP account needed to run them
- 🪶 **Lightweight** — built on the idiomatic `google-cloud-compute` client

## 🛠️ Tools

| Tool | What it does |
|------|--------------|
| `list_instances` | List every VM in the project, across all zones |
| `get_instance` | Show one instance's status, IPs, and machine type |
| `start_instance` | Start a stopped instance |
| `stop_instance` | Stop a running instance |
| `delete_instance` | Permanently delete an instance |
| `list_ssh_keys` | List SSH keys set in an instance's metadata |
| `add_ssh_key` | Add an SSH public key for a user to an instance |
| `list_firewall_rules` | List all firewall rules in the project |
| `create_firewall_rule` | Open TCP ports with a new firewall rule |
| `delete_firewall_rule` | Remove a firewall rule by name |

## 📦 Installation

```bash
git clone https://github.com/Niraj7321/gcp-vm-mcp-server.git
cd gcp-vm-mcp-server

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

## ⚙️ Configuration

All settings come from the environment — copy the template and fill in your own values:

```bash
copy .env.example .env          # Windows  (cp on macOS/Linux)
```

| Variable | Required | Description |
|----------|:--------:|-------------|
| `GCP_PROJECT_ID` | ✅ | Your Google Cloud project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅* | Path to a service-account key file |
| `GCP_ZONE` | – | Default zone (informational) |
| `LOG_LEVEL` | – | `INFO` (default), `DEBUG`, etc. |

> \* Or skip the key file entirely and authenticate locally with
> `gcloud auth application-default login`.

The service account should follow **least privilege** — `Compute Instance Admin (v1)`
is typically enough for these tools.

## 🤖 Use with Claude Desktop

Add the server to `claude_desktop_config.json`
(`%APPDATA%\Claude\` on Windows, `~/Library/Application Support/Claude/` on macOS),
then fully restart Claude Desktop:

```json
{
  "mcpServers": {
    "gcp-vm": {
      "command": "C:\\path\\to\\gcp-vm-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\gcp-vm-mcp-server\\server.py"],
      "env": {
        "GCP_PROJECT_ID": "your-project-id",
        "GOOGLE_APPLICATION_CREDENTIALS": "C:\\path\\to\\service-account.json"
      }
    }
  }
}
```

Now just ask Claude:

> *"List all my VMs."*
> *"Stop the instance named `web-1` in `us-central1-a`."*
> *"Open ports 80 and 443 with a firewall rule called `web-fw`."*

## 🏃 Run standalone

```bash
python server.py
```

The server speaks MCP over stdio and waits for a client to connect — that's expected
(it won't print a prompt).

## 🧪 Testing

```bash
pip install pytest
pytest
```

Tests mock the Compute Engine client, so they run anywhere — no credentials or network
required.

## 📁 Project structure

```
gcp-vm-mcp-server/
├── server.py            # MCP server + tool definitions
├── requirements.txt
├── .env.example         # configuration template
├── .gitignore
├── README.md
└── tests/
    └── test_server.py   # mocked unit tests
```

## 🔒 Security

- Credentials are **never** committed — `.gitignore` blocks `service-account.json`, `.env`, and keys.
- `create_firewall_rule` defaults to `0.0.0.0/0` — narrow `source_range` for anything that isn't a public service.
- Grant the service account the **minimum** permissions it needs.

## 🗺️ Roadmap

- [ ] Create new instances from the chat (`create_instance`)
- [ ] Snapshot & disk management
- [ ] Resource-label filtering for `list_instances`

---

<div align="center">
<sub>Built with Python · <a href="https://modelcontextprotocol.io">Model Context Protocol</a> · Google Cloud Compute Engine</sub>
</div>
