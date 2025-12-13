# K3s MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-latest-green.svg)](https://github.com/astral-sh/uv)
[![MCP](https://img.shields.io/badge/MCP-1.0-purple.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Model Context Protocol (MCP) server for managing Kubernetes (K3s) clusters. This server provides comprehensive tools for managing pods, deployments, services, nodes, and cluster resources through the MCP interface.

**Built with Python and `uv` for fast, reliable dependency management.**

## Features

### Pod Management
- List pods across namespaces with label selectors
- Get pod logs with tail and container selection
- Execute commands in pods
- Restart pods (delete and recreate)

### Deployment Management
- List and describe deployments
- Scale deployments up or down
- Get deployment status and replica counts

### Service Management
- List services and endpoints
- View service ports and selectors
- Check service types (ClusterIP, NodePort, LoadBalancer)

### Node Management
- List all cluster nodes
- Get node status and resources
- View node capacity and allocatable resources
- Check node conditions (Ready, MemoryPressure, etc.)

### Resource Management
- Apply YAML manifests
- Delete resources (pods, deployments, services)
- List namespaces
- Get cluster information

## Quick Start

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone or create project directory
cd ~/Projects/k3s-mcp-server

# 3. Run setup script
chmod +x setup.sh
./setup.sh

# 4. Set environment variables
export KUBECONFIG="/Users/yourusername/.kube/k3s-cortex-config.yaml"

# 5. Test the server
uv run k3s-mcp-server

# 6. Configure Claude Desktop and restart
```

See [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

## Installation

### Prerequisites

- Python 3.10 or higher
- `uv` package manager
- K3s cluster with kubeconfig access
- Kubeconfig file (default: `~/.kube/k3s-cortex-config.yaml`)

### Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone or download this repository
cd k3s-mcp-server

# Run setup script (creates structure and installs dependencies)
./setup.sh

# Or manually:
mkdir -p src/k3s_mcp_server
# Place server.py and __init__.py in src/k3s_mcp_server/
uv sync
```

## Configuration

The server is configured via environment variables:

### Required Variables

- `KUBECONFIG`: Path to kubeconfig file (default: `~/.kube/k3s-cortex-config.yaml`)

### Optional Variables

- `K3S_DEFAULT_NAMESPACE`: Default namespace for operations (default: `default`)
- `K3S_DEBUG`: Enable debug logging (default: `false`)

## Setting Up K3s Access

### Using Existing Kubeconfig

If you already have a kubeconfig file from your K3s cluster:

```bash
# Set the path to your kubeconfig
export KUBECONFIG="/path/to/your/kubeconfig.yaml"
```

### Getting Kubeconfig from K3s Server

On your K3s server, the kubeconfig is located at:

```bash
# SSH to K3s server
ssh user@k3s-server

# Copy kubeconfig
sudo cat /etc/rancher/k3s/k3s.yaml

# Copy the content to your local machine:
# ~/.kube/k3s-cortex-config.yaml
```

**Important**: Update the `server` field in the kubeconfig to point to your K3s server IP/hostname instead of `127.0.0.1`.

### Verify Access

```bash
# Test kubectl access
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes

# Should show your K3s nodes
```

## MCP Configuration

Add to your Claude Desktop configuration file:

**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/k3s-mcp-server",
        "run",
        "k3s-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/Users/yourusername/.kube/k3s-cortex-config.yaml"
      }
    }
  }
}
```

**Important**: Use the absolute path to your project directory and kubeconfig file!

## Available Tools

### Pod Tools

- **get_pods**: List pods in namespace or cluster-wide
  - Parameters: `namespace` (optional), `labels` (optional selector)
- **get_logs**: Get pod logs
  - Parameters: `pod_name`, `namespace`, `container` (optional), `tail_lines` (default: 100)
- **restart_pod**: Restart a pod by deleting it
  - Parameters: `name`, `namespace`
- **execute_command**: Execute command in pod
  - Parameters: `pod_name`, `namespace`, `command` (array), `container` (optional)

### Deployment Tools

- **get_deployments**: List all deployments
  - Parameters: `namespace` (optional)
- **get_deployment**: Get specific deployment details
  - Parameters: `name`, `namespace`
- **scale_deployment**: Scale deployment replicas
  - Parameters: `name`, `namespace`, `replicas`

### Service Tools

- **get_services**: List all services
  - Parameters: `namespace` (optional)

### Node Tools

- **get_nodes**: List all nodes with resource information

### Cluster Tools

- **get_cluster_info**: Get cluster version and summary
- **get_namespaces**: List all namespaces

### Resource Management Tools

- **apply_manifest**: Apply YAML manifest
  - Parameters: `manifest_yaml`, `namespace` (optional)
- **delete_resource**: Delete a resource
  - Parameters: `kind` (Pod/Deployment/Service), `name`, `namespace`

## Example Usage

Once configured, you can ask Claude to interact with your K3s cluster:

> "Can you list all pods in my K3s cluster?"

> "What's the status of the cortex-dashboard deployment?"

> "Scale the eui-dashboard deployment to 3 replicas"

> "Show me the logs from the latest cortex pod"

> "Which nodes are in my cluster and what's their status?"

> "List all services in the default namespace"

> "Execute 'df -h' in the cortex pod to check disk space"

> "Apply this deployment manifest: [YAML content]"

## Development

```bash
# Install dependencies
uv sync

# Run the server directly
uv run k3s-mcp-server

# Run with custom environment
KUBECONFIG=/path/to/config.yaml \
K3S_DEFAULT_NAMESPACE=cortex \
K3S_DEBUG=true \
uv run k3s-mcp-server

# Install development dependencies
uv sync --all-extras

# Run tests (if implemented)
uv run pytest
```

## Project Structure

```
k3s-mcp-server/
├── src/
│   └── k3s_mcp_server/
│       ├── __init__.py       # Package initialization
│       └── server.py         # Main server implementation
├── pyproject.toml            # Project configuration
├── uv.lock                   # Locked dependencies (generated)
├── .env.example              # Environment variable template
├── .gitignore                # Git ignore patterns
├── setup.sh                  # Automated setup script
├── README.md                 # This file
└── QUICKSTART.md            # 5-minute setup guide
```

## Security Considerations

- **Kubeconfig Security**: Keep your kubeconfig file secure and never commit it to version control
- **RBAC**: Ensure the kubeconfig user has appropriate RBAC permissions
- **Network Access**: Ensure network connectivity to the K3s API server
- **Credentials**: Store kubeconfig securely, preferably with restricted file permissions (chmod 600)
- **Audit**: K8s API server logs all actions, useful for auditing

## Troubleshooting

### Connection Errors

- Verify `KUBECONFIG` path is correct and file exists
- Check network connectivity to K3s server
- Ensure kubeconfig `server` field points to correct IP/hostname
- Test with: `kubectl --kubeconfig /path/to/config get nodes`

### Authentication Errors

- Verify kubeconfig contains valid credentials
- Check if certificates are valid and not expired
- Ensure user/service account has appropriate RBAC permissions

### Permission Errors

- The kubeconfig user needs appropriate RBAC permissions
- Common required permissions: pods/get, pods/list, deployments/get, deployments/scale, etc.
- Check with: `kubectl --kubeconfig /path/to/config auth can-i get pods`

### Tools Not Showing in Claude

- Verify the path in Claude config is absolute, not relative
- Check that the config file is valid JSON
- Ensure you completely quit and restarted Claude Desktop
- Check Claude Desktop logs for errors
- Verify `KUBECONFIG` path in env section

### Debug Mode

Enable debug logging:

```bash
export K3S_DEBUG=true
uv run k3s-mcp-server
```

Check stderr output for detailed connection and operation logs.

## Integration with Cortex

This K3s MCP server is designed to work with the Cortex automation system:

1. **Cluster**: Cortex K3s cluster at `10.88.145.180:6443`
2. **Kubeconfig**: `~/.kube/k3s-cortex-config.yaml`
3. **Namespaces**: `default`, `cortex`, `monitoring`, etc.
4. **Deployments**: cortex-dashboard, eui-dashboard, masters, workers

### Example Cortex Operations

```
"Show me all cortex pods"
"Scale the cortex-dashboard deployment to 2 replicas"
"Get logs from the development-master pod"
"What's the status of all nodes in the cortex cluster?"
"List all services in the monitoring namespace"
```

## API Documentation

For more information about the Kubernetes API:
- [Kubernetes API Reference](https://kubernetes.io/docs/reference/kubernetes-api/)
- [K3s Documentation](https://docs.k3s.io/)
- [Python Kubernetes Client](https://github.com/kubernetes-client/python)

## Dependencies

- **mcp** (>=1.0.0): Model Context Protocol SDK
- **kubernetes** (>=29.0.0): Official Python client for Kubernetes
- **pyyaml** (>=6.0): YAML parser for manifest handling

## Roadmap

Future enhancements may include:

- ConfigMap and Secret management
- PersistentVolume and PVC operations
- Ingress management
- Job and CronJob support
- StatefulSet operations
- DaemonSet management
- HorizontalPodAutoscaler (HPA) configuration
- Resource quota and limit management
- Event streaming and monitoring
- Helm chart deployment support

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

Areas for improvement:
- Additional resource types
- Better error handling
- Performance optimizations
- Documentation improvements
- Test coverage
- Bug fixes

## License

MIT

## Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Kubernetes](https://kubernetes.io/)
- [K3s - Lightweight Kubernetes](https://k3s.io/)
- [uv - Python Package Manager](https://github.com/astral-sh/uv)
- [MCP Servers Collection](https://github.com/modelcontextprotocol/servers)

## Support

If you encounter issues:

1. Check the documentation:
   - [QUICKSTART.md](QUICKSTART.md) - Quick setup
   - [README.md](README.md) - Full documentation

2. Test kubectl access directly:
   ```bash
   kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes
   ```

3. Check Claude Desktop logs for errors

4. Enable debug mode: `export K3S_DEBUG=true`

5. Review Kubernetes API server logs

## Acknowledgments

This project uses:
- The Model Context Protocol by Anthropic
- Kubernetes Python Client
- K3s lightweight Kubernetes
- uv for fast Python package management

---

**Ready to get started?** → See [QUICKSTART.md](QUICKSTART.md)

**Need help?** → Check the Troubleshooting section above
