# GCP VM MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
Google Compute Engine virtual-machine lifecycle operations as tools an MCP
client (e.g. Claude) can call.

Built on the idiomatic `google-cloud-compute` client and Application Default
Credentials. All environment-specific values (project, zone, credentials) come
from the environment — nothing is hardcoded.

## Tools

| Tool | Description |
|------|-------------|
| `list_instances` | List all VMs in the project across every zone |
| `get_instance` | Show details for one instance (status, IPs, machine type) |
| `start_instance` | Start a stopped instance |
| `stop_instance` | Stop a running instance |
| `delete_instance` | Permanently delete an instance |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Configure credentials and project — either set
`GOOGLE_APPLICATION_CREDENTIALS` to a service-account key, or run
`gcloud auth application-default login`:

```bash
copy .env.example .env        # then edit .env
```

## Run

```bash
python server.py
```

## Test

```bash
pip install pytest
pytest
```

## Security

- Credentials are never committed — see `.gitignore`.
- The service account should follow least privilege (Compute Instance Admin is
  usually sufficient for these tools).
