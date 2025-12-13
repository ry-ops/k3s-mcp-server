"""
K3s MCP Server
==============

A Model Context Protocol (MCP) server for managing Kubernetes (K3s) clusters.

This package provides comprehensive tools for interacting with K3s/Kubernetes through
Claude AI, enabling natural language management of pods, deployments, services,
nodes, and cluster resources.

Features:
---------
- Pod management (list, logs, exec, restart)
- Deployment operations (list, describe, scale)
- Service management (list, describe)
- Node monitoring (list, status, resources)
- Resource operations (apply manifests, delete resources)
- Namespace management
- Cluster information and status

Requirements:
-------------
- Python 3.10+
- K3s/Kubernetes cluster with API access
- Valid kubeconfig file

Usage:
------
Configure via environment variables:
    - KUBECONFIG: Path to kubeconfig file (default: ~/.kube/k3s-cortex-config.yaml)
    - K3S_DEFAULT_NAMESPACE: Default namespace (default: default)
    - K3S_DEBUG: Enable debug logging (default: false)

Example:
    export KUBECONFIG="/Users/username/.kube/k3s-cortex-config.yaml"
    uv run k3s-mcp-server

Links:
------
- GitHub: https://github.com/ry-ops/k3s-mcp-server
- Documentation: https://github.com/ry-ops/k3s-mcp-server#readme
- MCP Protocol: https://modelcontextprotocol.io/
- Kubernetes API: https://kubernetes.io/docs/reference/kubernetes-api/

License:
--------
MIT License - see LICENSE file for details

Author:
-------
ry-ops

"""

__version__ = "1.0.0"
__author__ = "ry-ops"
__license__ = "MIT"
__url__ = "https://github.com/ry-ops/k3s-mcp-server"

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "__url__",
]
