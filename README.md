<p align="center">
  <img src="docs/hero.svg" width="100%" alt="You ask to scale api to 5 and show its logs; scale_deployment, get_pods and get_logs run, three new api pods appear across the K3s nodes and log lines stream in.">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/tools-13-ffc61c" alt="13 tools">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-3ec7ff" alt="Python 3.10+"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-stdio-b58cff" alt="MCP"></a>
  <a href="https://k3s.io/"><img src="https://img.shields.io/badge/K3s-and%20any%20Kubernetes-ff8a1f" alt="K3s"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8b96ad" alt="MIT"></a>
</p>

<p align="center"><b>Run your Kubernetes cluster from a conversation.</b> An MCP server that gives Claude, or any MCP client, 13 tools for K3s, built on the official Kubernetes Python client and your kubeconfig. It works with any Kubernetes cluster, not just K3s.</p>

<p align="center">
  <a href="#tools">Tools</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#setup">Setup</a> ·
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## ✨ What you can ask

> *"What's running in the `shop` namespace?"*
> *"Why is the api pod crash-looping? Show me its last 100 log lines."*
> *"Scale `web` to 3 replicas."*
> *"Restart the stuck worker pod."*
> *"Run `env` inside the api container."*
> *"Apply this manifest."*
> *"Which nodes are Ready, and how much capacity do they have?"*

<a id="tools"></a>

## 🧰 Tools

<p align="center">
  <img src="docs/rbac.svg" width="100%" alt="Eight tools look and five change things. With a view role, get_pods is allowed and delete_resource gets 403 Forbidden; with an edit role on one namespace, both are allowed there.">
</p>

| | Tool | What it does |
|---|---|---|
| 👀 | `get_pods` | List pods in a namespace or all of them, with label selectors |
| 👀 | `get_deployments` · `get_deployment` | List deployments, or describe one |
| 👀 | `get_services` | List services |
| 👀 | `get_nodes` | Nodes with their resource information |
| 👀 | `get_namespaces` | All namespaces |
| 👀 | `get_logs` | A pod's logs; choose the container and how many lines to tail |
| 👀 | `get_cluster_info` | Version, nodes and namespaces at a glance |
| ✏️ | `scale_deployment` | Set a deployment's replica count |
| ✏️ | `restart_pod` | Delete a pod so its controller recreates it |
| ✏️ | `execute_command` | Run a command in a pod's container |
| ✏️ | `apply_manifest` | Create or update a Pod, Deployment or Service from YAML |
| ✏️ | `delete_resource` | Delete a Pod, Deployment or Service |

<a id="safety"></a>

## 🔒 Safety

There's **no read-only switch**. The server can do whatever the **kubeconfig** it uses is allowed to do, and five tools change things, including running commands inside containers. So:

- **Just watching?** Give it a kubeconfig for a service account bound to the built-in **`view`** ClusterRole. Writes then fail with `403 Forbidden` at the API server.
- **Hands-on?** Bind **`edit`** with a RoleBinding in the namespaces you trust it with, rather than handing it cluster-admin.
- **Keep your MCP client's tool approval on**, so you see each call before it runs.

<a id="setup"></a>

## 🚀 Setup

You need **Python 3.10+** with [`uv`](https://github.com/astral-sh/uv), and a kubeconfig for your cluster. On a K3s server it's at `/etc/rancher/k3s/k3s.yaml`; change its `server:` address to one you can reach.

```bash
git clone https://github.com/ry-ops/k3s-mcp-server && cd k3s-mcp-server
./setup.sh                                # or: uv sync
export KUBECONFIG="$HOME/.kube/config"    # see the note below
./test-connection.sh
```

> [!NOTE]
> If `KUBECONFIG` isn't set, the server looks for **`~/.kube/k3s-cortex-config.yaml`**, not the usual `~/.kube/config`. Set `KUBECONFIG` to point at your file.

| Variable | Default | What it does |
|---|---|---|
| `KUBECONFIG` | `~/.kube/k3s-cortex-config.yaml` | The kubeconfig to use. Its context and RBAC decide what the server can reach. |
| `K3S_DEFAULT_NAMESPACE` | `default` | Namespace used when a tool call doesn't name one |
| `K3S_DEBUG` | `false` | Verbose logging to stderr |

**Connect Claude Desktop.** Add this to `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or `%APPDATA%/Claude/claude_desktop_config.json` on Windows:

```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": { "KUBECONFIG": "/absolute/path/to/your/kubeconfig.yaml" }
    }
  }
}
```

Restart Claude Desktop completely. There's more in [QUICKSTART.md](QUICKSTART.md), [CLAUDE-DESKTOP-CONFIG.md](CLAUDE-DESKTOP-CONFIG.md) and [INSTALLATION-CHECKLIST.md](INSTALLATION-CHECKLIST.md).

<a id="troubleshooting"></a>

## 🩺 Troubleshooting

<details>
<summary><b>"Kubeconfig not found"</b></summary>

Set `KUBECONFIG` to an absolute path. Without it, the server looks for `~/.kube/k3s-cortex-config.yaml`.
</details>

<details>
<summary><b>Connection refused or timeouts</b></summary>

- The `server:` URL in your kubeconfig must be reachable from where the server runs.
- K3s writes `https://127.0.0.1:6443` by default; change it to the server's address.
</details>

<details>
<summary><b>403 Forbidden</b></summary>

That's RBAC working. The kubeconfig's identity isn't allowed to do that. See [Safety](#safety).
</details>

<details>
<summary><b>Tools don't show up in Claude</b></summary>

Use absolute paths, check the config is valid JSON, and quit Claude Desktop completely before reopening it. Set `K3S_DEBUG=true` and check Claude's logs.
</details>

## 🧱 Project layout

```
src/k3s_mcp_server/server.py   the server that gets packaged and installed (13 tools)
docs/                          ARCHITECTURE.md and the animations on this page
setup.sh, test-connection.sh   setup and a connection check
```

Dependencies: `mcp`, `kubernetes` (the official client) and `pyyaml`.

## 🌐 Part of Cortex

This server is one of the infrastructure tools behind the Cortex platform. See [CORTEX-INTEGRATION.md](CORTEX-INTEGRATION.md) for how it fits in, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## License

MIT. See [LICENSE](LICENSE).

<!-- org-footer -->
---

<p align="center"><sub>Part of <a href="https://github.com/ry-ops">ry-ops</a> · building the pipes between infrastructure, automation, and observability · built by <a href="https://github.com/ry-ops">ry-ops</a></sub></p>
