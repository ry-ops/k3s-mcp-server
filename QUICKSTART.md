# Quick Start Guide

Get up and running with the K3s MCP Server in 5 minutes!

## 1. Install Dependencies

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to project directory
cd ~/Projects/k3s-mcp-server

# Install project dependencies
uv sync
```

## 2. Get Kubeconfig from K3s Server

### Option A: Copy from K3s Server

```bash
# SSH to your K3s server
ssh user@10.88.145.180

# View kubeconfig
sudo cat /etc/rancher/k3s/k3s.yaml

# Copy the output to your local machine
```

### Option B: Use Existing Kubeconfig

If you already have a kubeconfig file:

```bash
# Copy to standard location
cp /path/to/your/k3s-config.yaml ~/.kube/k3s-cortex-config.yaml

# Or set KUBECONFIG to point to it
export KUBECONFIG="/path/to/your/k3s-config.yaml"
```

### Update Server Address

Edit `~/.kube/k3s-cortex-config.yaml` and update the server address:

```yaml
apiVersion: v1
clusters:
- cluster:
    server: https://10.88.145.180:6443  # Change from https://127.0.0.1:6443
    # ... rest of config
```

## 3. Verify kubectl Access

```bash
# Test connection to K3s cluster
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes

# Should show your K3s nodes like:
# NAME     STATUS   ROLES                  AGE   VERSION
# k3s-01   Ready    control-plane,master   30d   v1.28.5+k3s1
```

## 4. Test the MCP Server

```bash
# Set kubeconfig path
export KUBECONFIG="/Users/yourusername/.kube/k3s-cortex-config.yaml"

# Run the server
uv run k3s-mcp-server
```

You should see:
```
Starting K3s MCP Server...
Using kubeconfig: /Users/yourusername/.kube/k3s-cortex-config.yaml
Default namespace: default
Loaded kubeconfig from: /Users/yourusername/.kube/k3s-cortex-config.yaml
```

Press `Ctrl+C` to stop.

## 5. Configure Claude Desktop

Edit config file:
- **MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

Add this configuration (replace paths with yours):

```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yourusername/Projects/k3s-mcp-server",
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

**Important**:
- Use absolute paths (not `~` or relative paths)
- Replace `yourusername` with your actual username
- Ensure the kubeconfig path is correct

## 6. Restart Claude Desktop

Completely quit and restart Claude Desktop (don't just close the window).

**MacOS**: Quit Claude completely with `Cmd+Q`

## 7. Test It!

Open a new conversation in Claude and try:

```
List all pods in my K3s cluster
```

```
Show me all deployments
```

```
What's the status of all nodes?
```

```
Get cluster information
```

That's it! 🎉

## Common Issues

### "Kubeconfig not found"

**Fix:**
- Verify the path in your env variable is correct
- Use absolute path (not `~`)
- Check file exists: `ls -la /Users/yourusername/.kube/k3s-cortex-config.yaml`

### "Connection refused"

**Fix:**
- Check network connectivity: `ping 10.88.145.180`
- Verify server address in kubeconfig is correct (not 127.0.0.1)
- Ensure K3s is running: `ssh user@10.88.145.180 "sudo systemctl status k3s"`

### "Authentication failed"

**Fix:**
- Verify kubeconfig credentials are valid
- Check certificates haven't expired
- Test with kubectl: `kubectl --kubeconfig /path/to/config get nodes`

### "Tools not showing in Claude"

**Fix:**
1. Validate JSON config (use a JSON validator)
2. Use absolute paths (not `~` or relative)
3. Completely quit Claude (Cmd+Q on Mac)
4. Check Claude Desktop logs:
   - **MacOS**: `~/Library/Logs/Claude/`
   - **Windows**: `%APPDATA%/Claude/logs/`

### "Permission denied"

**Fix:**
- Check RBAC permissions in K3s
- Test permissions: `kubectl --kubeconfig /path/to/config auth can-i get pods`
- May need to create service account with proper roles

## Example Queries for Claude

Once working, try these commands:

### Basic Information
```
"Show me cluster information"
"List all namespaces"
"What nodes are in my cluster?"
```

### Pods
```
"List all pods"
"Show me pods in the cortex namespace"
"Get logs from pod cortex-dashboard-xxxxx"
"Restart the failing pod in default namespace"
```

### Deployments
```
"List all deployments"
"What's the status of the eui-dashboard deployment?"
"Scale cortex-dashboard to 2 replicas"
```

### Services
```
"Show all services"
"What services are in the monitoring namespace?"
```

### Advanced
```
"Execute 'df -h' in pod cortex-dashboard-xxxxx to check disk usage"
"Show me the last 50 lines of logs from the development-master pod"
"Apply this manifest: [paste YAML]"
```

## Cortex-Specific Examples

For the Cortex automation system:

```
"Show me all cortex-related pods"
"What's the status of the development master?"
"List all deployments in the cortex namespace"
"Get logs from the latest coordinator-master pod"
"Scale the eui-dashboard to handle more traffic"
```

## Next Steps

- Read [README.md](README.md) for complete documentation
- Explore all available tools in Claude
- Set up custom namespaces and RBAC if needed
- Integrate with Cortex automation workflows

## Security Reminder

- Never commit kubeconfig to git
- Keep kubeconfig file permissions restricted: `chmod 600 ~/.kube/k3s-cortex-config.yaml`
- Consider using service accounts instead of admin credentials for production
- Audit K8s API access regularly

## Getting Help

If you're stuck:

1. **Verify kubectl works**: `kubectl --kubeconfig /path/to/config get nodes`
2. **Check server logs**: Enable debug mode with `K3S_DEBUG=true`
3. **Test MCP server**: Run `uv run k3s-mcp-server` manually
4. **Check Claude logs**: Look for errors in Claude Desktop logs
5. **Review README**: Check the troubleshooting section

## Quick Reference

### Environment Variables
```bash
export KUBECONFIG="/path/to/k3s-cortex-config.yaml"
export K3S_DEFAULT_NAMESPACE="default"  # Optional
export K3S_DEBUG="true"  # Optional
```

### Test Connection
```bash
# Test kubectl
kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes

# Test MCP server
KUBECONFIG=~/.kube/k3s-cortex-config.yaml uv run k3s-mcp-server
```

### Claude Config Path
```bash
# MacOS
open ~/Library/Application\ Support/Claude/

# Or edit directly
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Happy K3s management with Claude! 🚀
