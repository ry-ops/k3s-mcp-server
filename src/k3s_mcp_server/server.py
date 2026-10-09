#!/usr/bin/env python3
"""
K3s MCP Server

An MCP server for interacting with Kubernetes (K3s) clusters.
Provides comprehensive tools for managing pods, deployments, services, nodes, and more.

GitHub: https://github.com/ry-ops/k3s-mcp-server
Documentation: https://github.com/ry-ops/k3s-mcp-server#readme

Configuration via environment variables:
    KUBECONFIG: Path to kubeconfig file (default: ~/.kube/k3s-cortex-config.yaml)
    K3S_DEFAULT_NAMESPACE: Default namespace for operations (default: default)
    K3S_DEBUG: Enable debug logging (default: false)

Author: ry-ops
License: MIT
Version: 1.4.0
"""

import os
import sys
import json
import yaml
from typing import Any, Optional, Dict, List
from pathlib import Path
import re
import asyncio
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from kubernetes.utils import parse_quantity
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

from k3s_mcp_server import __version__


# Configuration
KUBECONFIG = os.getenv("KUBECONFIG", str(Path.home() / ".kube" / "k3s-cortex-config.yaml"))
DEFAULT_NAMESPACE = os.getenv("K3S_DEFAULT_NAMESPACE", "default")
DEBUG = os.getenv("K3S_DEBUG", "false").lower() == "true"

# Field manager name recorded on objects changed by server-side apply
FIELD_MANAGER = "k3s-mcp-server"

# Anchored regex for Kubernetes role label parsing
_ROLE_LABEL_RE = re.compile(r'^node-role\.kubernetes\.io/(.+)$')


class K3sClient:
    """
    Client for interacting with Kubernetes (K3s) cluster.

    Handles kubeconfig loading and provides high-level API methods.
    """

    def __init__(self):
        """Initialize the Kubernetes client."""
        self.kubeconfig_path = KUBECONFIG
        self._load_config()

        # Initialize API clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self.custom_objects = client.CustomObjectsApi()
        self._dynamic = None

        if DEBUG:
            print(f"K3s MCP Server initialized with kubeconfig: {self.kubeconfig_path}", file=sys.stderr)

    def _load_config(self):
        """Load kubeconfig from file or environment."""
        try:
            # Check if kubeconfig file exists
            if not os.path.exists(self.kubeconfig_path):
                print(f"Error: Kubeconfig not found at {self.kubeconfig_path}", file=sys.stderr)
                print("Set KUBECONFIG environment variable to the correct path", file=sys.stderr)
                sys.exit(1)

            # Load kubeconfig
            config.load_kube_config(config_file=self.kubeconfig_path)
            print(f"Loaded kubeconfig from: {self.kubeconfig_path}", file=sys.stderr)

        except Exception as e:
            print(f"Error loading kubeconfig: {e}", file=sys.stderr)
            sys.exit(1)

    def _format_pod_info(self, pod) -> Dict[str, Any]:
        """Format pod information for display."""
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
            "pod_ip": pod.status.pod_ip,
            "host_ip": pod.status.host_ip,
            "containers": [
                {
                    "name": c.name,
                    "image": c.image,
                    "ready": next((cs.ready for cs in pod.status.container_statuses if cs.name == c.name), False) if pod.status.container_statuses else False,
                    "restart_count": next((cs.restart_count for cs in pod.status.container_statuses if cs.name == c.name), 0) if pod.status.container_statuses else 0,
                }
                for c in pod.spec.containers
            ],
            "created": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
            "labels": pod.metadata.labels or {},
        }

    def _format_deployment_info(self, deployment) -> Dict[str, Any]:
        """Format deployment information for display."""
        return {
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "replicas": {
                "desired": deployment.spec.replicas,
                "current": deployment.status.replicas or 0,
                "ready": deployment.status.ready_replicas or 0,
                "available": deployment.status.available_replicas or 0,
                "unavailable": deployment.status.unavailable_replicas or 0,
            },
            "strategy": deployment.spec.strategy.type,
            "containers": [
                {
                    "name": c.name,
                    "image": c.image,
                }
                for c in deployment.spec.template.spec.containers
            ],
            "created": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None,
            "labels": deployment.metadata.labels or {},
            "selector": deployment.spec.selector.match_labels or {},
        }

    def _format_service_info(self, service) -> Dict[str, Any]:
        """Format service information for display."""
        return {
            "name": service.metadata.name,
            "namespace": service.metadata.namespace,
            "type": service.spec.type,
            "cluster_ip": service.spec.cluster_ip,
            "external_ips": service.spec.external_i_ps or [],
            "ports": [
                {
                    "name": p.name,
                    "port": p.port,
                    "target_port": str(p.target_port),
                    "protocol": p.protocol,
                    "node_port": p.node_port if hasattr(p, 'node_port') else None,
                }
                for p in service.spec.ports or []
            ],
            "selector": service.spec.selector or {},
            "created": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
            "labels": service.metadata.labels or {},
        }

    def _format_node_info(self, node) -> Dict[str, Any]:
        """Format node information for display."""
        # Get node conditions
        conditions = {c.type: c.status for c in node.status.conditions or []}

        # Get resource capacity and allocatable
        capacity = node.status.capacity or {}
        allocatable = node.status.allocatable or {}

        return {
            "name": node.metadata.name,
            "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
            "roles": [m.group(1) for label in (node.metadata.labels or {}) for m in [_ROLE_LABEL_RE.match(label)] if m],
            "version": node.status.node_info.kubelet_version,
            "os": f"{node.status.node_info.os_image} ({node.status.node_info.architecture})",
            "kernel": node.status.node_info.kernel_version,
            "container_runtime": node.status.node_info.container_runtime_version,
            "capacity": {
                "cpu": capacity.get("cpu"),
                "memory": capacity.get("memory"),
                "pods": capacity.get("pods"),
            },
            "allocatable": {
                "cpu": allocatable.get("cpu"),
                "memory": allocatable.get("memory"),
                "pods": allocatable.get("pods"),
            },
            "addresses": [
                {"type": addr.type, "address": addr.address}
                for addr in node.status.addresses or []
            ],
            "conditions": conditions,
            "created": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
            "labels": node.metadata.labels or {},
        }

    async def get_pods(self, namespace: Optional[str] = None, labels: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List pods in a namespace or across all namespaces.

        Args:
            namespace: Namespace to filter pods (None for all namespaces)
            labels: Label selector (e.g., 'app=nginx,env=prod')

        Returns:
            List of pod information dictionaries
        """
        try:
            if namespace:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=labels or ""
                )
            else:
                pods = self.core_v1.list_pod_for_all_namespaces(
                    label_selector=labels or ""
                )

            return [self._format_pod_info(pod) for pod in pods.items]
        except ApiException as e:
            raise Exception(f"Failed to list pods: {e}")

    async def get_deployments(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List deployments in a namespace or across all namespaces.

        Args:
            namespace: Namespace to filter deployments (None for all namespaces)

        Returns:
            List of deployment information dictionaries
        """
        try:
            if namespace:
                deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deployments = self.apps_v1.list_deployment_for_all_namespaces()

            return [self._format_deployment_info(d) for d in deployments.items]
        except ApiException as e:
            raise Exception(f"Failed to list deployments: {e}")

    async def get_deployment(self, name: str, namespace: str) -> Dict[str, Any]:
        """
        Get a specific deployment.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            Deployment information dictionary
        """
        try:
            deployment = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            return self._format_deployment_info(deployment)
        except ApiException as e:
            raise Exception(f"Failed to get deployment {name}: {e}")

    async def get_services(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List services in a namespace or across all namespaces.

        Args:
            namespace: Namespace to filter services (None for all namespaces)

        Returns:
            List of service information dictionaries
        """
        try:
            if namespace:
                services = self.core_v1.list_namespaced_service(namespace=namespace)
            else:
                services = self.core_v1.list_service_for_all_namespaces()

            return [self._format_service_info(s) for s in services.items]
        except ApiException as e:
            raise Exception(f"Failed to list services: {e}")

    async def get_nodes(self) -> List[Dict[str, Any]]:
        """
        List all nodes in the cluster.

        Returns:
            List of node information dictionaries
        """
        try:
            nodes = self.core_v1.list_node()
            return [self._format_node_info(node) for node in nodes.items]
        except ApiException as e:
            raise Exception(f"Failed to list nodes: {e}")

    @staticmethod
    def _ts(value) -> Optional[str]:
        """ISO timestamp or None."""
        return value.isoformat() if value else None

    @staticmethod
    def _images(pod_spec) -> List[str]:
        """Container images in a pod spec."""
        return [c.image for c in pod_spec.containers] if pod_spec else []

    def _list(self, namespaced_fn, all_fn, namespace: Optional[str], what: str,
              labels: Optional[str] = None):
        """List objects in one namespace or all of them."""
        try:
            if namespace:
                return namespaced_fn(namespace=namespace, label_selector=labels or "").items
            return all_fn(label_selector=labels or "").items
        except ApiException as e:
            raise Exception(f"Failed to list {what}: {e}")

    async def get_statefulsets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List StatefulSets with replica counts and images."""
        items = self._list(self.apps_v1.list_namespaced_stateful_set,
                           self.apps_v1.list_stateful_set_for_all_namespaces, namespace, "statefulsets")
        return [
            {
                "name": s.metadata.name,
                "namespace": s.metadata.namespace,
                "replicas": s.spec.replicas,
                "ready": s.status.ready_replicas or 0,
                "updated": s.status.updated_replicas or 0,
                "service": s.spec.service_name,
                "images": self._images(s.spec.template.spec),
                "created": self._ts(s.metadata.creation_timestamp),
            }
            for s in items
        ]

    async def get_daemonsets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List DaemonSets with scheduling and readiness counts."""
        items = self._list(self.apps_v1.list_namespaced_daemon_set,
                           self.apps_v1.list_daemon_set_for_all_namespaces, namespace, "daemonsets")
        return [
            {
                "name": d.metadata.name,
                "namespace": d.metadata.namespace,
                "desired": d.status.desired_number_scheduled,
                "current": d.status.current_number_scheduled,
                "ready": d.status.number_ready,
                "updated": d.status.updated_number_scheduled or 0,
                "available": d.status.number_available or 0,
                "node_selector": d.spec.template.spec.node_selector or {},
                "images": self._images(d.spec.template.spec),
            }
            for d in items
        ]

    async def get_jobs(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List Jobs with their outcome and the CronJob that created them."""
        items = self._list(self.batch_v1.list_namespaced_job,
                           self.batch_v1.list_job_for_all_namespaces, namespace, "jobs")
        jobs = []
        for j in items:
            conditions = {c.type: c for c in j.status.conditions or [] if c.status == "True"}
            if "Complete" in conditions:
                status = "Complete"
            elif "Failed" in conditions:
                status = "Failed"
            elif "Suspended" in conditions:
                status = "Suspended"
            else:
                status = "Running" if j.status.active else "Pending"
            failed = conditions.get("Failed")
            jobs.append({
                "name": j.metadata.name,
                "namespace": j.metadata.namespace,
                "status": status,
                "reason": failed.reason if failed else None,
                "completions": j.spec.completions,
                "succeeded": j.status.succeeded or 0,
                "failed": j.status.failed or 0,
                "active": j.status.active or 0,
                "started": self._ts(j.status.start_time),
                "completed": self._ts(j.status.completion_time),
                "owner": next((f"{o.kind}/{o.name}" for o in j.metadata.owner_references or []), None),
            })
        return jobs

    async def get_cronjobs(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List CronJobs with schedule and last run times."""
        items = self._list(self.batch_v1.list_namespaced_cron_job,
                           self.batch_v1.list_cron_job_for_all_namespaces, namespace, "cronjobs")
        return [
            {
                "name": c.metadata.name,
                "namespace": c.metadata.namespace,
                "schedule": c.spec.schedule,
                "time_zone": c.spec.time_zone,
                "suspended": bool(c.spec.suspend),
                "active": len(c.status.active or []),
                "last_scheduled": self._ts(c.status.last_schedule_time),
                "last_successful": self._ts(c.status.last_successful_time),
            }
            for c in items
        ]

    async def get_ingresses(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List Ingresses with hosts, paths, backends, TLS and load balancer addresses."""
        items = self._list(self.networking_v1.list_namespaced_ingress,
                           self.networking_v1.list_ingress_for_all_namespaces, namespace, "ingresses")

        def backend(b) -> Optional[str]:
            if b is None:
                return None
            if b.service:
                port = b.service.port.number or b.service.port.name if b.service.port else None
                return f"{b.service.name}:{port}" if port else b.service.name
            if b.resource:
                return f"{b.resource.kind}/{b.resource.name}"
            return None

        ingresses = []
        for i in items:
            rules = []
            for r in i.spec.rules or []:
                paths = r.http.paths if r.http else []
                rules.append({
                    "host": r.host or "*",
                    "paths": [
                        {"path": p.path or "/", "type": p.path_type, "backend": backend(p.backend)}
                        for p in paths
                    ],
                })
            lb = i.status.load_balancer.ingress if i.status and i.status.load_balancer else None
            ingresses.append({
                "name": i.metadata.name,
                "namespace": i.metadata.namespace,
                "class": i.spec.ingress_class_name,
                "rules": rules,
                "default_backend": backend(i.spec.default_backend),
                "tls_hosts": [h for t in i.spec.tls or [] for h in t.hosts or []],
                "addresses": [a.ip or a.hostname for a in lb or []],
            })
        return ingresses

    async def get_configmaps(self, namespace: Optional[str] = None,
                             name: Optional[str] = None) -> Any:
        """
        List ConfigMaps with their keys, or return one ConfigMap's data.

        Args:
            namespace: Namespace (None lists all namespaces; required with name)
            name: ConfigMap name; returns its data, with long values truncated

        Returns:
            List of ConfigMap summaries, or one ConfigMap's data
        """
        if name:
            try:
                cm = self.core_v1.read_namespaced_config_map(name=name, namespace=namespace)
            except ApiException as e:
                raise Exception(f"Failed to get configmap {name}: {e}")
            limit = 4000
            data = {
                k: v if len(v) <= limit else v[:limit] + f"\n… [truncated, {len(v)} chars]"
                for k, v in (cm.data or {}).items()
            }
            return {
                "name": cm.metadata.name,
                "namespace": cm.metadata.namespace,
                "data": data,
                "binary_keys": sorted((cm.binary_data or {}).keys()),
            }

        items = self._list(self.core_v1.list_namespaced_config_map,
                           self.core_v1.list_config_map_for_all_namespaces, namespace, "configmaps")
        return [
            {
                "name": c.metadata.name,
                "namespace": c.metadata.namespace,
                "keys": sorted((c.data or {}).keys()) + sorted((c.binary_data or {}).keys()),
                "created": self._ts(c.metadata.creation_timestamp),
            }
            for c in items
        ]

    async def get_pvcs(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List PersistentVolumeClaims with status, size, storage class and bound volume."""
        items = self._list(self.core_v1.list_namespaced_persistent_volume_claim,
                           self.core_v1.list_persistent_volume_claim_for_all_namespaces,
                           namespace, "persistentvolumeclaims")
        return [
            {
                "name": c.metadata.name,
                "namespace": c.metadata.namespace,
                "status": c.status.phase,
                "requested": (c.spec.resources.requests or {}).get("storage") if c.spec.resources else None,
                "capacity": (c.status.capacity or {}).get("storage"),
                "access_modes": c.spec.access_modes or [],
                "storage_class": c.spec.storage_class_name,
                "volume": c.spec.volume_name,
            }
            for c in items
        ]

    async def scale_deployment(self, name: str, namespace: str, replicas: int) -> Dict[str, Any]:
        """
        Scale a deployment to a specific number of replicas.

        Args:
            name: Deployment name
            namespace: Namespace
            replicas: Desired replica count

        Returns:
            Updated deployment information
        """
        try:
            # Patch the deployment
            body = {"spec": {"replicas": replicas}}
            self.apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=body
            )

            return {
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "status": "Scaled successfully"
            }
        except ApiException as e:
            raise Exception(f"Failed to scale deployment {name}: {e}")

    async def restart_pod(self, name: str, namespace: str) -> Dict[str, Any]:
        """
        Restart a pod by deleting it (will be recreated by controller).

        Args:
            name: Pod name
            namespace: Namespace

        Returns:
            Deletion status
        """
        try:
            self.core_v1.delete_namespaced_pod(name=name, namespace=namespace)
            return {
                "name": name,
                "namespace": namespace,
                "status": "Pod deleted (will be recreated by controller)"
            }
        except ApiException as e:
            raise Exception(f"Failed to delete pod {name}: {e}")

    # Rollouts ---------------------------------------------------------------

    _ROLLOUT_KINDS = {
        "deployment": "deployment", "deployments": "deployment", "deploy": "deployment",
        "statefulset": "stateful_set", "statefulsets": "stateful_set", "sts": "stateful_set",
        "daemonset": "daemon_set", "daemonsets": "daemon_set", "ds": "daemon_set",
    }

    _KIND_NAMES = {"deployment": "Deployment", "stateful_set": "StatefulSet",
                   "daemon_set": "DaemonSet"}

    def _rollout_kind(self, kind: str) -> str:
        """Map a workload kind to the AppsV1Api method suffix."""
        suffix = self._ROLLOUT_KINDS.get(kind.lower())
        if not suffix:
            raise Exception(f"Rollouts work on Deployments, StatefulSets and DaemonSets, not {kind!r}")
        return suffix

    async def rollout_restart(self, kind: str, name: str, namespace: str) -> Dict[str, Any]:
        """
        Restart a workload's pods with a rolling update, like `kubectl rollout restart`.

        Sets the kubectl.kubernetes.io/restartedAt annotation on the pod template.
        """
        suffix = self._rollout_kind(kind)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {"spec": {"template": {"metadata": {"annotations": {
            "kubectl.kubernetes.io/restartedAt": now}}}}}
        try:
            getattr(self.apps_v1, f"patch_namespaced_{suffix}")(
                name=name, namespace=namespace, body=body, field_manager=FIELD_MANAGER)
        except ApiException as e:
            raise Exception(f"Failed to restart {self._KIND_NAMES[suffix]} {name}: "
                            f"{self._api_error_message(e)}")
        return {"kind": self._KIND_NAMES[suffix], "name": name, "namespace": namespace,
                "restarted_at": now,
                "status": "Rolling restart started; check progress with rollout_status"}

    def _rollout_state(self, suffix: str, obj) -> Dict[str, Any]:
        """Work out whether a rollout is finished, following kubectl's rules."""
        spec, status = obj.spec, obj.status
        observed = (status.observed_generation or 0) >= (obj.metadata.generation or 0)

        if suffix == "deployment":
            want = spec.replicas if spec.replicas is not None else 1
            updated, ready, available = (status.updated_replicas or 0,
                                         status.ready_replicas or 0, status.available_replicas or 0)
            total = status.replicas or 0
            progressing = next((c for c in status.conditions or [] if c.type == "Progressing"), None)
            # Like kubectl, trust the deadline condition only once the controller has
            # seen the latest spec; otherwise it may describe the previous rollout.
            if observed and progressing and progressing.reason == "ProgressDeadlineExceeded":
                return {"done": False, "failed": True,
                        "message": f"Rollout exceeded its progress deadline: {progressing.message}"}
            if not observed:
                message, done = "Waiting for the controller to see the new spec", False
            elif updated < want:
                message, done = f"{updated} of {want} replicas updated", False
            elif total > updated:
                message, done = f"{total - updated} old replicas pending termination", False
            elif available < updated:
                message, done = f"{available} of {updated} updated replicas available", False
            else:
                message, done = f"Rolled out: {available}/{want} available", True
            counts = {"desired": want, "updated": updated, "ready": ready, "available": available}

        elif suffix == "stateful_set":
            want = spec.replicas if spec.replicas is not None else 1
            updated, ready = status.updated_replicas or 0, status.ready_replicas or 0
            on_delete = spec.update_strategy and spec.update_strategy.type == "OnDelete"
            if on_delete:
                return {"done": True, "message": "OnDelete strategy: pods update only when deleted",
                        "desired": want, "updated": updated, "ready": ready}
            if not observed:
                message, done = "Waiting for the controller to see the new spec", False
            elif ready < want:
                message, done = f"{ready} of {want} pods ready", False
            elif status.update_revision != status.current_revision:
                message, done = f"{updated} of {want} pods updated", False
            else:
                message, done = f"Rolled out: {ready}/{want} ready", True
            counts = {"desired": want, "updated": updated, "ready": ready}

        else:
            want = status.desired_number_scheduled or 0
            updated, available = status.updated_number_scheduled or 0, status.number_available or 0
            if not observed:
                message, done = "Waiting for the controller to see the new spec", False
            elif updated < want:
                message, done = f"{updated} of {want} pods updated", False
            elif available < want:
                message, done = f"{available} of {want} updated pods available", False
            else:
                message, done = f"Rolled out: {available}/{want} available", True
            counts = {"desired": want, "updated": updated, "available": available}

        return {"done": done, "message": message, **counts}

    async def rollout_status(self, kind: str, name: str, namespace: str,
                             wait_seconds: int = 0) -> Dict[str, Any]:
        """
        Report whether a workload's rollout has finished, optionally waiting for it.

        Args:
            kind: Deployment, StatefulSet or DaemonSet
            name: Workload name
            namespace: Namespace
            wait_seconds: Poll until done or this many seconds pass (0 checks once; max 300)
        """
        suffix = self._rollout_kind(kind)
        read = getattr(self.apps_v1, f"read_namespaced_{suffix}")
        deadline = asyncio.get_running_loop().time() + max(0, min(wait_seconds, 300))
        while True:
            try:
                obj = read(name=name, namespace=namespace)
            except ApiException as e:
                raise Exception(f"Failed to get {self._KIND_NAMES[suffix]} {name}: "
                                f"{self._api_error_message(e)}")
            state = self._rollout_state(suffix, obj)
            if state["done"] or state.get("failed") or asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(2)
        return {"kind": self._KIND_NAMES[suffix], "name": name, "namespace": namespace, **state}

    def _deployment_revisions(self, name: str, namespace: str):
        """The deployment and its ReplicaSets keyed by revision number."""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            selector = ",".join(f"{k}={v}" for k, v in
                                (deployment.spec.selector.match_labels or {}).items())
            replica_sets = self.apps_v1.list_namespaced_replica_set(
                namespace=namespace, label_selector=selector).items
        except ApiException as e:
            raise Exception(f"Failed to read deployment {name}: {self._api_error_message(e)}")

        revisions = {}
        for rs in replica_sets:
            if not any(o.uid == deployment.metadata.uid for o in rs.metadata.owner_references or []):
                continue
            rev = (rs.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
            if rev and rev.isdigit():
                revisions[int(rev)] = rs
        return deployment, revisions

    async def rollout_history(self, name: str, namespace: str) -> Dict[str, Any]:
        """List a deployment's revisions with their images and change cause."""
        deployment, revisions = self._deployment_revisions(name, namespace)
        current = (deployment.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
        return {
            "name": name,
            "namespace": namespace,
            "current_revision": int(current) if current and current.isdigit() else None,
            "revisions": [
                {
                    "revision": rev,
                    "images": self._images(rs.spec.template.spec),
                    "change_cause": (rs.metadata.annotations or {}).get("kubernetes.io/change-cause"),
                    "replicas": rs.status.replicas or 0,
                    "created": self._ts(rs.metadata.creation_timestamp),
                }
                for rev, rs in sorted(revisions.items(), reverse=True)
            ],
        }

    async def rollout_undo(self, name: str, namespace: str,
                           to_revision: Optional[int] = None) -> Dict[str, Any]:
        """
        Roll a deployment back to an earlier revision, like `kubectl rollout undo`.

        Args:
            name: Deployment name
            namespace: Namespace
            to_revision: Revision to roll back to (default: the one before the current)
        """
        deployment, revisions = self._deployment_revisions(name, namespace)
        if not revisions:
            raise Exception(f"Deployment {name} has no revision history")
        current = max(revisions)
        if to_revision is None:
            older = [r for r in revisions if r < current]
            if not older:
                raise Exception(f"Deployment {name} has no earlier revision to roll back to")
            to_revision = max(older)
        if to_revision not in revisions:
            raise Exception(f"Revision {to_revision} not found; available: {sorted(revisions)}")
        if to_revision == current:
            return {"name": name, "namespace": namespace, "revision": current,
                    "status": "Already at that revision; nothing to do"}

        template = self.apps_v1.api_client.sanitize_for_serialization(
            revisions[to_revision].spec.template)
        template.get("metadata", {}).get("labels", {}).pop("pod-template-hash", None)
        patch = [{"op": "replace", "path": "/spec/template", "value": template}]
        try:
            self.apps_v1.patch_namespaced_deployment(
                name=name, namespace=namespace, body=patch, field_manager=FIELD_MANAGER)
        except ApiException as e:
            raise Exception(f"Failed to roll back deployment {name}: {self._api_error_message(e)}")
        return {
            "name": name,
            "namespace": namespace,
            "rolled_back_to": to_revision,
            "images": self._images(revisions[to_revision].spec.template.spec),
            "status": "Rollback started; check progress with rollout_status",
        }

    # Nodes ------------------------------------------------------------------

    async def set_node_schedulable(self, name: str, schedulable: bool) -> Dict[str, Any]:
        """Cordon (schedulable=False) or uncordon (schedulable=True) a node."""
        try:
            node = self.core_v1.patch_node(
                name=name, body={"spec": {"unschedulable": not schedulable}},
                field_manager=FIELD_MANAGER)
        except ApiException as e:
            action = "uncordon" if schedulable else "cordon"
            raise Exception(f"Failed to {action} node {name}: {self._api_error_message(e)}")
        return {
            "name": name,
            "schedulable": not node.spec.unschedulable,
            "status": "Uncordoned: new pods can be scheduled here" if schedulable
            else "Cordoned: no new pods will be scheduled here; running pods stay",
        }

    async def get_logs(self, pod_name: str, namespace: str, container: Optional[str] = None,
                      tail_lines: int = 100, previous: bool = False) -> str:
        """
        Get logs from a pod.

        Args:
            pod_name: Pod name
            namespace: Namespace
            container: Container name (optional, uses first container if not specified)
            tail_lines: Number of lines to tail
            previous: Return logs from the previous (crashed) container instance

        Returns:
            Pod logs as string
        """
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
                previous=previous
            )
            return logs
        except ApiException as e:
            raise Exception(f"Failed to get logs for pod {pod_name}: {e}")

    @staticmethod
    def _format_event(event) -> Dict[str, Any]:
        """Format an event for output."""
        last_seen = event.last_timestamp or event.event_time or event.metadata.creation_timestamp
        obj = event.involved_object
        return {
            "type": event.type,
            "reason": event.reason,
            "object": f"{obj.kind}/{obj.name}" if obj else None,
            "namespace": event.metadata.namespace,
            "message": event.message,
            "count": event.count or 1,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }

    async def get_events(self, namespace: Optional[str] = None, name: Optional[str] = None,
                         kind: Optional[str] = None, event_type: Optional[str] = None,
                         limit: int = 50) -> List[Dict[str, Any]]:
        """
        List events, newest first.

        Args:
            namespace: Namespace to filter events (None for all namespaces)
            name: Only events about the object with this name
            kind: Only events about objects of this kind (e.g., Pod, Deployment)
            event_type: Only events of this type (Normal or Warning)
            limit: Maximum number of events to return

        Returns:
            List of event information dictionaries
        """
        selectors = []
        if name:
            selectors.append(f"involvedObject.name={name}")
        if kind:
            selectors.append(f"involvedObject.kind={kind}")
        if event_type:
            selectors.append(f"type={event_type}")
        field_selector = ",".join(selectors)

        try:
            if namespace:
                events = self.core_v1.list_namespaced_event(
                    namespace=namespace, field_selector=field_selector
                )
            else:
                events = self.core_v1.list_event_for_all_namespaces(field_selector=field_selector)
        except ApiException as e:
            raise Exception(f"Failed to list events: {e}")

        formatted = [self._format_event(ev) for ev in events.items]
        formatted.sort(key=lambda ev: ev["last_seen"] or "", reverse=True)
        return formatted[:limit]

    @staticmethod
    def _format_container_state(state) -> Optional[Dict[str, Any]]:
        """Format a container state (waiting, running or terminated)."""
        if state is None:
            return None
        if state.waiting:
            return {"state": "waiting", "reason": state.waiting.reason,
                    "message": state.waiting.message}
        if state.running:
            started = state.running.started_at
            return {"state": "running", "started": started.isoformat() if started else None}
        if state.terminated:
            t = state.terminated
            return {
                "state": "terminated",
                "reason": t.reason,
                "exit_code": t.exit_code,
                "message": t.message,
                "finished": t.finished_at.isoformat() if t.finished_at else None,
            }
        return None

    async def describe_pod(self, name: str, namespace: str) -> Dict[str, Any]:
        """
        Describe a pod: status, conditions, container states and recent events.

        Environment variables are left out because they can hold credentials.

        Args:
            name: Pod name
            namespace: Namespace

        Returns:
            Pod details dictionary
        """
        try:
            pod = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
        except ApiException as e:
            raise Exception(f"Failed to get pod {name}: {e}")

        specs = {c.name: c for c in (pod.spec.init_containers or []) + pod.spec.containers}
        statuses = (pod.status.init_container_statuses or []) + (pod.status.container_statuses or [])
        init_names = {c.name for c in pod.spec.init_containers or []}

        containers = []
        for cs in statuses:
            spec = specs.get(cs.name)
            resources = spec.resources if spec else None
            containers.append({
                "name": cs.name,
                "init": cs.name in init_names,
                "image": cs.image,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
                "state": self._format_container_state(cs.state),
                "last_state": self._format_container_state(cs.last_state),
                "requests": (resources.requests or {}) if resources else {},
                "limits": (resources.limits or {}) if resources else {},
            })

        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "reason": pod.status.reason,
            "message": pod.status.message,
            "node": pod.spec.node_name,
            "pod_ip": pod.status.pod_ip,
            "qos_class": pod.status.qos_class,
            "owners": [f"{o.kind}/{o.name}" for o in pod.metadata.owner_references or []],
            "labels": pod.metadata.labels or {},
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                for c in pod.status.conditions or []
            ],
            "containers": containers,
            "events": await self.get_events(namespace=namespace, name=name, kind="Pod", limit=20),
        }

    @staticmethod
    def _format_usage(usage: Dict[str, str]) -> Dict[str, Any]:
        """Convert metrics-server quantities to millicores and MiB."""
        return {
            "cpu_millicores": round(parse_quantity(usage.get("cpu", "0")) * 1000),
            "memory_mib": round(parse_quantity(usage.get("memory", "0")) / 2**20),
        }

    async def get_resource_usage(self, kind: str = "pods",
                                 namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get current CPU and memory usage from metrics-server.

        Args:
            kind: "pods" or "nodes"
            namespace: Namespace to filter pods (None for all namespaces; ignored for nodes)

        Returns:
            List of usage dictionaries
        """
        group, version = "metrics.k8s.io", "v1beta1"
        try:
            if kind == "nodes":
                items = self.custom_objects.list_cluster_custom_object(group, version, "nodes")
                allocatable = {
                    n.metadata.name: self._format_usage(n.status.allocatable or {})
                    for n in self.core_v1.list_node().items
                }
                nodes = []
                for i in items.get("items", []):
                    name = i["metadata"]["name"]
                    usage = self._format_usage(i.get("usage", {}))
                    alloc = allocatable.get(name)
                    if alloc:
                        usage["cpu_percent"] = round(
                            100 * usage["cpu_millicores"] / alloc["cpu_millicores"]
                        ) if alloc["cpu_millicores"] else None
                        usage["memory_percent"] = round(
                            100 * usage["memory_mib"] / alloc["memory_mib"]
                        ) if alloc["memory_mib"] else None
                    nodes.append({"name": name, **usage})
                return nodes
            if kind != "pods":
                raise ValueError(f"kind must be 'pods' or 'nodes', not {kind!r}")
            if namespace:
                items = self.custom_objects.list_namespaced_custom_object(
                    group, version, namespace, "pods"
                )
            else:
                items = self.custom_objects.list_cluster_custom_object(group, version, "pods")
        except ApiException as e:
            if e.status == 404:
                raise Exception("Metrics API not available: is metrics-server installed?")
            raise Exception(f"Failed to get resource usage: {e}")

        return [
            {
                "name": i["metadata"]["name"],
                "namespace": i["metadata"]["namespace"],
                "containers": [
                    {"name": c["name"], **self._format_usage(c.get("usage", {}))}
                    for c in i.get("containers", [])
                ],
            }
            for i in items.get("items", [])
        ]

    async def execute_command(self, pod_name: str, namespace: str, command: List[str],
                             container: Optional[str] = None) -> str:
        """
        Execute a command in a pod.

        Args:
            pod_name: Pod name
            namespace: Namespace
            command: Command to execute (as list of strings)
            container: Container name (optional)

        Returns:
            Command output
        """
        try:
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                container=container,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            return resp
        except ApiException as e:
            raise Exception(f"Failed to execute command in pod {pod_name}: {e}")

    @property
    def dynamic(self) -> DynamicClient:
        """Dynamic client for any kind, created on first use (it runs API discovery)."""
        if self._dynamic is None:
            self._dynamic = DynamicClient(client.ApiClient())
        return self._dynamic

    @staticmethod
    def _api_error_message(e: ApiException) -> str:
        """Pull the API server's message out of an ApiException."""
        try:
            return json.loads(e.body)["message"]
        except (TypeError, ValueError, KeyError):
            return f"{e.status} {e.reason}"

    @staticmethod
    def _content(obj) -> Dict[str, Any]:
        """An object as a dict, minus field-ownership bookkeeping."""
        data = obj.to_dict()
        meta = data.get("metadata", {})
        for key in ("managedFields", "resourceVersion"):
            meta.pop(key, None)
        return data

    async def apply_manifest(self, manifest_yaml: str, namespace: Optional[str] = None,
                             dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
        """
        Apply a Kubernetes manifest with server-side apply, like `kubectl apply --server-side`.

        Creates objects that don't exist and updates ones that do. Accepts several
        YAML documents separated by `---`, List kinds, and any kind the cluster
        knows, including custom resources. Each document is applied on its own,
        so one failure doesn't stop the rest.

        Args:
            manifest_yaml: YAML manifest content (one or more documents)
            namespace: Namespace for namespaced objects; overrides metadata.namespace
            dry_run: Validate on the server without saving anything
            force: Take ownership of fields another manager owns (resolves conflicts)

        Returns:
            Per-document results
        """
        try:
            docs = [d for d in yaml.safe_load_all(manifest_yaml) if d]
        except yaml.YAMLError as e:
            raise Exception(f"Failed to parse YAML manifest: {e}")

        objects = []
        for doc in docs:
            if not isinstance(doc, dict):
                raise Exception("Each YAML document must be a mapping")
            if doc.get("kind", "").endswith("List") and isinstance(doc.get("items"), list):
                objects.extend(doc["items"])
            else:
                objects.append(doc)
        if not objects:
            raise Exception("Manifest contains no objects")

        results = []
        for obj in objects:
            kind = obj.get("kind")
            api_version = obj.get("apiVersion")
            metadata = obj.setdefault("metadata", {})
            name = metadata.get("name")
            entry: Dict[str, Any] = {"kind": kind, "name": name}

            try:
                if not kind or not api_version:
                    raise ValueError("apiVersion and kind are required")
                if not name:
                    raise ValueError("metadata.name is required (generateName isn't supported)")

                resource = self.dynamic.resources.get(api_version=api_version, kind=kind)
                obj_namespace = None
                if resource.namespaced:
                    obj_namespace = namespace or metadata.get("namespace") or DEFAULT_NAMESPACE
                    metadata["namespace"] = obj_namespace
                    entry["namespace"] = obj_namespace

                try:
                    before = self._content(resource.get(name=name, namespace=obj_namespace))
                except NotFoundError:
                    before = None

                applied = resource.server_side_apply(
                    body=obj,
                    name=name,
                    namespace=obj_namespace,
                    field_manager=FIELD_MANAGER,
                    force_conflicts=force or None,
                    dry_run="All" if dry_run else None,
                )

                # Compare content only: a first apply over kubectl-made objects adds a
                # managedFields entry (and a new resourceVersion) without changing them
                if before is None:
                    entry["action"] = "created"
                elif self._content(applied) == before:
                    entry["action"] = "unchanged"
                else:
                    entry["action"] = "configured"
            except ResourceNotFoundError:
                entry["error"] = f"The cluster has no kind {kind} in {api_version}"
            except ApiException as e:
                entry["error"] = self._api_error_message(e)
            except ValueError as e:
                entry["error"] = str(e)
            results.append(entry)

        failed = sum(1 for r in results if "error" in r)
        return {
            "dry_run": dry_run,
            "applied": len(results) - failed,
            "failed": failed,
            "results": results,
        }

    def _resolve_kind(self, kind: str, api_version: Optional[str] = None):
        """
        Find the API resource for a kind, like kubectl does.

        Accepts the kind (Deployment), plural (deployments), singular (deployment)
        or short name (deploy), in any case. When a kind exists in several API
        groups, the core and apps groups win; otherwise api_version is required.
        """
        resources = self.dynamic.resources
        lowered = kind.lower()
        filters = {} if api_version is None else {"api_version": api_version}

        candidates = []
        for kw in ({"kind": kind}, {"singular_name": lowered}, {"name": lowered},
                   {"short_names": [lowered]}):
            candidates.extend(resources.search(**kw, **filters))
        if api_version is None:
            # Case-insensitive match on the kind itself, e.g. "configmap"
            candidates.extend(r for r in resources.search()
                              if getattr(r, "kind", "").lower() == lowered)

        unique = {}
        for r in candidates:
            if r.kind.endswith("List") or "/" in r.name:
                continue
            unique.setdefault((r.group_version, r.kind), r)
        found = list(unique.values())

        if not found:
            where = f" in {api_version}" if api_version else ""
            raise Exception(f"The cluster has no kind {kind!r}{where}")
        if len(found) > 1:
            preferred = [r for r in found if r.group_version in ("v1", "apps/v1")]
            if len(preferred) == 1:
                return preferred[0]
            options = ", ".join(f"{r.group_version} {r.kind}" for r in found)
            raise Exception(f"{kind!r} is ambiguous ({options}); pass api_version")
        return found[0]

    async def get_resource(self, kind: str, name: Optional[str] = None,
                           namespace: Optional[str] = None, api_version: Optional[str] = None,
                           labels: Optional[str] = None, limit: int = 100) -> Any:
        """
        Read objects of any kind, including custom resources.

        Without a name, lists objects with a short summary. With a name, returns
        the whole object minus managedFields. Secrets are refused so their values
        never reach the conversation.

        Args:
            kind: Kind, plural, singular or short name
            name: Object name (omit to list)
            namespace: Namespace (omit to list all namespaces; ignored for cluster-scoped kinds)
            api_version: API group/version, needed only when the kind is ambiguous
            labels: Label selector when listing
            limit: Maximum number of objects when listing
        """
        resource = self._resolve_kind(kind, api_version)
        if resource.group_version == "v1" and resource.kind == "Secret":
            raise Exception("Reading Secrets isn't supported: their values would end up in "
                            "the conversation")
        obj_namespace = namespace if resource.namespaced else None

        try:
            if name:
                obj = resource.get(name=name, namespace=obj_namespace).to_dict()
                obj.get("metadata", {}).pop("managedFields", None)
                return obj
            result = resource.get(namespace=obj_namespace, label_selector=labels or None,
                                  limit=limit)
        except ApiException as e:
            target = f"{resource.kind} {name}" if name else resource.name
            raise Exception(f"Failed to get {target}: {self._api_error_message(e)}")

        items = []
        for item in result.to_dict().get("items", []):
            meta = item.get("metadata", {})
            summary = {"name": meta.get("name")}
            if resource.namespaced:
                summary["namespace"] = meta.get("namespace")
            summary["created"] = meta.get("creationTimestamp")
            conditions = (item.get("status") or {}).get("conditions") or []
            ready = next((c for c in conditions if c.get("type") in ("Ready", "Available")), None)
            if ready:
                summary["ready"] = ready.get("status")
                if ready.get("status") != "True" and ready.get("message"):
                    summary["message"] = ready.get("message")
            items.append(summary)
        response = {"kind": resource.kind, "api_version": resource.group_version,
                    "count": len(items), "items": items}
        if (result.to_dict().get("metadata") or {}).get("continue"):
            response["truncated"] = f"More than {limit} objects; narrow with namespace or labels"
        return response

    async def delete_resource(self, kind: str, name: str, namespace: str,
                              api_version: Optional[str] = None,
                              dry_run: bool = False) -> Dict[str, Any]:
        """
        Delete a Kubernetes object of any kind, including custom resources.

        Args:
            kind: Kind, plural, singular or short name (Deployment, deployments, deploy)
            name: Object name
            namespace: Namespace (ignored for cluster-scoped kinds)
            api_version: API group/version, needed only when the kind is ambiguous
            dry_run: Check the delete on the server without doing it

        Returns:
            Deletion status
        """
        resource = self._resolve_kind(kind, api_version)
        obj_namespace = namespace if resource.namespaced else None
        # The API server reads delete options from the body when there is one and
        # then ignores the query string, so dryRun must go in the body too.
        options: Dict[str, Any] = {"propagationPolicy": "Background"}
        if dry_run:
            options["dryRun"] = ["All"]
        try:
            resource.delete(name=name, namespace=obj_namespace, body=options)
        except ApiException as e:
            raise Exception(f"Failed to delete {resource.kind} {name}: {self._api_error_message(e)}")

        result = {"kind": resource.kind, "api_version": resource.group_version, "name": name}
        if obj_namespace:
            result["namespace"] = obj_namespace
        result["status"] = "Would be deleted (dry run)" if dry_run else "Deleted"
        return result

    async def get_namespaces(self) -> List[Dict[str, Any]]:
        """
        List all namespaces in the cluster.

        Returns:
            List of namespace information dictionaries
        """
        try:
            namespaces = self.core_v1.list_namespace()
            return [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "created": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None,
                    "labels": ns.metadata.labels or {},
                }
                for ns in namespaces.items
            ]
        except ApiException as e:
            raise Exception(f"Failed to list namespaces: {e}")

    async def get_cluster_info(self) -> Dict[str, Any]:
        """
        Get cluster information.

        Returns:
            Cluster information dictionary
        """
        try:
            # Get version
            version = client.VersionApi().get_code()

            # Get nodes summary
            nodes = await self.get_nodes()

            # Get namespaces count
            namespaces = await self.get_namespaces()

            return {
                "version": {
                    "major": version.major,
                    "minor": version.minor,
                    "git_version": version.git_version,
                    "platform": version.platform,
                },
                "nodes": {
                    "total": len(nodes),
                    "ready": sum(1 for n in nodes if n["status"] == "Ready"),
                },
                "namespaces": {
                    "total": len(namespaces),
                    "list": [ns["name"] for ns in namespaces],
                },
            }
        except ApiException as e:
            raise Exception(f"Failed to get cluster info: {e}")


# Initialize K3s client
k3s = K3sClient()

# Initialize MCP server
app = Server("k3s-mcp-server", version=__version__)


# Define tools
TOOLS = [
    Tool(
        name="get_pods",
        description="List pods in a namespace or across all namespaces. Supports label selectors for filtering.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter pods (omit for all namespaces)"
                },
                "labels": {
                    "type": "string",
                    "description": "Label selector (e.g., 'app=nginx,env=prod')"
                }
            }
        },
    ),
    Tool(
        name="get_deployments",
        description="List deployments in a namespace or across all namespaces",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter deployments (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_deployment",
        description="Get detailed information about a specific deployment",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="get_services",
        description="List services in a namespace or across all namespaces",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter services (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_statefulsets",
        description="List StatefulSets in a namespace or across all namespaces, with replica counts, governing service and images",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter StatefulSets (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_daemonsets",
        description="List DaemonSets in a namespace or across all namespaces, with desired, ready and available counts, node selector and images",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter DaemonSets (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_jobs",
        description="List Jobs in a namespace or across all namespaces, with status (Complete, Failed, Running), succeeded and failed counts, times and the CronJob that created them",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter Jobs (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_cronjobs",
        description="List CronJobs in a namespace or across all namespaces, with schedule, suspended flag, active runs and last scheduled and successful times",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter CronJobs (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_ingresses",
        description="List Ingresses in a namespace or across all namespaces, with class, hosts, paths and backend services, TLS hosts and load balancer addresses",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter Ingresses (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_configmaps",
        description="List ConfigMaps with their keys, or pass a name to read one ConfigMap's data (long values are truncated)",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace (omit to list all namespaces; with name, defaults to the default namespace)"},
                "name": {"type": "string", "description": "ConfigMap name, to return its data"}
            }
        },
    ),
    Tool(
        name="get_pvcs",
        description="List PersistentVolumeClaims in a namespace or across all namespaces, with status, requested and actual size, access modes, storage class and bound volume",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter PersistentVolumeClaims (omit for all namespaces)"
                }
            }
        },
    ),
    Tool(
        name="get_resource",
        description="Read objects of any kind, including custom resources such as K3s HelmCharts, Traefik IngressRoutes or cert-manager Certificates. Without a name it lists objects with a short summary; with a name it returns the whole object. Secrets are refused.",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "Kind, plural or short name, e.g. HelmChart, certificates, sts"},
                "name": {"type": "string", "description": "Object name (omit to list)"},
                "namespace": {"type": "string", "description": "Namespace (omit to list all namespaces; ignored for cluster-scoped kinds)"},
                "api_version": {"type": "string", "description": "API group/version, e.g. traefik.io/v1alpha1; only needed when the kind exists in several groups"},
                "labels": {"type": "string", "description": "Label selector when listing"},
                "limit": {"type": "integer", "description": "Maximum objects when listing (default: 100)"}
            },
            "required": ["kind"]
        },
    ),
    Tool(
        name="rollout_status",
        description="Check whether a Deployment, StatefulSet or DaemonSet has finished rolling out, with updated, ready and available counts. Can wait for it to finish.",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["Deployment", "StatefulSet", "DaemonSet"], "description": "Workload kind (default: Deployment)"},
                "name": {"type": "string", "description": "Workload name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"},
                "wait_seconds": {"type": "integer", "description": "Keep checking until done or this many seconds pass (default: 0, max: 300)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="rollout_history",
        description="List a Deployment's revisions with their images and change cause, newest first",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="get_nodes",
        description="List all nodes in the cluster with resource information",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="scale_deployment",
        description="Scale a deployment to a specific number of replicas",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"},
                "replicas": {"type": "integer", "description": "Desired replica count"}
            },
            "required": ["name", "replicas"]
        },
    ),
    Tool(
        name="restart_pod",
        description="Restart a pod by deleting it (will be recreated by its controller)",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="get_logs",
        description="Get logs from a pod. Can specify container and number of lines to tail.",
        inputSchema={
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"},
                "container": {"type": "string", "description": "Container name (optional)"},
                "tail_lines": {"type": "integer", "description": "Number of lines to tail (default: 100)"},
                "previous": {
                    "type": "boolean",
                    "description": "Logs from the previous container instance, e.g. after a crash (default: false)"
                }
            },
            "required": ["pod_name"]
        },
    ),
    Tool(
        name="get_events",
        description="List cluster events, newest first. Filter by namespace, object name, kind, or type (Warning) to see why something is failing.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to filter events (omit for all namespaces)"},
                "name": {"type": "string", "description": "Only events about the object with this name"},
                "kind": {"type": "string", "description": "Only events about this kind, e.g. Pod or Deployment"},
                "type": {"type": "string", "enum": ["Normal", "Warning"], "description": "Only events of this type"},
                "limit": {"type": "integer", "description": "Maximum number of events (default: 50)"}
            }
        },
    ),
    Tool(
        name="describe_pod",
        description="Describe a pod: phase, conditions, each container's state, restarts, last termination reason and exit code, resources, and recent events. Environment variables are not included.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="get_resource_usage",
        description="Current CPU (millicores) and memory (MiB) usage for pods or nodes, from metrics-server (bundled with K3s). Nodes include percent of allocatable.",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["pods", "nodes"], "description": "pods or nodes (default: pods)"},
                "namespace": {"type": "string", "description": "Namespace to filter pods (omit for all namespaces)"}
            }
        },
    ),
    Tool(
        name="rollout_restart",
        description="Restart all pods of a Deployment, StatefulSet or DaemonSet with a rolling update, like kubectl rollout restart",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["Deployment", "StatefulSet", "DaemonSet"], "description": "Workload kind (default: Deployment)"},
                "name": {"type": "string", "description": "Workload name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="rollout_undo",
        description="Roll a Deployment back to an earlier revision (default: the previous one), like kubectl rollout undo",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"},
                "to_revision": {"type": "integer", "description": "Revision to roll back to (see rollout_history)"}
            },
            "required": ["name"]
        },
    ),
    Tool(
        name="cordon_node",
        description="Mark a node unschedulable so no new pods land on it; running pods stay. Needs permission to patch nodes, which deploy/rbac.yaml doesn't grant by default.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Node name"}},
            "required": ["name"]
        },
    ),
    Tool(
        name="uncordon_node",
        description="Mark a node schedulable again after cordon_node",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Node name"}},
            "required": ["name"]
        },
    ),
    Tool(
        name="execute_command",
        description="Execute a command in a pod container",
        inputSchema={
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command to execute as array (e.g., ['ls', '-la'])"
                },
                "container": {"type": "string", "description": "Container name (optional)"}
            },
            "required": ["pod_name", "command"]
        },
    ),
    Tool(
        name="apply_manifest",
        description="Apply a Kubernetes YAML manifest with server-side apply: creates objects or updates existing ones. Accepts several documents separated by ---, and any kind the cluster knows, including custom resources.",
        inputSchema={
            "type": "object",
            "properties": {
                "manifest_yaml": {"type": "string", "description": "YAML manifest content (one or more documents)"},
                "namespace": {"type": "string", "description": "Namespace for namespaced objects; overrides metadata.namespace (optional)"},
                "dry_run": {"type": "boolean", "description": "Validate on the server without saving anything (default: false)"},
                "force": {"type": "boolean", "description": "Take over fields owned by another field manager to resolve apply conflicts (default: false)"}
            },
            "required": ["manifest_yaml"]
        },
    ),
    Tool(
        name="delete_resource",
        description="Delete a Kubernetes object of any kind, including custom resources. Accepts kind, plural or short names (Deployment, deployments, deploy).",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "Kind, e.g. Pod, Deployment, ConfigMap, Ingress, or a custom resource kind"},
                "name": {"type": "string", "description": "Object name"},
                "namespace": {"type": "string", "description": "Namespace (default: default; ignored for cluster-scoped kinds)"},
                "api_version": {"type": "string", "description": "API group/version, e.g. apps/v1; only needed when the kind exists in several groups"},
                "dry_run": {"type": "boolean", "description": "Check the delete on the server without doing it (default: false)"}
            },
            "required": ["kind", "name"]
        },
    ),
    Tool(
        name="get_namespaces",
        description="List all namespaces in the cluster",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_cluster_info",
        description="Get cluster information including version, nodes, and namespaces",
        inputSchema={"type": "object", "properties": {}},
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """
    Handle tool calls from Claude.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of text content responses
    """
    try:
        # Get default namespace if not provided
        if "namespace" in arguments and not arguments.get("namespace"):
            arguments["namespace"] = DEFAULT_NAMESPACE

        # Route to appropriate handler
        if name == "get_pods":
            result = await k3s.get_pods(
                namespace=arguments.get("namespace"),
                labels=arguments.get("labels")
            )
        elif name == "get_deployments":
            result = await k3s.get_deployments(namespace=arguments.get("namespace"))
        elif name == "get_deployment":
            result = await k3s.get_deployment(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
            )
        elif name == "get_services":
            result = await k3s.get_services(namespace=arguments.get("namespace"))
        elif name in ("get_statefulsets", "get_daemonsets", "get_jobs", "get_cronjobs",
                      "get_ingresses", "get_pvcs"):
            result = await getattr(k3s, name)(namespace=arguments.get("namespace"))
        elif name == "get_configmaps":
            namespace = arguments.get("namespace")
            if arguments.get("name") and not namespace:
                namespace = DEFAULT_NAMESPACE
            result = await k3s.get_configmaps(namespace=namespace, name=arguments.get("name"))
        elif name == "get_resource":
            result = await k3s.get_resource(
                kind=arguments["kind"],
                name=arguments.get("name"),
                namespace=arguments.get("namespace"),
                api_version=arguments.get("api_version"),
                labels=arguments.get("labels"),
                limit=arguments.get("limit", 100)
            )
        elif name == "rollout_status":
            result = await k3s.rollout_status(
                kind=arguments.get("kind", "Deployment"),
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                wait_seconds=arguments.get("wait_seconds", 0)
            )
        elif name == "rollout_history":
            result = await k3s.rollout_history(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
            )
        elif name == "rollout_restart":
            result = await k3s.rollout_restart(
                kind=arguments.get("kind", "Deployment"),
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
            )
        elif name == "rollout_undo":
            result = await k3s.rollout_undo(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                to_revision=arguments.get("to_revision")
            )
        elif name in ("cordon_node", "uncordon_node"):
            result = await k3s.set_node_schedulable(
                name=arguments["name"], schedulable=(name == "uncordon_node")
            )
        elif name == "get_nodes":
            result = await k3s.get_nodes()
        elif name == "scale_deployment":
            result = await k3s.scale_deployment(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                replicas=arguments["replicas"]
            )
        elif name == "restart_pod":
            result = await k3s.restart_pod(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
            )
        elif name == "get_logs":
            result = await k3s.get_logs(
                pod_name=arguments["pod_name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                container=arguments.get("container"),
                tail_lines=arguments.get("tail_lines", 100),
                previous=arguments.get("previous", False)
            )
        elif name == "get_events":
            result = await k3s.get_events(
                namespace=arguments.get("namespace"),
                name=arguments.get("name"),
                kind=arguments.get("kind"),
                event_type=arguments.get("type"),
                limit=arguments.get("limit", 50)
            )
        elif name == "describe_pod":
            result = await k3s.describe_pod(
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
            )
        elif name == "get_resource_usage":
            result = await k3s.get_resource_usage(
                kind=arguments.get("kind", "pods"),
                namespace=arguments.get("namespace")
            )
        elif name == "execute_command":
            result = await k3s.execute_command(
                pod_name=arguments["pod_name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                command=arguments["command"],
                container=arguments.get("container")
            )
        elif name == "apply_manifest":
            result = await k3s.apply_manifest(
                manifest_yaml=arguments["manifest_yaml"],
                namespace=arguments.get("namespace"),
                dry_run=arguments.get("dry_run", False),
                force=arguments.get("force", False)
            )
        elif name == "delete_resource":
            result = await k3s.delete_resource(
                kind=arguments["kind"],
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE),
                api_version=arguments.get("api_version"),
                dry_run=arguments.get("dry_run", False)
            )
        elif name == "get_namespaces":
            result = await k3s.get_namespaces()
        elif name == "get_cluster_info":
            result = await k3s.get_cluster_info()
        else:
            raise ValueError(f"Unknown tool: {name}")

        # Format response
        if isinstance(result, str):
            # For logs and command output
            return [TextContent(type="text", text=result)]
        else:
            # For structured data
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        error_msg = f"Error executing {name}: {str(e)}"
        print(error_msg, file=sys.stderr)
        return [TextContent(type="text", text=error_msg)]


async def main():
    """Main entry point for the MCP server."""
    print("Starting K3s MCP Server...", file=sys.stderr)
    print(f"Using kubeconfig: {KUBECONFIG}", file=sys.stderr)
    print(f"Default namespace: {DEFAULT_NAMESPACE}", file=sys.stderr)

    # Run the server
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def run():
    """Console-script entry point."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
