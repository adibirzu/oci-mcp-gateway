#!/usr/bin/env bash
# Deploy all MCP gateway components to OKE.
#
# Usage:
#   ./deploy/scripts/deploy.sh          # full deploy
#   ./deploy/scripts/deploy.sh backends # backends only
#   ./deploy/scripts/deploy.sh gateway  # gateway only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/../kubernetes" && pwd)"
COMPONENT="${1:-all}"

echo "=== OCI MCP Gateway — Deploy to OKE ==="
echo "Component: $COMPONENT"
echo ""

# Namespace (idempotent)
kubectl create ns oci-mcp --dry-run=client -o yaml | kubectl apply -f -

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "shared" ]]; then
  echo "--- Applying shared resources ---"
  kubectl apply -f "$K8S_DIR/shared/"
fi

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "backends" ]]; then
  echo "--- Deploying backends ---"
  for backend_dir in "$K8S_DIR"/backends/*/; do
    backend_name=$(basename "$backend_dir")
    echo "  Deploying $backend_name..."
    kubectl apply -f "$backend_dir"
  done

  echo "  Waiting for backends..."
  for backend_dir in "$K8S_DIR"/backends/*/; do
    backend_name=$(basename "$backend_dir")
    # Extract deployment name from the deployment.yaml
    deploy_name=$(grep -m1 'name:' "$backend_dir/deployment.yaml" | awk '{print $2}')
    kubectl rollout status -n oci-mcp "deployment/$deploy_name" --timeout=120s || true
  done
fi

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "gateway" ]]; then
  echo "--- Deploying gateway ---"
  kubectl apply -f "$K8S_DIR/gateway/"
  kubectl rollout status -n oci-mcp deployment/oci-mcp-gateway --timeout=120s
fi

echo ""
echo "--- Status ---"
kubectl get pods -n oci-mcp -o wide
echo ""
kubectl get svc -n oci-mcp

# Wait for LB IP if gateway was deployed
if [[ "$COMPONENT" == "all" || "$COMPONENT" == "gateway" ]]; then
  echo ""
  echo "Waiting for LoadBalancer IP..."
  for i in $(seq 1 20); do
    LB_IP=$(kubectl get svc oci-mcp-gateway -n oci-mcp -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
    if [[ -n "$LB_IP" ]]; then
      echo "Gateway LB IP: $LB_IP"
      echo ""
      echo "MCP endpoint: http://$LB_IP/mcp"
      echo "Health check: curl -s http://$LB_IP/health"
      break
    fi
    echo "  Waiting... ($i/20)"
    sleep 15
  done

  if [[ -z "${LB_IP:-}" ]]; then
    echo "WARNING: LoadBalancer IP not assigned after 5 minutes."
    echo "Check: kubectl get svc oci-mcp-gateway -n oci-mcp"
  fi
fi

echo ""
echo "=== Deploy complete ==="
