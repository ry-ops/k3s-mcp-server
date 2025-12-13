# K3s MCP Server - Installation Checklist

Use this checklist to verify your installation is complete and ready.

## Pre-Installation

- [ ] Python 3.10+ installed: `python3 --version`
- [ ] uv package manager installed: `uv --version`
- [ ] K3s cluster accessible
- [ ] Kubeconfig available at `~/.kube/k3s-cortex-config.yaml`

## Installation Steps

- [ ] Clone/download project to `~/Projects/k3s-mcp-server`
- [ ] Run setup script: `./setup.sh`
- [ ] Verify dependencies installed: `uv sync` completes successfully
- [ ] Test package import: `uv run python -c "import k3s_mcp_server; print(k3s_mcp_server.__version__)"`

## Kubeconfig Setup

- [ ] Kubeconfig file exists: `ls -la ~/.kube/k3s-cortex-config.yaml`
- [ ] File permissions correct: `chmod 600 ~/.kube/k3s-cortex-config.yaml`
- [ ] Server address is external (not 127.0.0.1): `grep server ~/.kube/k3s-cortex-config.yaml`
- [ ] kubectl works: `kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml get nodes`

## Claude Desktop Configuration

- [ ] Locate Claude config file:
  - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
  - Windows: `%APPDATA%/Claude/claude_desktop_config.json`
- [ ] Edit configuration file
- [ ] Add k3s-mcp-server configuration (see claude-config-example.json)
- [ ] Verify JSON is valid: `python3 -m json.tool claude_desktop_config.json`
- [ ] Use absolute paths (not `~` or relative)
- [ ] Save configuration file

## Testing

- [ ] Quit Claude Desktop completely (Cmd+Q on macOS)
- [ ] Restart Claude Desktop
- [ ] Start new conversation
- [ ] Verify K3s tools appear in MCP tools list
- [ ] Test basic command: "List all nodes in my K3s cluster"
- [ ] Test pod listing: "Show me all pods"
- [ ] Test deployment query: "List all deployments"

## Verification

- [ ] All 13 K3s tools available in Claude
- [ ] No errors in Claude Desktop logs
- [ ] Server responds to queries
- [ ] Can list cluster resources
- [ ] Can view pod logs
- [ ] Can scale deployments

## Troubleshooting (if needed)

- [ ] Check Claude Desktop logs for errors
- [ ] Enable debug mode: `"K3S_DEBUG": "true"` in config
- [ ] Test connection manually: `./test-connection.sh`
- [ ] Verify kubeconfig: `kubectl --kubeconfig ~/.kube/k3s-cortex-config.yaml cluster-info`
- [ ] Review troubleshooting section in README.md

## Post-Installation

- [ ] Review CORTEX-INTEGRATION.md for Cortex-specific use cases
- [ ] Test Cortex-specific queries
- [ ] Set up monitoring/alerting as needed
- [ ] Document any custom configurations

## Success Criteria

✅ All checklist items completed
✅ Claude can list K3s resources
✅ No errors in logs
✅ Autonomous operations working

---

**Installation Date**: _______________
**Installed By**: _______________
**Cluster**: 10.88.145.180:6443
**Namespace**: default

**Status**: ⬜ Not Started | ⬜ In Progress | ⬜ Complete | ⬜ Issues

**Notes**:
_______________________________________________
_______________________________________________
_______________________________________________
