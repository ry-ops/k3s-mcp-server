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
Version: 1.0.0
"""

import os
import sys
import json
import yaml
from typing import Any, Optional, Dict, List
from pathlib import Path

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio


# Configuration
KUBECONFIG = os.getenv("KUBECONFIG", str(Path.home() / ".kube" / "k3s-cortex-config.yaml"))
DEFAULT_NAMESPACE = os.getenv("K3S_DEFAULT_NAMESPACE", "default")
DEBUG = os.getenv("K3S_DEBUG", "false").lower() == "true"


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
            "roles": [label.split("/")[1] for label in (node.metadata.labels or {}) if label.startswith("node-role.kubernetes.io/")],
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
            deployment = self.apps_v1.patch_namespaced_deployment_scale(
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

    async def get_logs(self, pod_name: str, namespace: str, container: Optional[str] = None,
                      tail_lines: int = 100, follow: bool = False) -> str:
        """
        Get logs from a pod.

        Args:
            pod_name: Pod name
            namespace: Namespace
            container: Container name (optional, uses first container if not specified)
            tail_lines: Number of lines to tail
            follow: Stream logs (not implemented for MCP)

        Returns:
            Pod logs as string
        """
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            raise Exception(f"Failed to get logs for pod {pod_name}: {e}")

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

    async def apply_manifest(self, manifest_yaml: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        Apply a Kubernetes manifest.

        Args:
            manifest_yaml: YAML manifest content
            namespace: Namespace override (optional)

        Returns:
            Applied resource information
        """
        try:
            # Parse YAML
            manifest = yaml.safe_load(manifest_yaml)

            # Determine resource type and apply
            kind = manifest.get("kind")
            api_version = manifest.get("apiVersion")
            metadata = manifest.get("metadata", {})
            resource_namespace = namespace or metadata.get("namespace", DEFAULT_NAMESPACE)

            # Add namespace to metadata if not present
            if "namespace" not in metadata and kind not in ["Namespace", "Node", "PersistentVolume", "ClusterRole", "ClusterRoleBinding"]:
                manifest["metadata"]["namespace"] = resource_namespace

            # Apply based on kind
            if kind == "Pod":
                result = self.core_v1.create_namespaced_pod(
                    namespace=resource_namespace,
                    body=manifest
                )
            elif kind == "Deployment":
                result = self.apps_v1.create_namespaced_deployment(
                    namespace=resource_namespace,
                    body=manifest
                )
            elif kind == "Service":
                result = self.core_v1.create_namespaced_service(
                    namespace=resource_namespace,
                    body=manifest
                )
            else:
                raise Exception(f"Unsupported resource kind: {kind}")

            return {
                "kind": kind,
                "name": result.metadata.name,
                "namespace": result.metadata.namespace if hasattr(result.metadata, 'namespace') else None,
                "status": "Created successfully"
            }
        except yaml.YAMLError as e:
            raise Exception(f"Failed to parse YAML manifest: {e}")
        except ApiException as e:
            raise Exception(f"Failed to apply manifest: {e}")

    async def delete_resource(self, kind: str, name: str, namespace: str) -> Dict[str, Any]:
        """
        Delete a Kubernetes resource.

        Args:
            kind: Resource kind (Pod, Deployment, Service, etc.)
            name: Resource name
            namespace: Namespace

        Returns:
            Deletion status
        """
        try:
            if kind.lower() == "pod":
                self.core_v1.delete_namespaced_pod(name=name, namespace=namespace)
            elif kind.lower() == "deployment":
                self.apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
            elif kind.lower() == "service":
                self.core_v1.delete_namespaced_service(name=name, namespace=namespace)
            else:
                raise Exception(f"Unsupported resource kind for deletion: {kind}")

            return {
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "status": "Deleted successfully"
            }
        except ApiException as e:
            raise Exception(f"Failed to delete {kind} {name}: {e}")

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
app = Server("k3s-mcp-server")


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
                "tail_lines": {"type": "integer", "description": "Number of lines to tail (default: 100)"}
            },
            "required": ["pod_name"]
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
        description="Apply a Kubernetes YAML manifest to create or update resources",
        inputSchema={
            "type": "object",
            "properties": {
                "manifest_yaml": {"type": "string", "description": "YAML manifest content"},
                "namespace": {"type": "string", "description": "Namespace override (optional)"}
            },
            "required": ["manifest_yaml"]
        },
    ),
    Tool(
        name="delete_resource",
        description="Delete a Kubernetes resource (Pod, Deployment, Service, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "Resource kind (Pod, Deployment, Service)"},
                "name": {"type": "string", "description": "Resource name"},
                "namespace": {"type": "string", "description": "Namespace (default: default)"}
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
                tail_lines=arguments.get("tail_lines", 100)
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
                namespace=arguments.get("namespace")
            )
        elif name == "delete_resource":
            result = await k3s.delete_resource(
                kind=arguments["kind"],
                name=arguments["name"],
                namespace=arguments.get("namespace", DEFAULT_NAMESPACE)
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


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
