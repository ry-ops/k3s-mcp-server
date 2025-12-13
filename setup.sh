#!/bin/bash
set -e

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

# Create directory structure
echo ""
echo "Creating project structure..."

mkdir -p k3s_mcp_server
echo "✓ Created k3s_mcp_server directory"

# Check if files exist
if [ ! -f "k3s_mcp_server/__init__.py" ]; then
    echo "Error: k3s_mcp_server/__init__.py not found"
    echo "Please ensure the package files are in place"
    exit 1
fi

if [ ! -f "k3s_mcp_server/server.py" ]; then
    echo "Error: k3s_mcp_server/server.py not found"
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

KUBECONFIG_DEFAULT="$HOME/.kube/k3s-cortex-config.yaml"

if [ -f "$KUBECONFIG_DEFAULT" ]; then
    echo "✓ Found kubeconfig at $KUBECONFIG_DEFAULT"
else
    echo "⚠ Kubeconfig not found at $KUBECONFIG_DEFAULT"
    echo ""
    echo "Please ensure your kubeconfig is at one of these locations:"
    echo "  - $HOME/.kube/k3s-cortex-config.yaml (default)"
    echo "  - $HOME/.kube/config"
    echo ""
    echo "Or set the KUBECONFIG environment variable to your kubeconfig path"
fi

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Ensure your kubeconfig is available:"
echo "   export KUBECONFIG=\"$HOME/.kube/k3s-cortex-config.yaml\""
echo ""
echo "2. Test the server:"
echo "   ./test-connection.sh"
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
echo '           "KUBECONFIG": "'$HOME'/.kube/k3s-cortex-config.yaml"'
echo '         }'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "4. Restart Claude Desktop completely"
echo ""
echo "=================================================="
