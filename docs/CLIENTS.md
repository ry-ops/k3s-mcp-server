# Connecting clients

The server speaks MCP over **stdio**: your client starts it as a child process with `uv run`, and it stops when the client does. Every client needs the same three things:

- **Command**: `uv --directory /absolute/path/to/k3s-mcp-server run k3s-mcp-server`
- **`KUBECONFIG`**: an absolute path to the kubeconfig it should use. Use the least-privilege one from [QUICKSTART.md](QUICKSTART.md#3-give-the-server-its-own-identity), not your admin file.
- **Optional settings**: see [Settings](#settings).

## Claude Code

```bash
claude mcp add k3s --scope user \
  -e KUBECONFIG="$HOME/.kube/k3s-mcp.yaml" \
  -e K3S_DEFAULT_NAMESPACE=demo \
  -- uv --directory /absolute/path/to/k3s-mcp-server run k3s-mcp-server
```

- `--scope user` makes it available in every project. Use `--scope project` to share it through the repo's `.mcp.json` instead.
- `claude mcp get k3s` should show `Status: ✔ Connected`. New sessions pick up the tools.
- Remove it with `claude mcp remove k3s -s user`.

## Claude Desktop

Edit the config file, creating it if it doesn't exist:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": {
        "KUBECONFIG": "/absolute/path/to/k3s-mcp.yaml",
        "K3S_DEFAULT_NAMESPACE": "demo"
      }
    }
  }
}
```

If you already have other servers, add `"k3s"` next to them inside the same `mcpServers` object. Then **quit Claude Desktop completely** (`Cmd+Q` on macOS, *Exit* from the tray on Windows) and reopen it. Closing the window isn't enough.

Use absolute paths everywhere: Claude Desktop doesn't expand `~` or `$HOME`. If it can't find `uv`, put the full path to it in `command` (`which uv`).

## Other MCP clients

Any client that launches stdio servers works. Give it the same command, arguments and environment as above.

## Several clusters

Register the server once per cluster, each with its own name and kubeconfig. They share one checkout:

```json
{
  "mcpServers": {
    "k3s-lab":  { "command": "uv", "args": ["--directory", "/path/to/k3s-mcp-server", "run", "k3s-mcp-server"],
                  "env": { "KUBECONFIG": "/path/to/lab-mcp.yaml" } },
    "k3s-prod": { "command": "uv", "args": ["--directory", "/path/to/k3s-mcp-server", "run", "k3s-mcp-server"],
                  "env": { "KUBECONFIG": "/path/to/prod-view-only.yaml" } }
  }
}
```

The name shows up in the client, so you can say *"on k3s-prod, …"*. The server uses the kubeconfig's **current context**. To reach a different context, give it a different file.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `KUBECONFIG` | `~/.kube/k3s-cortex-config.yaml` | The kubeconfig to load. If the file is missing, the server prints an error and exits at startup. Always set this; the default is a leftover name. |
| `K3S_DEFAULT_NAMESPACE` | `default` | Where single-object tools (`get_deployment`, `get_logs`, `scale_deployment`, `restart_pod`, `execute_command`, `delete_resource`) act when the call doesn't name a namespace. It's also where `apply_manifest` creates objects whose YAML has no namespace. |
| `K3S_DEBUG` | `false` | `true` logs extra startup detail to stderr. |

The list tools, `get_pods`, `get_deployments` and `get_services`, search **every namespace** when no namespace is given, whatever `K3S_DEFAULT_NAMESPACE` says.

## Troubleshooting

**Run it by hand first.** This takes the client out of the picture:

```bash
KUBECONFIG=/path/to/k3s-mcp.yaml bash scripts/test-connection.sh
```

If that passes, the problem is in the client config. If it fails, the error tells you what's wrong with the kubeconfig or the network.

| Symptom | Cause and fix |
|---|---|
| `Kubeconfig not found at …` in the client's log | `KUBECONFIG` isn't set or isn't an absolute path. Without it the server falls back to `~/.kube/k3s-cortex-config.yaml`. |
| Connection refused or timeouts | The kubeconfig's `server:` isn't reachable from this machine. K3s writes `https://127.0.0.1:6443`; change it to the node's address. Check with `nc -z <server-ip> 6443`. |
| `403 Forbidden` | RBAC working as intended: this identity isn't allowed to do that. To allow writes in another namespace, add an `edit` RoleBinding there; see [`deploy/rbac.yaml`](../deploy/rbac.yaml). |
| `409 Conflict` from `apply_manifest` | The object already exists. `apply_manifest` only creates. |
| `Unsupported resource kind` | `apply_manifest` and `delete_resource` handle Pod, Deployment and Service only. |
| `Failed to parse YAML manifest` | Send one object per `apply_manifest` call; multi-document YAML isn't supported. |
| Tools don't appear | The JSON is invalid (check with `python3 -m json.tool <file>`), a path isn't absolute, or Claude Desktop wasn't fully quit. |
| `AttributeError: 'Server' object has no attribute 'list_tools'` | An old checkout resolved `mcp` 2.x. Pull the latest code and run `uv sync`; `pyproject.toml` now pins `mcp<2`. |

**Logs.** Claude Desktop writes one log per server: `~/Library/Logs/Claude/mcp-server-k3s.log` on macOS, `%APPDATA%\Claude\logs\` on Windows. In Claude Code, run `/mcp` to see each server's status. The server writes all its own messages to stderr, so they land in these logs.
