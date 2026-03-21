#!/usr/bin/env bash
# Create IDCS OAuth application for MCP gateway JWT authentication.
#
# Prerequisites:
#   - OCI CLI configured with admin privileges
#   - IDCS domain URL known
#
# This script creates the OAuth app and exports the JWKS public key.

set -euo pipefail

IDCS_DOMAIN="${IDCS_DOMAIN:-https://idcs-${IDCS_DOMAIN_ID}.identity.oraclecloud.com}"
APP_NAME="oci-mcp-gateway"
OUTPUT_DIR="${1:-.}"

echo "=== IDCS OAuth App Setup for MCP Gateway ==="
echo "Domain: $IDCS_DOMAIN"
echo ""

echo "This script provides the manual steps to configure IDCS."
echo "OCI does not have a CLI for IDCS app creation — use the console."
echo ""

cat <<'INSTRUCTIONS'
1. Go to OCI Console → Identity → Domains → Default Domain → Applications
2. Create a new "Confidential Application"
3. Configure:
   - Name: oci-mcp-gateway
   - Description: MCP Gateway OAuth Application
   - Grant type: Client Credentials
   - Token expiry: 3600 seconds
   - Allowed scopes: read:tools, write:tools, admin:gateway

4. After creation, note:
   - Client ID
   - Client Secret

5. Export the JWKS signing certificate:
   - Domain Settings → Signing Certificate → Download
   - Convert to PEM format:
     openssl x509 -in signing-cert.pem -pubkey -noout > jwt-public-key.pem

6. Create the K8s secret:
   kubectl create secret generic oci-mcp-gateway-secrets \
     --from-file=jwt-public-key.pem=jwt-public-key.pem \
     -n oci-mcp --dry-run=client -o yaml | kubectl apply -f -

7. Test token acquisition:
   TOKEN=$(curl -s -X POST \
     "$IDCS_DOMAIN/oauth2/v1/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=client_credentials&scope=read:tools" \
     -u "$CLIENT_ID:$CLIENT_SECRET" | jq -r '.access_token')

   curl -H "Authorization: Bearer $TOKEN" http://<GATEWAY_LB_IP>/mcp/health
INSTRUCTIONS

echo ""
echo "=== Done ==="
