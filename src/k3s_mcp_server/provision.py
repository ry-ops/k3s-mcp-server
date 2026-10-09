"""
Build clusters over SSH and hand them to k3s-mcp-server.

Phase 1 of the cluster provisioning design: a K3s provider. The first node
becomes the single control-plane server, the rest join as agents.

Secrets never leave this module in a result:
- The join token is generated here and written to each node through stdin
  into /etc/rancher/k3s/config.yaml (mode 600), never on a command line.
- The admin kubeconfig is written to <dir>/<name>-admin.yaml (mode 600),
  which use_cluster never offers.
- The scoped kubeconfig for the k3s-mcp service account is written to
  <dir>/<name>.yaml (mode 600); results carry paths and a CA fingerprint only.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import urllib.request
from typing import Any, Dict, List, Optional

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$")
K3S_CHANNELS_URL = "https://update.k3s.io/v1-release/channels"
SERVICE_ACCOUNT = "k3s-mcp"

# What every provider reports; phase 1 implements K3s only.
DISTRIBUTIONS = [
    {"name": "k3s", "status": "available", "transport": "SSH",
     "min_server": {"cpus": 2, "memory_mb": 2048}, "min_agent": {"cpus": 1, "memory_mb": 1024}},
    {"name": "rke2", "status": "planned (phase 2)", "transport": "SSH"},
    {"name": "kubeadm", "status": "planned (phase 2)", "transport": "SSH"},
    {"name": "talos", "status": "planned (phase 3)", "transport": "Talos API"},
]


# SSH -------------------------------------------------------------------------

class SSH:
    """Run commands on one node with the system ssh client (keys, agent and known_hosts as usual)."""

    def __init__(self, host: str, user: str, key: Optional[str] = None):
        self.host, self.user, self.key = host, user, key

    def _argv(self, command: str) -> List[str]:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=15"]
        if self.key:
            argv += ["-i", os.path.expanduser(self.key)]
        return argv + [f"{self.user}@{self.host}", command]

    async def run(self, command: str, stdin: Optional[bytes] = None, timeout: float = 600) -> tuple:
        proc = await asyncio.create_subprocess_exec(
            *self._argv(command), stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise Exception(f"{self.host}: timed out after {timeout:.0f}s")
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")

    async def check(self, command: str, what: str, stdin: Optional[bytes] = None, timeout: float = 600) -> str:
        """Run a command that must succeed; on failure report only the tail of stderr."""
        rc, out, err = await self.run(command, stdin, timeout)
        if rc != 0:
            tail = " | ".join(line for line in err.strip().splitlines()[-3:] if line)
            raise Exception(f"{self.host}: {what} failed (exit {rc}): {tail or 'no output'}")
        return out


# Versions --------------------------------------------------------------------

def _k3s_channels() -> Dict[str, Any]:
    """K3s release channels: stable, latest and the newest three minors."""
    try:
        with urllib.request.urlopen(K3S_CHANNELS_URL, timeout=10) as resp:
            data = json.load(resp)
    except Exception as e:  # network trouble shouldn't break the listing
        return {"default": "stable", "error": f"Couldn't read {K3S_CHANNELS_URL}: {e}"}
    channels = {c["name"]: c.get("latest") for c in data.get("data", [])}
    minors = sorted((n for n in channels if re.fullmatch(r"v1\.\d+", n)),
                    key=lambda n: int(n.split(".")[1]), reverse=True)[:3]
    return {"default": "stable", "stable": channels.get("stable"), "latest": channels.get("latest"),
            "supported_minors": [{"channel": m, "version": channels[m]} for m in minors]}


def _install_env(version: str) -> str:
    """INSTALL_K3S_* for a channel ('stable', 'v1.34') or an exact version ('v1.34.1+k3s1')."""
    if not re.fullmatch(r"[a-z0-9.+-]+", version):
        raise ValueError(f"Not a K3s version or channel: {version!r}")
    if re.fullmatch(r"v\d+\.\d+\.\d+\+k3s\d+", version):
        return f"INSTALL_K3S_VERSION={version}"
    return f"INSTALL_K3S_CHANNEL={version}"


async def list_distributions() -> Dict[str, Any]:
    k3s = dict(DISTRIBUTIONS[0])
    k3s["versions"] = await asyncio.to_thread(_k3s_channels)
    return {"distributions": [k3s] + DISTRIBUTIONS[1:]}


# Plan ------------------------------------------------------------------------

PROBE = ("echo arch=$(uname -m); echo cpus=$(nproc); "
         "echo mem_mb=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo); "
         "echo os=$(. /etc/os-release && echo $ID-$VERSION_ID); "
         "echo hostname=$(hostname); "
         "echo sudo=$(sudo -n true 2>/dev/null && echo yes || echo no); "
         "echo curl=$(command -v curl >/dev/null && echo yes || echo no); "
         "echo k3s=$(test -e /usr/local/bin/k3s && echo yes || echo no); "
         "echo internet=$(curl -sfI -m 8 https://get.k3s.io >/dev/null && echo yes || echo no)")


def _validate(name: str, distribution: str, hosts: List[str], kubeconfig_dir: str) -> None:
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("name must be 1-40 lowercase letters, digits or '-', not starting or ending with '-'")
    if name.endswith("-admin"):
        raise ValueError("name can't end in '-admin': that suffix marks admin kubeconfigs")
    if distribution != "k3s":
        raise ValueError(f"{distribution!r} isn't available yet; list_distributions shows what is")
    if not hosts:
        raise ValueError("nodes must list at least one host")
    if len(set(hosts)) != len(hosts):
        raise ValueError("nodes must be unique")
    for path in (_paths(kubeconfig_dir, name).values()):
        if os.path.exists(path):
            raise ValueError(f"{path} already exists; pick another name or remove the old cluster's files")


def _paths(kubeconfig_dir: str, name: str) -> Dict[str, str]:
    return {"kubeconfig": os.path.join(kubeconfig_dir, f"{name}.yaml"),
            "admin_kubeconfig": os.path.join(kubeconfig_dir, f"{name}-admin.yaml")}


async def plan_cluster(name: str, nodes: List[str], kubeconfig_dir: str, distribution: str = "k3s",
                       version: str = "stable", ssh_user: str = "ubuntu",
                       ssh_key: Optional[str] = None) -> Dict[str, Any]:
    """Check every node and list what create_cluster would do. Changes nothing."""
    _validate(name, distribution, nodes, kubeconfig_dir)
    _install_env(version)
    minimum = DISTRIBUTIONS[0]

    async def probe(i: int, host: str) -> Dict[str, Any]:
        role = "server" if i == 0 else "agent"
        entry: Dict[str, Any] = {"host": host, "role": role, "blockers": [], "warnings": []}
        rc, out, err = await SSH(host, ssh_user, ssh_key).run(PROBE, timeout=60)
        if rc != 0:
            entry["blockers"].append(f"SSH as {ssh_user} failed: {err.strip().splitlines()[-1] if err.strip() else f'exit {rc}'}")
            return entry
        facts = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        entry.update({k: facts.get(k) for k in ("hostname", "os", "arch", "cpus", "mem_mb")})
        need = minimum["min_server" if role == "server" else "min_agent"]
        if facts.get("sudo") != "yes":
            entry["blockers"].append(f"{ssh_user} can't run sudo without a password")
        if facts.get("k3s") == "yes":
            entry["blockers"].append("K3s is already installed here")
        if facts.get("curl") != "yes":
            entry["blockers"].append("curl is missing; the K3s installer needs it")
        if facts.get("internet") != "yes":
            entry["blockers"].append("Can't reach https://get.k3s.io to download K3s")
        if int(facts.get("cpus") or 0) < need["cpus"]:
            entry["warnings"].append(f"{facts.get('cpus')} CPUs; K3s recommends {need['cpus']} for a {role}")
        if int(facts.get("mem_mb") or 0) < need["memory_mb"]:
            entry["warnings"].append(f"{facts.get('mem_mb')} MB RAM; K3s recommends {need['memory_mb']} for a {role}")
        return entry

    checks = await asyncio.gather(*(probe(i, h) for i, h in enumerate(nodes)))
    hostnames = [c.get("hostname") for c in checks if c.get("hostname")]
    dupes = sorted({h for h in hostnames if hostnames.count(h) > 1})
    blockers = [f"{c['host']}: {b}" for c in checks for b in c["blockers"]]
    if dupes:
        blockers.append(f"Duplicate hostnames {', '.join(dupes)}: Kubernetes node names must be unique")
    paths = _paths(kubeconfig_dir, name)
    return {
        "name": name,
        "distribution": distribution,
        "version": version,
        "ready": not blockers,
        "blockers": blockers,
        "nodes": checks,
        "steps": [
            f"Install the K3s server on {nodes[0]} ({_install_env(version)}) with a generated join token",
            f"Join {len(nodes) - 1} agent(s) to https://{nodes[0]}:6443" if len(nodes) > 1 else "No agents to join",
            "Wait until every node is Ready and CoreDNS is available",
            f"Write the admin kubeconfig to {paths['admin_kubeconfig']} (mode 600; never offered by use_cluster)",
            "Create the k3s-mcp service account (view + node reads cluster-wide, edit in the chosen namespaces)",
            f"Write its scoped kubeconfig to {paths['kubeconfig']} (mode 600) for use_cluster",
        ],
    }


# Create ----------------------------------------------------------------------

def _write_private(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _fingerprint(ca_b64: str) -> str:
    der = ssl.PEM_cert_to_DER_cert(base64.b64decode(ca_b64).decode())
    digest = hashlib.sha256(der).hexdigest().upper()
    return "SHA256:" + ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def _rbac_objects(edit_namespaces: List[str]) -> List[Dict[str, Any]]:
    """The objects in deploy/rbac.yaml, with edit bound in each chosen namespace."""
    sa = {"kind": "ServiceAccount", "name": SERVICE_ACCOUNT, "namespace": SERVICE_ACCOUNT}
    objs: List[Dict[str, Any]] = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SERVICE_ACCOUNT}},
        {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": SERVICE_ACCOUNT, "namespace": SERVICE_ACCOUNT}},
        {"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/service-account-token",
         "metadata": {"name": f"{SERVICE_ACCOUNT}-token", "namespace": SERVICE_ACCOUNT,
                      "annotations": {"kubernetes.io/service-account.name": SERVICE_ACCOUNT}}},
        {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRole",
         "metadata": {"name": f"{SERVICE_ACCOUNT}-node-reader"},
         "rules": [{"apiGroups": [""], "resources": ["nodes"], "verbs": ["get", "list", "watch"]}]},
        {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding",
         "metadata": {"name": f"{SERVICE_ACCOUNT}-view"},
         "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"}, "subjects": [sa]},
        {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding",
         "metadata": {"name": f"{SERVICE_ACCOUNT}-node-reader"},
         "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole",
                     "name": f"{SERVICE_ACCOUNT}-node-reader"}, "subjects": [sa]},
    ]
    for ns in edit_namespaces:
        objs.append({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns}})
        objs.append({"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding",
                     "metadata": {"name": f"{SERVICE_ACCOUNT}-edit", "namespace": ns},
                     "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "edit"},
                     "subjects": [sa]})
    return objs


async def _wait_ready(api: client.ApiClient, expected: int, timeout: float = 600) -> List[Dict[str, Any]]:
    core, apps = client.CoreV1Api(api), client.AppsV1Api(api)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        nodes = []
        try:
            for n in (await asyncio.to_thread(core.list_node)).items:
                ready = next((c.status for c in n.status.conditions or [] if c.type == "Ready"), "Unknown")
                ip = next((a.address for a in n.status.addresses or [] if a.type == "InternalIP"), None)
                nodes.append({"name": n.metadata.name, "ip": ip, "ready": ready == "True",
                              "version": n.status.node_info.kubelet_version,
                              "control_plane": "node-role.kubernetes.io/control-plane" in (n.metadata.labels or {})})
            dns = await asyncio.to_thread(apps.read_namespaced_deployment, "coredns", "kube-system")
            dns_ok = (dns.status.available_replicas or 0) >= 1
        except ApiException:
            dns_ok = False
        if len(nodes) >= expected and all(n["ready"] for n in nodes) and dns_ok:
            return nodes
        if loop.time() > deadline:
            raise Exception(f"Cluster not ready after {timeout:.0f}s: "
                            f"{sum(n['ready'] for n in nodes)}/{expected} nodes Ready, CoreDNS available: {dns_ok}")
        await asyncio.sleep(5)


async def create_cluster(name: str, nodes: List[str], kubeconfig_dir: str, distribution: str = "k3s",
                         version: str = "stable", ssh_user: str = "ubuntu", ssh_key: Optional[str] = None,
                         edit_namespaces: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build the cluster, then write its admin and scoped kubeconfigs. Returns paths, never secrets."""
    plan = await plan_cluster(name, nodes, kubeconfig_dir, distribution, version, ssh_user, ssh_key)
    if not plan["ready"]:
        raise Exception("plan_cluster found blockers: " + "; ".join(plan["blockers"]))
    edit_namespaces = edit_namespaces or ["default"]
    for ns in edit_namespaces:
        if not NAME_RE.fullmatch(ns):
            raise ValueError(f"Not a namespace name: {ns!r}")

    server_ip, agents = nodes[0], nodes[1:]
    token = secrets.token_hex(32)
    install = f"curl -sfL https://get.k3s.io | sudo env {_install_env(version)} sh -s - "
    write_config = "sudo install -D -m 600 /dev/stdin /etc/rancher/k3s/config.yaml"

    server = SSH(server_ip, ssh_user, ssh_key)
    server_cfg = yaml.safe_dump({"token": token, "write-kubeconfig-mode": "0600", "tls-san": [server_ip]})
    await server.check(write_config, "writing the server config", stdin=server_cfg.encode())
    await server.check(install + "server", "installing the K3s server", timeout=900)
    await server.check("sudo timeout 180 sh -c 'until [ -s /etc/rancher/k3s/k3s.yaml ]; do sleep 2; done'",
                       "waiting for the server's kubeconfig", timeout=200)

    agent_cfg = yaml.safe_dump({"server": f"https://{server_ip}:6443", "token": token}).encode()

    async def join(host: str) -> None:
        node = SSH(host, ssh_user, ssh_key)
        await node.check(write_config, "writing the agent config", stdin=agent_cfg)
        await node.check(install + "agent", "installing the K3s agent", timeout=900)

    await asyncio.gather(*(join(h) for h in agents))

    # Admin kubeconfig: read over SSH, point it at the node, write it to disk only
    admin = yaml.safe_load(await server.check("sudo cat /etc/rancher/k3s/k3s.yaml", "reading the admin kubeconfig"))
    admin["clusters"][0]["name"] = name
    admin["clusters"][0]["cluster"]["server"] = f"https://{server_ip}:6443"
    admin["users"][0]["name"] = f"{name}-admin"
    admin["contexts"][0] = {"name": f"{name}-admin", "context": {"cluster": name, "user": f"{name}-admin"}}
    admin["current-context"] = f"{name}-admin"
    ca = admin["clusters"][0]["cluster"]["certificate-authority-data"]
    paths = _paths(kubeconfig_dir, name)
    _write_private(paths["admin_kubeconfig"], admin)

    api = config.new_client_from_config_dict(admin)
    ready_nodes = await _wait_ready(api, expected=len(nodes))

    # The MCP's own identity, as in deploy/rbac.yaml
    from kubernetes.dynamic import DynamicClient
    dyn = DynamicClient(api)
    for obj in _rbac_objects(edit_namespaces):
        res = dyn.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
        await asyncio.to_thread(res.server_side_apply, body=obj, name=obj["metadata"]["name"],
                                namespace=obj["metadata"].get("namespace"), field_manager="k3s-mcp-server")

    core = client.CoreV1Api(api)
    sa_token = None
    for _ in range(30):
        secret = await asyncio.to_thread(core.read_namespaced_secret, f"{SERVICE_ACCOUNT}-token", SERVICE_ACCOUNT)
        if (secret.data or {}).get("token"):
            sa_token = base64.b64decode(secret.data["token"]).decode()
            break
        await asyncio.sleep(1)
    if not sa_token:
        raise Exception("The k3s-mcp service account token was never issued")

    _write_private(paths["kubeconfig"], {
        "apiVersion": "v1", "kind": "Config",
        "clusters": [{"name": name, "cluster": {"server": f"https://{server_ip}:6443",
                                                "certificate-authority-data": ca}}],
        "users": [{"name": SERVICE_ACCOUNT, "user": {"token": sa_token}}],
        "contexts": [{"name": name, "context": {"cluster": name, "user": SERVICE_ACCOUNT,
                                                "namespace": edit_namespaces[0]}}],
        "current-context": name,
    })

    return {
        "name": name,
        "distribution": distribution,
        "api_server": f"https://{server_ip}:6443",
        "nodes": ready_nodes,
        "kubeconfig": paths["kubeconfig"],
        "admin_kubeconfig": paths["admin_kubeconfig"],
        "ca_fingerprint": _fingerprint(ca),
        "edit_namespaces": edit_namespaces,
        "next": f"use_cluster with name {name!r} to manage it with the scoped identity",
    }


# Status ----------------------------------------------------------------------

async def cluster_status(name: str, kubeconfig_dir: str) -> Dict[str, Any]:
    """Nodes, versions and Ready state of a cluster in the folder, without switching to it."""
    path = _paths(kubeconfig_dir, name)["kubeconfig"]
    if not NAME_RE.fullmatch(name or "") or not os.path.exists(path):
        raise Exception(f"No cluster named {name!r} in {kubeconfig_dir}")
    api = config.new_client_from_config(config_file=path)
    try:
        items = (await asyncio.to_thread(client.CoreV1Api(api).list_node)).items
        version = (await asyncio.to_thread(client.VersionApi(api).get_code)).git_version
    except Exception as e:
        raise Exception(f"Couldn't reach {name}: {e}")
    nodes = [{
        "name": n.metadata.name,
        "ready": next((c.status == "True" for c in n.status.conditions or [] if c.type == "Ready"), False),
        "ip": next((a.address for a in n.status.addresses or [] if a.type == "InternalIP"), None),
        "version": n.status.node_info.kubelet_version,
        "control_plane": "node-role.kubernetes.io/control-plane" in (n.metadata.labels or {}),
    } for n in items]
    return {"name": name, "version": version, "ready": f"{sum(n['ready'] for n in nodes)}/{len(nodes)}",
            "nodes": nodes}
