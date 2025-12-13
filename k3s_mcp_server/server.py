#!/usr/bin/env python3
"""
K3s MCP Server

An MCP server for interacting with Kubernetes (K3s) clusters.
Provides tools for managing pods, deployments, services, nodes, and more.

GitHub: https://github.com/ry-ops/k3s-mcp-server
Documentation: https://github.com/ry-ops/k3s-mcp-server#readme

Configuration via environment variables:
    KUBECONFIG: Path to kubeconfig file (required)
    K3S_DEFAULT_NAMESPACE: Default namespace (default: default)
    K3S_DEBUG: Enable debug logging (default: false)

Author: ry-ops
License: MIT
Version: 1.0.0
"""

import os
import sys
import json
import asyncio
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
KUBECONFIG_PATH = os.getenv(
    "KUBECONFIG",
    str(Path.home() / ".kube" / "k3s-cortex-config.yaml")
)
DEFAULT_NAMESPACE = os.getenv("K3S_DEFAULT_NAMESPACE", "default")
DEBUG = os.getenv("K3S_DEBUG", "false").lower() == "true"

# Validate kubeconfig exists
if not Path(KUBECONFIG_PATH).exists():
    print(f"Error: Kubeconfig not found at {KUBECONFIG_PATH}", file=sys.stderr)
    print("Set KUBECONFIG environment variable to point to your kubeconfig file", file=sys.stderr)
    sys.exit(1)


def debug_log(message: str):
    """Log debug messages if debug mode is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}", file=sys.stderr)


class K3sClient:
    """
    Client for interacting with K3s/Kubernetes API.

    Handles authentication via kubeconfig and provides methods for
    common kubectl operations.
    """

    def __init__(self):
        """Initialize the K3s/Kubernetes API client."""
        self.kubeconfig_path = KUBECONFIG_PATH
        self.default_namespace = DEFAULT_NAMESPACE

        # Load kubeconfig
        try:
            config.load_kube_config(config_file=self.kubeconfig_path)
            debug_log(f"Loaded kubeconfig from {self.kubeconfig_path}")
        except Exception as e:
            print(f"Error loading kubeconfig: {e}", file=sys.stderr)
            raise

        # Initialize API clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.dynamic_client = None

    async def get_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List pods in namespace or cluster-wide.

        Args:
            namespace: Namespace to list pods from (None for all namespaces)
            label_selector: Label selector to filter pods

        Returns:
            Dictionary with pod information
        """
        try:
            if namespace:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector or ""
                )
            else:
                pods = self.core_v1.list_pod_for_all_namespaces(
                    label_selector=label_selector or ""
                )

            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "node": pod.spec.node_name,
                    "ip": pod.status.pod_ip,
                    "conditions": [
                        {
                            "type": c.type,
                            "status": c.status,
                        }
                        for c in (pod.status.conditions or [])
                    ],
                    "containers": [
                        {
                            "name": c.name,
                            "image": c.image,
                            "ready": next(
                                (cs.ready for cs in pod.status.container_statuses or []
                                 if cs.name == c.name),
                                False
                            ),
                        }
                        for c in pod.spec.containers
                    ],
                }
                pod_list.append(pod_info)

            return {"pods": pod_list, "count": len(pod_list)}

        except ApiException as e:
            raise Exception(f"Failed to list pods: {e.reason}")

    async def get_pod_logs(
        self,
        pod_name: str,
        namespace: str,
        container: Optional[str] = None,
        tail_lines: int = 100,
    ) -> str:
        """
        Get logs from a pod.

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod
            container: Container name (optional, uses first container if not specified)
            tail_lines: Number of lines to tail

        Returns:
            Log output as string
        """
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
            )
            return logs

        except ApiException as e:
            raise Exception(f"Failed to get logs: {e.reason}")

    async def execute_command(
        self,
        pod_name: str,
        namespace: str,
        command: List[str],
        container: Optional[str] = None,
    ) -> str:
        """
        Execute a command in a pod.

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod
            command: Command to execute (as list)
            container: Container name (optional)

        Returns:
            Command output as string
        """
        try:
            exec_kwargs = {
                "name": pod_name,
                "namespace": namespace,
                "command": command,
                "stderr": True,
                "stdin": False,
                "stdout": True,
                "tty": False,
            }

            if container:
                exec_kwargs["container"] = container

            result = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                **exec_kwargs
            )

            return result

        except ApiException as e:
            raise Exception(f"Failed to execute command: {e.reason}")

    async def delete_pod(self, pod_name: str, namespace: str) -> Dict[str, Any]:
        """
        Delete a pod (useful for restarting).

        Args:
            pod_name: Name of the pod
            namespace: Namespace of the pod

        Returns:
            Result information
        """
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
            )
            return {"status": "deleted", "pod": pod_name, "namespace": namespace}

        except ApiException as e:
            raise Exception(f"Failed to delete pod: {e.reason}")

    async def get_deployments(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        List deployments.

        Args:
            namespace: Namespace to list from (None for all namespaces)

        Returns:
            Dictionary with deployment information
        """
        try:
            if namespace:
                deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deployments = self.apps_v1.list_deployment_for_all_namespaces()

            deployment_list = []
            for dep in deployments.items:
                deployment_info = {
                    "name": dep.metadata.name,
                    "namespace": dep.metadata.namespace,
                    "replicas": dep.spec.replicas,
                    "ready_replicas": dep.status.ready_replicas or 0,
                    "available_replicas": dep.status.available_replicas or 0,
                    "updated_replicas": dep.status.updated_replicas or 0,
                    "conditions": [
                        {
                            "type": c.type,
                            "status": c.status,
                            "reason": c.reason,
                        }
                        for c in (dep.status.conditions or [])
                    ],
                }
                deployment_list.append(deployment_info)

            return {"deployments": deployment_list, "count": len(deployment_list)}

        except ApiException as e:
            raise Exception(f"Failed to list deployments: {e.reason}")

    async def get_deployment(self, name: str, namespace: str) -> Dict[str, Any]:
        """
        Get specific deployment details.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            Deployment information
        """
        try:
            dep = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            return {
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "replicas": dep.spec.replicas,
                "ready_replicas": dep.status.ready_replicas or 0,
                "available_replicas": dep.status.available_replicas or 0,
                "selector": dep.spec.selector.match_labels,
                "strategy": dep.spec.strategy.type,
                "containers": [
                    {
                        "name": c.name,
                        "image": c.image,
                    }
                    for c in dep.spec.template.spec.containers
                ],
                "conditions": [
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason,
                        "message": c.message,
                    }
                    for c in (dep.status.conditions or [])
                ],
            }

        except ApiException as e:
            raise Exception(f"Failed to get deployment: {e.reason}")

    async def scale_deployment(
        self, name: str, namespace: str, replicas: int
    ) -> Dict[str, Any]:
        """
        Scale a deployment.

        Args:
            name: Deployment name
            namespace: Namespace
            replicas: Desired replica count

        Returns:
            Result information
        """
        try:
            # Get current deployment
            dep = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            # Update replicas
            dep.spec.replicas = replicas

            # Patch deployment
            self.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=dep,
            )

            return {
                "status": "scaled",
                "deployment": name,
                "namespace": namespace,
                "replicas": replicas,
            }

        except ApiException as e:
            raise Exception(f"Failed to scale deployment: {e.reason}")

    async def get_services(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        List services.

        Args:
            namespace: Namespace to list from (None for all namespaces)

        Returns:
            Dictionary with service information
        """
        try:
            if namespace:
                services = self.core_v1.list_namespaced_service(namespace=namespace)
            else:
                services = self.core_v1.list_service_for_all_namespaces()

            service_list = []
            for svc in services.items:
                service_info = {
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "type": svc.spec.type,
                    "cluster_ip": svc.spec.cluster_ip,
                    "ports": [
                        {
                            "name": p.name,
                            "port": p.port,
                            "target_port": str(p.target_port),
                            "protocol": p.protocol,
                            "node_port": p.node_port if p.node_port else None,
                        }
                        for p in (svc.spec.ports or [])
                    ],
                    "selector": svc.spec.selector or {},
                }
                service_list.append(service_info)

            return {"services": service_list, "count": len(service_list)}

        except ApiException as e:
            raise Exception(f"Failed to list services: {e.reason}")

    async def get_nodes(self) -> Dict[str, Any]:
        """
        List all nodes in the cluster.

        Returns:
            Dictionary with node information
        """
        try:
            nodes = self.core_v1.list_node()

            node_list = []
            for node in nodes.items:
                # Get node conditions
                conditions = {}
                for condition in (node.status.conditions or []):
                    conditions[condition.type] = condition.status

                node_info = {
                    "name": node.metadata.name,
                    "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                    "roles": [
                        label.split("/")[1]
                        for label in node.metadata.labels
                        if label.startswith("node-role.kubernetes.io/")
                    ],
                    "version": node.status.node_info.kubelet_version,
                    "os": node.status.node_info.os_image,
                    "kernel": node.status.node_info.kernel_version,
                    "container_runtime": node.status.node_info.container_runtime_version,
                    "capacity": {
                        "cpu": node.status.capacity.get("cpu"),
                        "memory": node.status.capacity.get("memory"),
                        "pods": node.status.capacity.get("pods"),
                    },
                    "allocatable": {
                        "cpu": node.status.allocatable.get("cpu"),
                        "memory": node.status.allocatable.get("memory"),
                        "pods": node.status.allocatable.get("pods"),
                    },
                    "addresses": [
                        {"type": addr.type, "address": addr.address}
                        for addr in node.status.addresses
                    ],
                    "conditions": conditions,
                }
                node_list.append(node_info)

            return {"nodes": node_list, "count": len(node_list)}

        except ApiException as e:
            raise Exception(f"Failed to list nodes: {e.reason}")

    async def get_namespaces(self) -> Dict[str, Any]:
        """
        List all namespaces.

        Returns:
            Dictionary with namespace information
        """
        try:
            namespaces = self.core_v1.list_namespace()

            namespace_list = [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                }
                for ns in namespaces.items
            ]

            return {"namespaces": namespace_list, "count": len(namespace_list)}

        except ApiException as e:
            raise Exception(f"Failed to list namespaces: {e.reason}")

    async def get_cluster_info(self) -> Dict[str, Any]:
        """
        Get cluster version and information.

        Returns:
            Dictionary with cluster information
        """
        try:
            version_api = client.VersionApi()
            version = version_api.get_code()

            # Get node count
            nodes = self.core_v1.list_node()
            node_count = len(nodes.items)

            # Get namespace count
            namespaces = self.core_v1.list_namespace()
            namespace_count = len(namespaces.items)

            return {
                "version": {
                    "major": version.major,
                    "minor": version.minor,
                    "git_version": version.git_version,
                    "platform": version.platform,
                },
                "node_count": node_count,
                "namespace_count": namespace_count,
            }

        except ApiException as e:
            raise Exception(f"Failed to get cluster info: {e.reason}")

    async def apply_manifest(self, manifest_yaml: str, namespace: Optional[str] = None):
        """
        Apply a YAML manifest to the cluster.

        Args:
            manifest_yaml: YAML manifest content
            namespace: Namespace to apply to (optional, uses manifest namespace if not specified)

        Returns:
            Result information
        """
        try:
            # Parse YAML
            manifests = list(yaml.safe_load_all(manifest_yaml))

            results = []
            for manifest in manifests:
                if not manifest:
                    continue

                kind = manifest.get("kind")
                metadata = manifest.get("metadata", {})
                name = metadata.get("name")
                obj_namespace = namespace or metadata.get("namespace", self.default_namespace)

                # Apply based on kind
                if kind == "Pod":
                    result = self.core_v1.create_namespaced_pod(
                        namespace=obj_namespace,
                        body=manifest,
                    )
                    results.append(f"Created Pod {name} in {obj_namespace}")

                elif kind == "Deployment":
                    result = self.apps_v1.create_namespaced_deployment(
                        namespace=obj_namespace,
                        body=manifest,
                    )
                    results.append(f"Created Deployment {name} in {obj_namespace}")

                elif kind == "Service":
                    result = self.core_v1.create_namespaced_service(
                        namespace=obj_namespace,
                        body=manifest,
                    )
                    results.append(f"Created Service {name} in {obj_namespace}")

                else:
                    results.append(f"Warning: Unsupported kind {kind} for {name}")

            return {"status": "applied", "results": results}

        except ApiException as e:
            raise Exception(f"Failed to apply manifest: {e.reason}")
        except yaml.YAMLError as e:
            raise Exception(f"Invalid YAML: {e}")

    async def delete_resource(
        self, kind: str, name: str, namespace: str
    ) -> Dict[str, Any]:
        """
        Delete a resource.

        Args:
            kind: Resource kind (Pod, Deployment, Service)
            name: Resource name
            namespace: Namespace

        Returns:
            Result information
        """
        try:
            if kind == "Pod":
                self.core_v1.delete_namespaced_pod(name=name, namespace=namespace)
            elif kind == "Deployment":
                self.apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
            elif kind == "Service":
                self.core_v1.delete_namespaced_service(name=name, namespace=namespace)
            else:
                raise Exception(f"Unsupported resource kind: {kind}")

            return {
                "status": "deleted",
                "kind": kind,
                "name": name,
                "namespace": namespace,
            }

        except ApiException as e:
            raise Exception(f"Failed to delete resource: {e.reason}")


# Initialize client
k3s_client = K3sClient()

# Initialize MCP server
app = Server("k3s-mcp-server")


# Define tools
TOOLS = [
    # Pod tools
    Tool(
        name="get_pods",
        description="List pods in namespace or cluster-wide with optional label selector",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list pods from (omit for all namespaces)",
                },
                "labels": {
                    "type": "string",
                    "description": "Label selector (e.g., 'app=cortex,env=prod')",
                },
            },
        },
    ),
    Tool(
        name="get_logs",
        description="Get logs from a pod",
        inputSchema={
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace"},
                "container": {
                    "type": "string",
                    "description": "Container name (optional, uses first container if omitted)",
                },
                "tail_lines": {
                    "type": "integer",
                    "description": "Number of lines to tail (default: 100)",
                },
            },
            "required": ["pod_name", "namespace"],
        },
    ),
    Tool(
        name="execute_command",
        description="Execute a command in a pod container",
        inputSchema={
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command to execute as array (e.g., ['ls', '-la'])",
                },
                "container": {
                    "type": "string",
                    "description": "Container name (optional)",
                },
            },
            "required": ["pod_name", "namespace", "command"],
        },
    ),
    Tool(
        name="restart_pod",
        description="Restart a pod by deleting it (will be recreated by deployment/replicaset)",
        inputSchema={
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Namespace"},
            },
            "required": ["pod_name", "namespace"],
        },
    ),

    # Deployment tools
    Tool(
        name="get_deployments",
        description="List all deployments in namespace or cluster-wide",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list from (omit for all namespaces)",
                },
            },
        },
    ),
    Tool(
        name="get_deployment",
        description="Get detailed information about a specific deployment",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace"},
            },
            "required": ["name", "namespace"],
        },
    ),
    Tool(
        name="scale_deployment",
        description="Scale a deployment to specified number of replicas",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "description": "Namespace"},
                "replicas": {
                    "type": "integer",
                    "description": "Desired number of replicas",
                },
            },
            "required": ["name", "namespace", "replicas"],
        },
    ),

    # Service tools
    Tool(
        name="get_services",
        description="List all services in namespace or cluster-wide",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list from (omit for all namespaces)",
                },
            },
        },
    ),

    # Node tools
    Tool(
        name="get_nodes",
        description="List all nodes in the cluster with status and resource information",
        inputSchema={"type": "object", "properties": {}},
    ),

    # Cluster tools
    Tool(
        name="get_cluster_info",
        description="Get cluster version and summary information",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_namespaces",
        description="List all namespaces in the cluster",
        inputSchema={"type": "object", "properties": {}},
    ),

    # Resource management tools
    Tool(
        name="apply_manifest",
        description="Apply a YAML manifest to create or update resources",
        inputSchema={
            "type": "object",
            "properties": {
                "manifest_yaml": {
                    "type": "string",
                    "description": "YAML manifest content",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to apply to (optional, uses manifest namespace if omitted)",
                },
            },
            "required": ["manifest_yaml"],
        },
    ),
    Tool(
        name="delete_resource",
        description="Delete a resource (Pod, Deployment, or Service)",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Resource kind (Pod, Deployment, Service)",
                    "enum": ["Pod", "Deployment", "Service"],
                },
                "name": {"type": "string", "description": "Resource name"},
                "namespace": {"type": "string", "description": "Namespace"},
            },
            "required": ["kind", "name", "namespace"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """
    Handle tool execution requests from MCP client.

    Args:
        name: Tool name to execute
        arguments: Tool arguments

    Returns:
        List of TextContent with JSON response or error
    """
    try:
        result = None

        # Pod operations
        if name == "get_pods":
            result = await k3s_client.get_pods(
                namespace=arguments.get("namespace"),
                label_selector=arguments.get("labels"),
            )

        elif name == "get_logs":
            logs = await k3s_client.get_pod_logs(
                pod_name=arguments["pod_name"],
                namespace=arguments["namespace"],
                container=arguments.get("container"),
                tail_lines=arguments.get("tail_lines", 100),
            )
            return [TextContent(type="text", text=logs)]

        elif name == "execute_command":
            output = await k3s_client.execute_command(
                pod_name=arguments["pod_name"],
                namespace=arguments["namespace"],
                command=arguments["command"],
                container=arguments.get("container"),
            )
            return [TextContent(type="text", text=output)]

        elif name == "restart_pod":
            result = await k3s_client.delete_pod(
                pod_name=arguments["pod_name"],
                namespace=arguments["namespace"],
            )

        # Deployment operations
        elif name == "get_deployments":
            result = await k3s_client.get_deployments(
                namespace=arguments.get("namespace")
            )

        elif name == "get_deployment":
            result = await k3s_client.get_deployment(
                name=arguments["name"],
                namespace=arguments["namespace"],
            )

        elif name == "scale_deployment":
            result = await k3s_client.scale_deployment(
                name=arguments["name"],
                namespace=arguments["namespace"],
                replicas=arguments["replicas"],
            )

        # Service operations
        elif name == "get_services":
            result = await k3s_client.get_services(
                namespace=arguments.get("namespace")
            )

        # Node operations
        elif name == "get_nodes":
            result = await k3s_client.get_nodes()

        # Cluster operations
        elif name == "get_cluster_info":
            result = await k3s_client.get_cluster_info()

        elif name == "get_namespaces":
            result = await k3s_client.get_namespaces()

        # Resource management
        elif name == "apply_manifest":
            result = await k3s_client.apply_manifest(
                manifest_yaml=arguments["manifest_yaml"],
                namespace=arguments.get("namespace"),
            )

        elif name == "delete_resource":
            result = await k3s_client.delete_resource(
                kind=arguments["kind"],
                name=arguments["name"],
                namespace=arguments["namespace"],
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        error_msg = f"Error executing {name}: {str(e)}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def main():
    """
    Main entry point for the K3s MCP server.

    Validates kubeconfig and starts the MCP server on stdio.
    """
    try:
        # Print startup information
        print("=" * 50, file=sys.stderr)
        print("K3s MCP Server v1.0.0", file=sys.stderr)
        print("=" * 50, file=sys.stderr)
        print(f"Kubeconfig: {KUBECONFIG_PATH}", file=sys.stderr)
        print(f"Default Namespace: {DEFAULT_NAMESPACE}", file=sys.stderr)
        print(f"Debug Mode: {'Enabled' if DEBUG else 'Disabled'}", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        # Test cluster connectivity
        try:
            cluster_info = await k3s_client.get_cluster_info()
            print(f"Connected to cluster v{cluster_info['version']['git_version']}", file=sys.stderr)
            print(f"Nodes: {cluster_info['node_count']}", file=sys.stderr)
            print(f"Namespaces: {cluster_info['namespace_count']}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not verify cluster connection: {e}", file=sys.stderr)

        print("=" * 50, file=sys.stderr)
        print(f"Server ready - {len(TOOLS)} tools available", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        # Run the MCP server
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
