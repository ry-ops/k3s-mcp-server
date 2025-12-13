# Claude Desktop Configuration Guide

This guide shows you how to configure Claude Desktop to use the K3s MCP Server.

## Configuration File Location

### macOS
```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

### Windows
```bash
%APPDATA%/Claude/claude_desktop_config.json
```

### Linux
```bash
~/.config/Claude/claude_desktop_config.json
```

## Basic Configuration

Add this to your `claude_desktop_config.json`:

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

**Important**: Replace `/Users/yourusername` with your actual username!

## Configuration with Multiple MCP Servers

If you already have other MCP servers configured:

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yourusername/Projects/proxmox-mcp-server",
        "run",
        "proxmox-mcp-server"
      ],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "automation",
        "PROXMOX_TOKEN_VALUE": "your-token-here"
      }
    },
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

## Configuration with Custom Namespace

Set a default namespace for operations:

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
        "KUBECONFIG": "/Users/yourusername/.kube/k3s-cortex-config.yaml",
        "K3S_DEFAULT_NAMESPACE": "cortex"
      }
    }
  }
}
```

## Configuration with Debug Logging

Enable debug mode to see detailed logs:

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
        "KUBECONFIG": "/Users/yourusername/.kube/k3s-cortex-config.yaml",
        "K3S_DEBUG": "true"
      }
    }
  }
}
```

## Step-by-Step Setup

### 1. Find Your Absolute Path

```bash
# Get full path to k3s-mcp-server
cd ~/Projects/k3s-mcp-server
pwd
# Copy this path

# Get full path to kubeconfig
ls -la ~/.kube/k3s-cortex-config.yaml
# Verify it exists
```

### 2. Edit Claude Config

**macOS**:
```bash
# Open in default editor
open ~/Library/Application\ Support/Claude/

# Or edit directly with VS Code
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Windows**:
```powershell
# Open in Explorer
explorer %APPDATA%\Claude

# Or edit with notepad
notepad %APPDATA%\Claude\claude_desktop_config.json
```

### 3. Add Configuration

Copy the configuration template above and:
1. Replace `/Users/yourusername` with your actual path from step 1
2. Verify the kubeconfig path is correct
3. Save the file

### 4. Validate JSON

Before restarting Claude, validate your JSON:

```bash
# macOS/Linux - use python to validate
python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Or use an online JSON validator: https://jsonlint.com/

### 5. Restart Claude Desktop

**macOS**:
- Quit Claude completely with `Cmd+Q` (not just close window)
- Reopen Claude

**Windows**:
- Right-click Claude in system tray → Exit
- Reopen Claude

### 6. Verify Tools are Available

Open a new conversation in Claude and you should see the K3s tools available in the MCP tools section.

## Troubleshooting

### Issue: Tools Not Showing

**Solutions**:
1. Verify JSON is valid (no trailing commas, proper quotes)
2. Use absolute paths (not `~` or relative paths)
3. Completely quit Claude (check Activity Monitor/Task Manager)
4. Check Claude logs for errors

**macOS Logs**:
```bash
~/Library/Logs/Claude/
```

**Windows Logs**:
```
%APPDATA%\Claude\logs\
```

### Issue: Server Fails to Start

**Check**:
1. Kubeconfig path is correct: `ls -la /path/to/kubeconfig`
2. uv is installed: `which uv`
3. Project directory exists: `ls -la /path/to/k3s-mcp-server`
4. Dependencies installed: `cd /path/to/k3s-mcp-server && uv sync`

**Test manually**:
```bash
cd ~/Projects/k3s-mcp-server
export KUBECONFIG="$HOME/.kube/k3s-cortex-config.yaml"
uv run k3s-mcp-server
```

### Issue: Connection to K3s Fails

**Check**:
1. K3s cluster is running
2. Network connectivity: `ping 10.88.145.180`
3. Kubeconfig server address is correct (not 127.0.0.1)
4. Test with kubectl: `kubectl --kubeconfig /path/to/config get nodes`

### Issue: Permission Errors

**Check**:
1. Kubeconfig file permissions: `chmod 600 ~/.kube/k3s-cortex-config.yaml`
2. RBAC permissions in K3s cluster
3. Test permissions: `kubectl --kubeconfig /path/to/config auth can-i get pods`

## Environment Variables Reference

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `KUBECONFIG` | Path to kubeconfig file | `~/.kube/k3s-cortex-config.yaml` | Yes |
| `K3S_DEFAULT_NAMESPACE` | Default namespace for operations | `default` | No |
| `K3S_DEBUG` | Enable debug logging | `false` | No |

## Example Configurations

### Minimal (Default Namespace)
```json
{
  "mcpServers": {
    "k3s": {
      "command": "uv",
      "args": ["--directory", "/Users/ryan/Projects/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": {
        "KUBECONFIG": "/Users/ryan/.kube/k3s-cortex-config.yaml"
      }
    }
  }
}
```

### Production (Cortex Namespace + Debug)
```json
{
  "mcpServers": {
    "k3s-cortex": {
      "command": "uv",
      "args": ["--directory", "/Users/ryan/Projects/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": {
        "KUBECONFIG": "/Users/ryan/.kube/k3s-cortex-config.yaml",
        "K3S_DEFAULT_NAMESPACE": "cortex",
        "K3S_DEBUG": "true"
      }
    }
  }
}
```

### Multiple Clusters
```json
{
  "mcpServers": {
    "k3s-prod": {
      "command": "uv",
      "args": ["--directory", "/Users/ryan/Projects/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": {
        "KUBECONFIG": "/Users/ryan/.kube/k3s-prod.yaml",
        "K3S_DEFAULT_NAMESPACE": "production"
      }
    },
    "k3s-staging": {
      "command": "uv",
      "args": ["--directory", "/Users/ryan/Projects/k3s-mcp-server", "run", "k3s-mcp-server"],
      "env": {
        "KUBECONFIG": "/Users/ryan/.kube/k3s-staging.yaml",
        "K3S_DEFAULT_NAMESPACE": "staging"
      }
    }
  }
}
```

## Testing the Configuration

After configuring Claude Desktop:

1. **Start a new conversation**
2. **Ask Claude**: "What MCP tools do you have available?"
3. **Look for K3s tools**: get_pods, get_deployments, get_nodes, etc.
4. **Test a simple command**: "List all nodes in my K3s cluster"

## Getting Help

If you're still having issues:

1. Review [QUICKSTART.md](QUICKSTART.md)
2. Check [README.md](README.md) troubleshooting section
3. Test the server manually (see above)
4. Check Claude Desktop logs
5. Verify kubeconfig with kubectl

---

**Configuration working?** → Try asking Claude to manage your K3s cluster!

**Still having issues?** → Check the troubleshooting section above.
