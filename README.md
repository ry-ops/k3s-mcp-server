<p align="center">
  <img src="docs/hero.svg" width="100%" alt="You ask to scale api to 5 and show its logs; scale_deployment, get_pods and get_logs run, three new api pods appear across the K3s nodes and log lines stream in.">
</p>

<p align="center">
  <a href="https://github.com/ry-ops/k3s-mcp-server/releases/latest"><img src="https://img.shields.io/github/v/release/ry-ops/k3s-mcp-server?color=3fd68b" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/tools-36-ffc61c" alt="36 tools">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-3ec7ff" alt="Python 3.10+"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-stdio-b58cff" alt="MCP"></a>
  <a href="https://k3s.io/"><img src="https://img.shields.io/badge/K3s-and%20any%20Kubernetes-ff8a1f" alt="K3s"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8b96ad" alt="MIT"></a>
</p>

<p align="center"><b>Run your Kubernetes cluster from a conversation.</b> An MCP server that gives Claude, or any MCP client, 36 tools for K3s, built on the official Kubernetes Python client and your kubeconfig. It works with any Kubernetes cluster, not just K3s.</p>

<p align="center">
  <a href="#tools">Tools</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#setup">Setup</a> ·
  <a href="#guides">Guides</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="#upcoming">Upcoming</a>
</p>

---

## ✨ What you can ask

> *"What's running in the `shop` namespace?"*
> *"Why is the api pod crash-looping? Show me its restarts and last 100 log lines."*
> *"Which pods are labelled `app=web`, and which nodes are they on?"*
> *"Scale `web` to 3 replicas."*
> *"Restart the stuck worker pod."*
> *"Run `env` inside the api container."*
> *"Create this deployment."* (paste the YAML)
> *"Which nodes are Ready, and how much capacity do they have?"*

## 🌟 Why this one

- **Reads and writes, 36 tools.** Workloads (deployments, StatefulSets, DaemonSets, Jobs, CronJobs), networking (services, ingresses), config and storage (ConfigMaps, volume claims), nodes, logs and any custom resource to look; scale, restart, roll out, roll back, exec, apply, delete and cordon to act.
- **Safe rollouts.** Restart a workload with a rolling update, watch it finish, see each revision's images, and roll a bad deploy back. A rollout stuck on a bad image is reported as failed, not left hanging.
- **Built for troubleshooting.** Events, a pod's container states and exit codes, logs from the crashed container, and live CPU and memory from metrics-server, so *"why is this pod crash-looping?"* gets a real answer.
- **Apply like kubectl.** `apply_manifest` uses server-side apply: it creates or updates, takes several YAML documents at once, handles any kind including custom resources, and has a dry run. `delete_resource` takes any kind too, with its own dry run.
- **Least privilege, ready to apply.** [`deploy/rbac.yaml`](deploy/rbac.yaml) gives the server its own service account: it can read everywhere, write only in the namespaces you pick, and never read Secrets outside them. Delete one Secret to cut it off.
- **Cluster-wide by default.** List tools search every namespace unless you name one, and label selectors narrow them down.
- **Builds clusters too.** With [proxmox-mcp-server](https://github.com/ry-ops/proxmox-mcp-server) making the VMs, `create_cluster` turns them into a K3s cluster over SSH and hands it a scoped identity; join tokens and kubeconfigs never enter the conversation. Opt-in: see [PROVISIONING.md](docs/PROVISIONING.md).
- **Any client, any number of clusters.** Works with Claude Code, Claude Desktop or any stdio MCP client. Drop scoped kubeconfigs in `~/.kube/clusters/` and switch with *"use lab2"*, no restart; every result names the cluster it came from.
- **Checks itself first.** `scripts/test-connection.sh` runs the server's own client against your cluster before you connect a client.
- **Small enough to read.** One Python module on the official Kubernetes client, with no database, no daemon and no state. [ARCHITECTURE.md](docs/ARCHITECTURE.md) maps every tool to its API call and the RBAC it needs.

<a id="tools"></a>

## 🧰 Tools

<p align="center">
  <img src="docs/rbac.svg" width="100%" alt="Twenty-one tools look and nine change things. With a view role, get_pods is allowed and delete_resource gets 403 Forbidden; with an edit role on one namespace, both are allowed there.">
</p>

| | Tool | What it does |
|---|---|---|
| 👀 | `get_pods` | Pods in one namespace or all of them, filtered by label, with status, node, IPs and restart counts |
| 👀 | `get_deployments` · `get_deployment` | Deployments in one namespace or all of them, or the details of one |
| 👀 | `get_statefulsets` · `get_daemonsets` | StatefulSets and DaemonSets with replica or scheduling counts and images |
| 👀 | `get_jobs` · `get_cronjobs` | Jobs with their outcome and failure reason; CronJobs with schedule and last runs |
| 👀 | `get_services` | Services in one namespace or all of them |
| 👀 | `get_ingresses` | Ingresses with hosts, paths, backend services, TLS hosts and addresses |
| 👀 | `get_configmaps` | ConfigMaps and their keys, or one ConfigMap's data |
| 👀 | `get_pvcs` | Volume claims with status, size, storage class and bound volume |
| 👀 | `get_nodes` | Nodes with roles, Ready and pressure conditions, versions, OS and capacity |
| 👀 | `get_namespaces` | All namespaces |
| 👀 | `get_logs` | A pod's logs; choose the container and how many lines to tail, or read the previous (crashed) container's logs |
| 👀 | `get_events` | Events, newest first, filtered by namespace, object, kind or `Warning` |
| 👀 | `describe_pod` | A pod's conditions, container states, restarts, last exit code and reason, resources and recent events (no environment variables) |
| 👀 | `get_resource_usage` | CPU and memory for pods or nodes from metrics-server, nodes as a percent of allocatable |
| 👀 | `get_cluster_info` | Version, nodes and namespaces at a glance |
| 🏗️ | `list_distributions` · `cluster_status` | Distributions it can build and their K3s versions; a cluster's nodes and Ready state without switching to it |
| 🏗️ | `plan_cluster` · `create_cluster` | Check nodes over SSH, then build a K3s cluster and write its admin and scoped kubeconfigs. **Opt-in** with `K3S_PROVISIONING=true` |
| 🔀 | `list_clusters` · `use_cluster` | The clusters in your kubeconfig folder and which is active; switch to another without a restart. Admin kubeconfigs (`*-admin.yaml`) are never offered. |
| 👀 | `get_resource` | Any kind, including custom resources (K3s `HelmChart`s, Traefik `IngressRoute`s, cert-manager `Certificate`s): list with Ready status, or one whole object. Secrets are refused. |
| 👀 | `rollout_status` | Whether a Deployment, StatefulSet or DaemonSet has finished rolling out; can wait for it |
| 👀 | `rollout_history` | A deployment's revisions with images and change cause |
| ✏️ | `scale_deployment` | Set a deployment's replica count |
| ✏️ | `restart_pod` | Delete a pod so its controller recreates it |
| ✏️ | `execute_command` | Run a command in a pod's container |
| ✏️ | `apply_manifest` | Server-side apply of YAML: create or update any kind, several documents at once, with dry run and conflict reporting |
| ✏️ | `delete_resource` | Delete an object of any kind, by kind or short name (`deploy`, `cm`, `pvc`), with dry run |
| ✏️ | `rollout_restart` | Restart a Deployment, StatefulSet or DaemonSet with a rolling update |
| ✏️ | `rollout_undo` | Roll a deployment back to the previous revision or a chosen one |
| ✏️ | `cordon_node` · `uncordon_node` | Stop or resume scheduling new pods on a node (opt-in RBAC, below) |

<a id="safety"></a>

## 🔒 Safety

There's **no read-only switch**. The server can do whatever the **kubeconfig** it uses is allowed to do, and nine tools change things, including running commands inside containers. So don't hand it cluster-admin. [`deploy/rbac.yaml`](deploy/rbac.yaml) sets up a service account that can:

- **Read** across the cluster (the built-in **`view`** role, plus nodes). It can't read Secrets.
- **Write** only in the namespaces you give an **`edit`** RoleBinding. The file binds `default`; change it, copy the block for more namespaces, or delete it for read-only. Writes anywhere else fail with `403 Forbidden` at the API server.
- **Custom resources** only if their CRD opts in. `view` and `edit` include a custom resource only when its ClusterRoles aggregate into them, and many CRDs, Traefik's among them, don't. Grant those kinds with your own Role if you want the server to manage them.
- **Building clusters** is off by default. `plan_cluster` and `create_cluster` run commands as root over SSH with your key, which RBAC can't limit, so they only appear with `K3S_PROVISIONING=true`. See [PROVISIONING.md](docs/PROVISIONING.md).
- **Nodes** stay read-only. `cordon_node` and `uncordon_node` need [`deploy/rbac-node-ops.yaml`](deploy/rbac-node-ops.yaml), an opt-in extra that lets the server patch nodes cluster-wide.

Apply it with your admin kubeconfig, then build a kubeconfig for the server from the service account's token:

```bash
kubectl apply -f deploy/rbac.yaml

SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CA=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
TOKEN=$(kubectl -n k3s-mcp get secret k3s-mcp-token -o jsonpath='{.data.token}' | base64 --decode)

umask 077
cat > ~/.kube/k3s-mcp.yaml <<EOF
apiVersion: v1
kind: Config
clusters:
- name: k3s
  cluster: {server: $SERVER, certificate-authority-data: $CA}
users:
- name: k3s-mcp
  user: {token: $TOKEN}
contexts:
- name: k3s-mcp
  context: {cluster: k3s, user: k3s-mcp, namespace: default}
current-context: k3s-mcp
EOF
```

Point `KUBECONFIG` at `~/.kube/k3s-mcp.yaml`. To revoke access, delete the token: `kubectl -n k3s-mcp delete secret k3s-mcp-token`.

**Keep your MCP client's tool approval on**, so you see each call before it runs.

<a id="setup"></a>

## 🚀 Setup

You need **Python 3.10+** with [`uv`](https://github.com/astral-sh/uv), and a cluster whose API server you can reach. [QUICKSTART.md](docs/QUICKSTART.md) walks through every step, including getting the kubeconfig off a K3s node.

```bash
git clone https://github.com/ry-ops/k3s-mcp-server && cd k3s-mcp-server
bash scripts/setup.sh                            # or: uv sync
export KUBECONFIG="$HOME/.kube/k3s-mcp.yaml"     # the scoped kubeconfig from Safety
bash scripts/test-connection.sh
```

**Connect Claude Code** in one command, available in every project:

```bash
claude mcp add k3s --scope user -e KUBECONFIG="$HOME/.kube/k3s-mcp.yaml" \
  -- uv --directory "$PWD" run k3s-mcp-server
```

**Or Claude Desktop.** Add this to `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows, then quit and reopen the app:

```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": { "KUBECONFIG": "/absolute/path/to/k3s-mcp.yaml" }
    }
  }
}
```

[CLIENTS.md](docs/CLIENTS.md) covers other clients and running several clusters side by side.

**To build clusters too,** add `K3S_PROVISIONING=true`. It's off by default because `plan_cluster` and `create_cluster` run root commands over SSH with your key, which no kubeconfig's RBAC can limit:

```bash
claude mcp add k3s --scope user -e KUBECONFIG="$HOME/.kube/k3s-mcp.yaml" -e K3S_PROVISIONING=true \
  -- uv --directory "$PWD" run k3s-mcp-server
```

The server tells your client on connect whether cluster building is on, so if you ask for a cluster while it's off, Claude explains how to turn it on instead of trying another way. [PROVISIONING.md](docs/PROVISIONING.md) has the full workflow with proxmox-mcp-server.

| Variable | Default | What it does |
|---|---|---|
| `KUBECONFIG` | `~/.kube/config` | The kubeconfig to use; its current context and RBAC decide what the server can reach. Point it at the scoped kubeconfig from [Safety](#safety), not your admin one. |
| `K3S_DEFAULT_NAMESPACE` | `default` | Where single-object tools act when a call doesn't name a namespace. List tools search all namespaces instead. |
| `K3S_KUBECONFIG_DIR` | `~/.kube/clusters` | A folder of kubeconfigs that `use_cluster` switches between, and where `create_cluster` writes new ones. Files ending in `-admin.yaml` are skipped. |
| `K3S_PROVISIONING` | `false` | `true` adds `plan_cluster` and `create_cluster`, which run commands over SSH with your key. See [PROVISIONING.md](docs/PROVISIONING.md). |
| `K3S_DEBUG` | `false` | Extra startup logging to stderr |

<a id="guides"></a>

## 📚 Guides

| | |
|---|---|
| [QUICKSTART.md](docs/QUICKSTART.md) | From clone to a working client, with least-privilege access and a checklist |
| [CLIENTS.md](docs/CLIENTS.md) | Claude Code, Claude Desktop, several clusters, settings, troubleshooting |
| [PROVISIONING.md](docs/PROVISIONING.md) | Building a K3s cluster with proxmox-mcp-server: what nodes need, what gets written, how secrets stay out |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How a call flows, namespace rules, every tool's API call and RBAC, known limits |
| [deploy/rbac.yaml](deploy/rbac.yaml) | The service account, roles and bindings |
| [deploy/rbac-node-ops.yaml](deploy/rbac-node-ops.yaml) | Optional: lets the server cordon and uncordon nodes |

<a id="troubleshooting"></a>

## 🩺 Troubleshooting

<details>
<summary><b>"Kubeconfig not found"</b></summary>

Set `KUBECONFIG` to an absolute path. Without it, the server looks for `~/.kube/config`.
</details>

<details>
<summary><b>Connection refused or timeouts</b></summary>

- The `server:` URL in your kubeconfig must be reachable from where the server runs.
- K3s writes `https://127.0.0.1:6443` by default; change it to the server's address.
</details>

<details>
<summary><b>403 Forbidden</b></summary>

That's RBAC working. The kubeconfig's identity isn't allowed to do that. To allow writes in another namespace, add an `edit` RoleBinding there. See [Safety](#safety).
</details>

<details>
<summary><b>Apply failed with a conflict</b></summary>

Another field manager owns that field. A common case: you scaled a deployment with `scale_deployment`, then applied YAML with a different `replicas`. Ask to apply again with `force` to take the field over, or drop it from the YAML.
</details>

<details>
<summary><b>Tools don't show up in Claude</b></summary>

Use absolute paths, check the config is valid JSON, and quit Claude Desktop completely before reopening it. Then check the client's log for the server's stderr. More in [CLIENTS.md](docs/CLIENTS.md#troubleshooting).
</details>

<a id="upcoming"></a>

## 🗺️ Upcoming

Planned, not built yet:

- [ ] **More distributions.** RKE2 and kubeadm for `create_cluster`, then Talos; highly available control planes; a teardown tool.
- [ ] **Tests and CI.** A pytest suite for the server's logic (rollout rules, kind lookup, apply results, the Secrets refusal) and a workflow that runs lint and tests on every pull request.
- [ ] **Follow logs.** Stream new lines from a pod instead of returning the last *N*.
- [ ] **Drain nodes.** Evict a node's pods after `cordon_node`, respecting PodDisruptionBudgets.
- [ ] **Roll back StatefulSets and DaemonSets.** `rollout_history` and `rollout_undo` from their ControllerRevisions; today they cover Deployments only.
- [ ] **Secret metadata.** Names, types and key names for Secrets. Their values stay out of the conversation on purpose.

## 🧱 Project layout

```
src/k3s_mcp_server/server.py   the server that gets packaged and installed (36 tools)
src/k3s_mcp_server/provision.py   cluster building over SSH: plan_cluster, create_cluster
docs/                          QUICKSTART, CLIENTS, PROVISIONING and ARCHITECTURE guides, and the animations on this page
scripts/                       setup.sh and test-connection.sh
deploy/rbac.yaml               a least-privilege service account for the server
deploy/rbac-node-ops.yaml      optional: node cordon and uncordon
```

Dependencies: `mcp`, `kubernetes` (the official client) and `pyyaml`.

## License

MIT. See [LICENSE](LICENSE).

<!-- org-footer -->
---

<p align="center"><sub>Part of <a href="https://github.com/ry-ops">ry-ops</a> · building the pipes between infrastructure, automation, and observability · built by <a href="https://github.com/ry-ops">ry-ops</a></sub></p>
