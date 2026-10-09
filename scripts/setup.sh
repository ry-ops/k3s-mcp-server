#!/bin/bash
set -e

# Run from the repo root, wherever the script is called from
cd "$(dirname "$0")/.."

echo "=================================================="
echo "K3s MCP Server Setup"
echo "=================================================="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed"
    echo "Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✓ Found uv package manager"

# Check the package files are in place
if [ ! -f "src/k3s_mcp_server/__init__.py" ]; then
    echo "Error: src/k3s_mcp_server/__init__.py not found"
    echo "Please ensure the package files are in place"
    exit 1
fi

if [ ! -f "src/k3s_mcp_server/server.py" ]; then
    echo "Error: src/k3s_mcp_server/server.py not found"
    echo "Please ensure the package files are in place"
    exit 1
fi

echo "✓ Found package files"

# Install dependencies
echo ""
echo "Installing dependencies..."
uv sync

echo ""
echo "✓ Dependencies installed"

# Check for kubeconfig
echo ""
echo "Checking for kubeconfig..."

KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"

if [ -f "$KUBECONFIG_PATH" ]; then
    echo "✓ Found kubeconfig at $KUBECONFIG_PATH"
else
    echo "⚠ Kubeconfig not found at $KUBECONFIG_PATH"
    echo ""
    echo "Put your kubeconfig at $HOME/.kube/config, or set the KUBECONFIG"
    echo "environment variable to its path."
fi

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Ensure your kubeconfig is available:"
echo "   export KUBECONFIG=\"$KUBECONFIG_PATH\""
echo ""
echo "2. Test the server:"
echo "   bash scripts/test-connection.sh"
echo ""
echo "3. Configure Claude Desktop:"
echo "   Edit: ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "   Add this configuration:"
echo '   {'
echo '     "mcpServers": {'
echo '       "k3s": {'
echo '         "command": "uv",'
echo '         "args": ["--directory", "'$(pwd)'", "run", "k3s-mcp-server"],'
echo '         "env": {'
echo '           "KUBECONFIG": "'$KUBECONFIG_PATH'"'
echo '         }'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "4. Restart Claude Desktop completely"
echo ""
echo "=================================================="
