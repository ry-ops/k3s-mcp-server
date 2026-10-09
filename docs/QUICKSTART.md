# Quickstart

From a fresh clone to Claude listing your nodes. Most of the time goes to step 3.

You need:

- **Python 3.10+** and [`uv`](https://github.com/astral-sh/uv)
- A **K3s cluster** (or any Kubernetes cluster) whose API server, port `6443`, you can reach from this machine
- **Admin access** to the cluster once, to create the server's own identity. `kubectl` on your machine is easiest; the `kubectl` that ships with K3s on a server node works too.

## 1. Install

```bash
git clone https://github.com/ry-ops/k3s-mcp-server && cd k3s-mcp-server
bash scripts/setup.sh        # checks uv, runs uv sync
```

`uv sync` on its own does the same install.

## 2. Get an admin kubeconfig

On a K3s server node the admin kubeconfig is `/etc/rancher/k3s/k3s.yaml`. Copy it to your machine and point it at the node's address, because K3s writes `127.0.0.1`:

```bash
scp root@<server-ip>:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-admin.yaml
sed -i.bak 's/127.0.0.1/<server-ip>/' ~/.kube/k3s-admin.yaml && rm ~/.kube/k3s-admin.yaml.bak
chmod 600 ~/.kube/k3s-admin.yaml
export KUBECONFIG=~/.kube/k3s-admin.yaml
kubectl get nodes
```

This file is **cluster-admin**. Use it to set things up, not as the server's kubeconfig.

## 3. Give the server its own identity

The server can do anything its kubeconfig allows, including deleting resources and running commands inside pods. [`deploy/rbac.yaml`](../deploy/rbac.yaml) creates a `k3s-mcp` service account that can read across the cluster but write only in the namespaces you choose.

1. Open `deploy/rbac.yaml` and set the `namespace` of the `k3s-mcp-edit` RoleBinding (at the bottom) to the namespace you want the server to change. Copy the block for more namespaces, or delete it for read-only.
2. Follow the commands in the README's [Safety](../README.md#safety) section. They apply the file and write `~/.kube/k3s-mcp.yaml`, a kubeconfig that holds only the service account's token.

## 4. Check the connection

```bash
export KUBECONFIG=~/.kube/k3s-mcp.yaml
bash scripts/test-connection.sh
```

It loads the server's own client and reads the cluster through it. You should see:

```
✓ Connected to cluster
  Version: v1.36.5+k3s1
  Nodes: 3/3 Ready
✓ Listed 3 nodes
✓ Listed 7 namespaces
✓ Listed 17 pods across all namespaces
✓ All tests passed!
```

## 5. Connect Claude

**Claude Code**: one command, available in every project:

```bash
claude mcp add k3s --scope user \
  -e KUBECONFIG="$HOME/.kube/k3s-mcp.yaml" \
  -- uv --directory "$PWD" run k3s-mcp-server
claude mcp get k3s           # Status: ✔ Connected
```

**Claude Desktop**: see [CLIENTS.md](CLIENTS.md#claude-desktop).

Start a new session so the tools load.

## 6. Try it

Each of these maps onto one or two of the 32 tools:

| Ask | Tool |
|---|---|
| *"Which nodes are Ready, and what are they running?"* | `get_nodes` |
| *"Switch to the lab2 cluster."* | `use_cluster` (see [CLIENTS.md](CLIENTS.md#several-clusters)) |
| *"What's running in the `demo` namespace?"* | `get_pods` |
| *"Show pods labelled `app=web`."* | `get_pods` with a label selector |
| *"Describe the `web` deployment."* | `get_deployment` |
| *"Show the last 50 log lines from the api pod."* | `get_pods`, then `get_logs` |
| *"Why is the worker pod crash-looping?"* | `describe_pod`, then `get_logs` with `previous` |
| *"Any warnings in `demo` lately?"* | `get_events` |
| *"Did last night's backup job succeed?"* | `get_cronjobs`, then `get_jobs` |
| *"Which hostnames route to the `web` service?"* | `get_ingresses` |
| *"Are any volume claims stuck Pending?"* | `get_pvcs` |
| *"Which nodes are busiest?"* | `get_resource_usage` |
| *"Scale `web` to 3 replicas."* | `scale_deployment` |
| *"Restart the stuck worker pod."* | `restart_pod` |
| *"Run `df -h` in the api container."* | `execute_command` |
| *"Apply this YAML: …"* (one or more documents) | `apply_manifest` |
| *"Dry-run this change first."* | `apply_manifest` with `dry_run` |
| *"Delete the old `report` CronJob."* | `delete_resource` |
| *"Restart `web` and tell me when it's done."* | `rollout_restart`, then `rollout_status` with `wait_seconds` |
| *"That deploy broke things; roll it back."* | `rollout_history`, then `rollout_undo` |
| *"Which Helm charts did K3s install?"* | `get_resource` with kind `HelmChart` (needs read access to that CRD) |

Writes outside the namespaces you gave `edit` come back as `403 Forbidden`. That's the RBAC from step 3 doing its job.

### What it can't do

- **Read Secrets.** No tool does, on purpose: their values would end up in the conversation.
- **Follow logs.** `get_logs` returns the last *N* lines (100 by default).
- **Drain nodes.** `cordon_node` stops new pods landing on a node, but moving running pods off it is up to you.
- **Roll back StatefulSets or DaemonSets.** `rollout_undo` handles Deployments only.

## Checklist

- [ ] `uv sync` (or `bash scripts/setup.sh`) completes
- [ ] The admin kubeconfig's `server:` is the node's address, not `127.0.0.1`
- [ ] `deploy/rbac.yaml` applied, with `edit` only where you want writes
- [ ] `~/.kube/k3s-mcp.yaml` written, mode `600`
- [ ] `bash scripts/test-connection.sh` passes with that kubeconfig
- [ ] Your client shows `k3s` as connected and lists 32 tools
- [ ] A read works, and a write outside your `edit` namespaces returns `403`

Stuck? See [CLIENTS.md → Troubleshooting](CLIENTS.md#troubleshooting).
