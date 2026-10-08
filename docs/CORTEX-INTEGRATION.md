# Cortex Integration Guide

This guide explains how to integrate the K3s MCP Server with the Cortex automation system.

## Overview

The K3s MCP Server provides Claude with direct access to manage and monitor the Cortex K3s cluster, enabling autonomous operations and AI-powered cluster management.

## Cortex Cluster Details

- **Cluster Endpoint**: `https://10.88.145.180:6443`
- **Kubeconfig**: `~/.kube/k3s-cortex-config.yaml`
- **Primary Namespaces**:
  - `default` - Default namespace
  - `cortex` - Cortex automation system (if used)
  - `monitoring` - Monitoring stack (if deployed)

## Integration Architecture

```
┌─────────────────┐
│  Claude AI      │
│  (via MCP)      │
└────────┬────────┘
         │
         │ MCP Protocol
         ▼
┌─────────────────────┐
│  K3s MCP Server     │
│  (Python/uv)        │
└────────┬────────────┘
         │
         │ Kubernetes API
         ▼
┌──────────────────────┐
│  K3s Cluster         │
│  10.88.145.180:6443  │
│  ┌─────────────────┐ │
│  │ Cortex Masters  │ │
│  │ Cortex Workers  │ │
│  │ EUI Dashboard   │ │
│  └─────────────────┘ │
└──────────────────────┘
```

## Setup for Cortex

### 1. Verify Kubeconfig

Ensure you have the Cortex kubeconfig:

```bash
# Check if kubeconfig exists
ls -la ~/.kube/k3s-cortex-config.yaml

# Verify it's configured for the correct cluster
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml cluster-info

# Expected output:
# Kubernetes control plane is running at https://10.88.145.180:6443
```

### 2. Configure MCP Server

Edit Claude Desktop config:

```json
{
  "mcpServers": {
    "k3s-cortex": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yourusername/Projects/k3s-mcp-server",
        "run",
        "k3s-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/Users/yourusername/.kube/k3s-cortex-config.yaml",
        "K3S_DEFAULT_NAMESPACE": "default"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

Completely quit and restart Claude Desktop.

## Cortex-Specific Use Cases

### Master Management

**List all masters**:
```
Show me all pods with label app=cortex-master
```

**Check master status**:
```
What's the status of the development-master deployment?
Get logs from the coordinator-master pod
```

**Scale masters**:
```
Scale the development-master deployment to 2 replicas
```

### Worker Management

**List workers**:
```
Show me all cortex worker pods
List all deployments with cortex-worker label
```

**Monitor workers**:
```
Get logs from the feature-implementer worker
Execute 'ps aux' in the bug-fixer worker pod
```

### Dashboard Operations

**Check dashboard**:
```
What's the status of the eui-dashboard deployment?
Show me all services for the dashboard
```

**Scale dashboard**:
```
Scale eui-dashboard to 3 replicas for high availability
```

**Get dashboard logs**:
```
Show me the last 100 lines of logs from the eui-dashboard pod
```

### Monitoring

**Cluster health**:
```
Get cluster information
Show me all node statuses
List all namespaces and their resource usage
```

**Pod monitoring**:
```
Show me all pods that are not running
List pods with high restart counts
Get events for the cortex namespace
```

### Deployments

**Deploy new Cortex components**:
```
Apply this deployment manifest:
[paste YAML]
```

**Update deployments**:
```
Update the cortex-dashboard image to version 2.0
```

## Autonomous Cortex Operations

Claude can autonomously manage Cortex through natural language:

### Example: Auto-scaling

```
"Monitor the cortex-dashboard deployment and scale it up if CPU usage is high"

Claude will:
1. Check current deployment status
2. Review pod resource usage
3. Scale deployment if needed
4. Verify new pods are running
5. Report back with status
```

### Example: Health Check

```
"Check the health of all Cortex masters and restart any that are failing"

Claude will:
1. List all master pods
2. Check status of each
3. Get logs from failing pods
4. Restart failing pods
5. Verify recovery
6. Report summary
```

### Example: Log Analysis

```
"Check the development-master logs for errors and summarize any issues"

Claude will:
1. Get recent logs
2. Analyze for error patterns
3. Summarize issues found
4. Suggest remediation steps
```

## Integration with Cortex Dashboard

The K3s MCP Server complements the Cortex EUI Dashboard:

- **Dashboard**: Real-time UI monitoring
- **MCP Server**: AI-powered automation and management

Together they provide:
- Visual monitoring (Dashboard)
- Autonomous operations (Claude + MCP)
- Event correlation across both systems

## Best Practices

### 1. Use Specific Namespaces

For Cortex operations, specify namespaces explicitly:

```
Show me all pods in the cortex namespace
List deployments in default namespace
```

### 2. Label-Based Selection

Use labels to filter Cortex resources:

```
Get pods with label app=cortex,tier=master
Show deployments with label managed-by=cortex
```

### 3. Safe Operations

Always verify before destructive operations:

```
# Good
"Show me the status of pod X before restarting it"

# Be cautious with
"Delete all pods in namespace"
```

### 4. Monitoring Integration

Correlate K3s data with Dashboard events:

```
"Check if the pod restart at 14:30 corresponds to a deployment update"
```

## Security Considerations

### RBAC Permissions

The kubeconfig should have appropriate RBAC permissions:

```yaml
# Example: Cortex operator role
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cortex-operator
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch", "create", "update", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

### Network Security

- K3s API is TLS-encrypted (6443/tcp)
- Kubeconfig contains certificates for authentication
- Keep kubeconfig secure: `chmod 600 ~/.kube/k3s-cortex-config.yaml`

### Audit Logging

All K3s API operations are logged by the cluster. Review logs:

```bash
ssh user@10.88.145.180
sudo journalctl -u k3s -f
```

## Troubleshooting

### Connection Issues

```bash
# Test network connectivity
ping 10.88.145.180

# Test API endpoint
curl -k https://10.88.145.180:6443

# Test kubectl access
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes
```

### Permission Issues

```bash
# Check permissions
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml auth can-i get pods
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml auth can-i scale deployments
```

### Debug Mode

Enable debug logging to see detailed operations:

```json
{
  "mcpServers": {
    "k3s-cortex": {
      "env": {
        "KUBECONFIG": "/path/to/config",
        "K3S_DEBUG": "true"
      }
    }
  }
}
```

## Example Cortex Workflows

### 1. Daily Health Check

```
Claude, please:
1. Check cluster health
2. List all Cortex pods and their status
3. Check for any pods with high restart counts
4. Review logs from any failing components
5. Summarize the cluster health
```

### 2. Deployment Update

```
Claude, please:
1. Show me the current version of cortex-dashboard
2. Scale it to 0 replicas
3. Apply the new deployment manifest
4. Scale back to 2 replicas
5. Verify all pods are running
6. Check logs for errors
```

### 3. Performance Investigation

```
Claude, please:
1. List all pods sorted by restart count
2. Get logs from the top 3 restarting pods
3. Analyze logs for error patterns
4. Suggest fixes based on the errors found
```

### 4. Master Coordination Check

```
Claude, please:
1. List all Cortex masters
2. Check their handoff directories for pending tasks
3. Review recent logs from coordinator-master
4. Summarize current task distribution
```

## Metrics and Monitoring

While the MCP server provides operational control, combine with:

- **Prometheus**: Time-series metrics
- **Grafana**: Visualization
- **Cortex Dashboard**: Real-time events

Ask Claude to correlate data:

```
"Check if the CPU spike at 3pm correlates with increased pod restarts"
```

## Future Enhancements

Potential Cortex integrations:

1. **Automated Scaling**: Claude monitors metrics and auto-scales
2. **Self-Healing**: Automatic detection and remediation
3. **Capacity Planning**: Analyze trends and recommend resources
4. **Cost Optimization**: Identify over-provisioned resources
5. **Security Scanning**: Regular security audits
6. **Backup Automation**: Automated backup verification

## Support

For Cortex-specific integration issues:

1. Check Cortex documentation
2. Review K3s cluster logs
3. Enable debug mode in MCP server
4. Test kubectl access separately
5. Check RBAC permissions

## Resources

- [K3s Documentation](https://docs.k3s.io/)
- [Kubernetes API Reference](https://kubernetes.io/docs/reference/kubernetes-api/)
- [Cortex Repository](https://github.com/ry-ops/cortex)
- [MCP Protocol](https://modelcontextprotocol.io/)

---

**Ready to integrate?** → Follow the setup steps above and start managing Cortex with Claude!
