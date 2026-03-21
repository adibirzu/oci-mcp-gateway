#!/usr/bin/env bash
# Build all MCP server images on the control-plane VM and push to OCIR.
# ARM Macs must NOT build x86_64 images locally — always use the remote VM.
#
# Usage:
#   ./deploy/scripts/build-all.sh              # build all
#   ./deploy/scripts/build-all.sh logan        # build only logan
#   ./deploy/scripts/build-all.sh gateway oci  # build gateway and oci

set -euo pipefail

OCIR="eu-frankfurt-1.ocir.io/${OCIR_TENANCY}"
TAG=$(date +%Y%m%d%H%M%S)
BUILD_VM="${BUILD_VM:-control-plane-oci}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MCP_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"

# Image name → local source directory + Dockerfile
declare -A SOURCES=(
  [oci-mcp-gateway]="$PROJECT_ROOT"
  [oci-logan]="$MCP_ROOT/../mcp-oci-logan-server"
  [mcp-oci]="$MCP_ROOT/mcp-oci"
  [oci-mcp-security]="$MCP_ROOT/oci-mcp-security"
  [finopsai-mcp]="$MCP_ROOT/finopsai-mcp"
  [db-observatory]="$MCP_ROOT/mcp-oci-database-observatory"
)

# Dockerfiles: use project's own if it has one, otherwise use our dockerfiles/
declare -A DOCKERFILES=(
  [oci-mcp-gateway]="Dockerfile"
  [oci-logan]="$PROJECT_ROOT/dockerfiles/Dockerfile.logan"
  [mcp-oci]="$PROJECT_ROOT/dockerfiles/Dockerfile.mcp-oci"
  [oci-mcp-security]="Dockerfile"
  [finopsai-mcp]="$PROJECT_ROOT/dockerfiles/Dockerfile.finops"
  [db-observatory]="$PROJECT_ROOT/dockerfiles/Dockerfile.db-observatory"
)

# Filter to requested images (or all if no args)
if [[ $# -gt 0 ]]; then
  TARGETS=("$@")
else
  TARGETS=("${!SOURCES[@]}")
fi

echo "=== OCI MCP Gateway — Build & Push ==="
echo "OCIR:     $OCIR"
echo "Tag:      $TAG"
echo "Build VM: $BUILD_VM"
echo "Targets:  ${TARGETS[*]}"
echo ""

for name in "${TARGETS[@]}"; do
  src="${SOURCES[$name]:-}"
  if [[ -z "$src" ]]; then
    echo "ERROR: Unknown image '$name'. Valid: ${!SOURCES[*]}"
    exit 1
  fi

  if [[ ! -d "$src" ]]; then
    echo "SKIP: $name — source dir not found: $src"
    continue
  fi

  dockerfile="${DOCKERFILES[$name]}"
  # If dockerfile is an absolute path (our dockerfiles/), copy it into the build context
  docker_flag=""
  if [[ "$dockerfile" == "$PROJECT_ROOT"/* && "$src" != "$PROJECT_ROOT" ]]; then
    docker_flag="-f /tmp/mcp/$name/Dockerfile.gateway"
  fi

  echo "--- Building $name ---"
  echo "  Source:     $src"
  echo "  Dockerfile: $dockerfile"

  # Sync source to build VM
  rsync -avz --delete \
    --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
    --exclude 'node_modules' --exclude '.env' --exclude '.env.*' \
    "$src/" "$BUILD_VM:/tmp/mcp/$name/"

  # If using our Dockerfile, copy it to the build context
  if [[ -n "$docker_flag" ]]; then
    scp "$dockerfile" "$BUILD_VM:/tmp/mcp/$name/Dockerfile.gateway"
    dockerfile="Dockerfile.gateway"
  fi

  # Build and push on the VM
  ssh "$BUILD_VM" bash -c "'
    cd /tmp/mcp/$name
    docker build -f $dockerfile \
      -t $OCIR/$name:$TAG \
      -t $OCIR/$name:latest \
      . && \
    docker push $OCIR/$name:$TAG && \
    docker push $OCIR/$name:latest
  '"

  echo "  Pushed: $OCIR/$name:$TAG"
  echo ""
done

echo "=== All builds complete. Tag: $TAG ==="
