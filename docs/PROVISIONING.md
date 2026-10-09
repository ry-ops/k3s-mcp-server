# Building clusters

k3s-mcp-server can build a K3s cluster on machines you can SSH into, then manage it straight away. Paired with [proxmox-mcp-server](https://github.com/ry-ops/proxmox-mcp-server), which makes the VMs, one conversation goes from nothing to a working cluster:

> *"Make three Ubuntu VMs on pve01, vmbr1 VLAN 145, 10.88.145.181–183, and build a K3s cluster called lab2 on them."*

1. proxmox-mcp-server's `deploy_cloud_vms` creates the VMs from a cloud image, with your SSH key and a static IP each.
2. `plan_cluster` checks every node over SSH and lists the steps. It changes nothing.
3. `create_cluster` installs the K3s server on the first node, joins the rest as agents, waits until every node is Ready and CoreDNS is up, and writes two kubeconfigs.
4. `use_cluster("lab2")` switches to the new cluster with its scoped identity. Every other tool works on it from there.

## Turn it on

`plan_cluster` and `create_cluster` run commands as root over SSH with your key. No kubeconfig's RBAC limits that, so they're **off by default**. Turn them on per registration:

```bash
claude mcp add k3s --scope user \
  -e KUBECONFIG=$HOME/.kube/k3s-mcp.yaml \
  -e K3S_PROVISIONING=true \
  -- uv --directory /path/to/k3s-mcp-server run k3s-mcp-server
```

`list_distributions` and `cluster_status` are always available. Keep your client's tool approval on, so you see the plan and approve `create_cluster` before it runs.

The server reports the setting to your MCP client when it connects (in its server instructions) and in `list_distributions`. While it's off, a request to build a cluster gets an explanation of how to enable it, and Claude is told not to build one some other way, such as running installers through `execute_command`.

## What the nodes need

| Need | Why |
|---|---|
| SSH from this machine as a user with passwordless `sudo` (default `ubuntu`) | Every step runs over SSH, using your normal keys, agent and `~/.ssh/config` |
| `curl`, and outbound HTTPS to `get.k3s.io` and GitHub | The K3s installer downloads K3s |
| 2 CPUs and 2 GB RAM for the server, 1 CPU and 1 GB per agent | The sizes `plan_cluster` checks for; smaller nodes get a warning, not a refusal |
| Unique hostnames, and no K3s already installed | Node names come from hostnames; an existing install is a blocker |

Ubuntu cloud images made by `deploy_cloud_vms` meet all of these. `plan_cluster` reports anything missing, per node, before anything changes.

## What it writes

| File | Mode | Holds | Used by |
|---|---|---|---|
| `~/.kube/clusters/<name>.yaml` | 600 | A token for the `k3s-mcp` service account: `view` and node reads cluster-wide, `edit` in the namespaces you choose (default `default`) | `use_cluster`, and any tool that reads a kubeconfig |
| `~/.kube/clusters/<name>-admin.yaml` | 600 | The cluster-admin kubeconfig from the server node, pointed at its address | You. `use_cluster` never offers `-admin` files |
| `/etc/rancher/k3s/config.yaml` on each node | 600, root | The join token, and the server address on agents | K3s |

The service account matches [`deploy/rbac.yaml`](../deploy/rbac.yaml).

## Secrets stay out of the conversation

- **The join token** is generated on this machine and written to each node's `config.yaml` through SSH's standard input. It never appears on a command line, in a log or in a tool result.
- **Kubeconfigs** are written to disk, never returned. `create_cluster` returns the file paths and the CA's SHA-256 fingerprint, so you can check which cluster you got.
- **Errors** carry the last lines of the failing command's stderr, never its input.

## Versions

`list_distributions` reads K3s's release channels and shows `stable`, `latest` and the three newest minor versions. Pass `version` as a channel (`stable`, `v1.36`) or an exact release (`v1.36.5+k3s1`); the default is `stable`.

## Limits in this release

- **K3s only.** RKE2 and kubeadm (phase 2) and Talos (phase 3) are planned; `list_distributions` shows their status.
- **One control-plane node.** The first node is the server; highly available control planes come later.
- **No teardown tool yet.** To remove a cluster, run `sudo /usr/local/bin/k3s-uninstall.sh` on the server and `sudo /usr/local/bin/k3s-agent-uninstall.sh` on each agent (or delete the VMs), then delete both files in `~/.kube/clusters/`. If you reuse the IPs, remove their old host keys: `ssh-keygen -R <ip>`.
- **A failed build isn't rolled back.** Fix what the error names, tear down as above, and run `create_cluster` again.
