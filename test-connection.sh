#!/bin/bash
set -e

echo "=================================================="
echo "K3s MCP Server Connection Test"
echo "=================================================="
echo ""

# Check for kubeconfig
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/k3s-cortex-config.yaml}"

if [ ! -f "$KUBECONFIG_PATH" ]; then
    echo "Error: Kubeconfig not found at $KUBECONFIG_PATH"
    echo ""
    echo "Please set KUBECONFIG environment variable or place kubeconfig at:"
    echo "  $HOME/.kube/k3s-cortex-config.yaml"
    exit 1
fi

echo "✓ Found kubeconfig at $KUBECONFIG_PATH"
echo ""

# Test kubectl access
echo "Testing kubectl access..."
echo ""

if command -v kubectl &> /dev/null; then
    echo "Running: kubectl --kubeconfig $KUBECONFIG_PATH cluster-info"
    echo ""
    kubectl --kubeconfig "$KUBECONFIG_PATH" cluster-info || {
        echo ""
        echo "Error: Could not connect to cluster"
        echo "Please verify:"
        echo "  1. K3s cluster is running"
        echo "  2. Network connectivity to cluster"
        echo "  3. Kubeconfig has correct server address"
        exit 1
    }

    echo ""
    echo "Running: kubectl --kubeconfig $KUBECONFIG_PATH get nodes"
    echo ""
    kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes || {
        echo ""
        echo "Error: Could not list nodes"
        exit 1
    }

    echo ""
    echo "✓ kubectl access verified"
else
    echo "⚠ kubectl not found, skipping direct kubectl tests"
    echo "  Install kubectl to run additional verification"
fi

echo ""
echo "=================================================="
echo "Testing K3s MCP Server"
echo "=================================================="
echo ""

# Create test script
cat > /tmp/test_k3s_mcp.py <<'EOF'
#!/usr/bin/env python3
import os
import sys
import asyncio
from pathlib import Path

# Set kubeconfig
kubeconfig_path = os.getenv("KUBECONFIG", str(Path.home() / ".kube" / "k3s-cortex-config.yaml"))
os.environ["KUBECONFIG"] = kubeconfig_path

print(f"Using kubeconfig: {kubeconfig_path}")
print("")

try:
    from k3s_mcp_server.server import k3s_client

    async def test():
        print("Testing cluster connectivity...")

        # Test cluster info
        try:
            info = await k3s_client.get_cluster_info()
            print(f"✓ Connected to cluster")
            print(f"  Version: {info['version']['git_version']}")
            print(f"  Nodes: {info['node_count']}")
            print(f"  Namespaces: {info['namespace_count']}")
            print("")
        except Exception as e:
            print(f"✗ Failed to get cluster info: {e}")
            return False

        # Test listing nodes
        try:
            nodes = await k3s_client.get_nodes()
            print(f"✓ Listed {nodes['count']} nodes")
            for node in nodes['nodes']:
                print(f"  - {node['name']}: {node['status']}")
            print("")
        except Exception as e:
            print(f"✗ Failed to list nodes: {e}")
            return False

        # Test listing namespaces
        try:
            namespaces = await k3s_client.get_namespaces()
            print(f"✓ Listed {namespaces['count']} namespaces")
            print("")
        except Exception as e:
            print(f"✗ Failed to list namespaces: {e}")
            return False

        # Test listing pods
        try:
            pods = await k3s_client.get_pods()
            print(f"✓ Listed {pods['count']} pods across all namespaces")
            print("")
        except Exception as e:
            print(f"✗ Failed to list pods: {e}")
            return False

        return True

    result = asyncio.run(test())

    if result:
        print("=" * 50)
        print("✓ All tests passed!")
        print("=" * 50)
        print("")
        print("The K3s MCP server is ready to use.")
        print("")
        print("Configure Claude Desktop with:")
        print('  "KUBECONFIG": "' + kubeconfig_path + '"')
        print("")
        sys.exit(0)
    else:
        print("=" * 50)
        print("✗ Some tests failed")
        print("=" * 50)
        sys.exit(1)

except ImportError as e:
    print(f"Error importing k3s_mcp_server: {e}")
    print("")
    print("Make sure you've run: uv sync")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF

# Run test
export KUBECONFIG="$KUBECONFIG_PATH"
uv run python /tmp/test_k3s_mcp.py

# Cleanup
rm /tmp/test_k3s_mcp.py
