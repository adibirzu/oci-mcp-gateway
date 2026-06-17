# Security & Remediation

This document tracks (1) the **secret/identifier leak remediation plan** and
(2) the status of the findings from `rlm_deployment_pipeline_report.md`.

> **Do not "fix" a committed leak with a new commit.** A new commit does not
> remove the value from history. The correct remediation is a history rewrite
> (`git filter-repo --replace-text`) followed by a force-push and credential
> rotation. The recipe below is intended to be run **by a maintainer**, not
> automatically.

---

## 1. Committed identifier leak — remediation plan (NOT yet executed)

Real tenancy identifiers are present in committed files. Per the repo's
redaction convention, these must be replaced with `<PLACEHOLDER>` tokens that
resolve via a local-only secrets file, and purged from history.

### 1.1 Inventory

> Values below are **masked** so this doc itself does not re-leak them. The
> exact strings live in the local-only secrets file
> (`~/.claude/private/octo-apm-redactions.md`); the maintainer pastes them into
> the local `redactions.txt` when running the rewrite.

| # | Value (class) | Masked | Placeholder | Files |
|---|---------------|--------|-------------|-------|
| 1 | OCIR tenancy namespace | `fr4zqf…` | `${OCIR_TENANCY}` | 6 backend/gateway `deployment.yaml`, `deploy/scripts/build-all.sh` |
| 2 | IDCS domain GUID | `idcs-2818…6675` | `<IDCS_DOMAIN_ID>` | `config/gateway.json`, `deploy/scripts/setup-idcs-app.sh` |
| 3 | LB subnet OCID | `ocid1.subnet.oc1.eu-frankfurt-1.aaaa…h7x2hq` | `<GATEWAY_LB_SUBNET_OCID>` | `deploy/kubernetes/gateway/service.yaml` |
| 4 | APM upload endpoint host | `aaaadheru…apm-agt.eu-frankfurt-1.…` | `<APM_UPLOAD_ENDPOINT>` | `deploy/kubernetes/gateway/deployment.yaml` |
| 5 | Internal demo domains (optional) | `cp/ops.octodemo.cloud` | `<CP_ORIGIN>`, `<OPS_ORIGIN>` | `config/gateway.json`, `configmap.yaml`, `api_gateway_route.tf` |

None of these are *credentials* (the APM **data key** and static token are
already in a K8s Secret, not committed). But OCIDs/namespaces/endpoints
fingerprint the tenancy and topology, which the redaction rule forbids.

### 1.2 History-rewrite recipe (maintainer runs this)

```bash
# 1. Fresh mirror clone (never rewrite your working clone)
git clone --mirror <repo-url> oci-mcp-gateway-rewrite.git
cd oci-mcp-gateway-rewrite.git

# 2. Replacement map — build it locally, keep it OUT of the repo.
#    Fill the LEFT side with the exact values from
#    ~/.claude/private/octo-apm-redactions.md (do NOT commit this file).
cat > /tmp/redactions.txt <<'EOF'
<OCIR_NAMESPACE_LITERAL>==>${OCIR_TENANCY}
idcs-<IDCS_GUID_LITERAL>==>idcs-<IDCS_DOMAIN_ID>
<SUBNET_OCID_LITERAL>==><GATEWAY_LB_SUBNET_OCID>
<APM_HOST_LITERAL>==><APM_UPLOAD_ENDPOINT>
EOF

# 3. Rewrite every commit on every branch/tag
git filter-repo --replace-text /tmp/redactions.txt

# 4. Force-push the rewritten history
git push --force --mirror <repo-url>
```

After the rewrite, the working tree must consume these via env substitution at
deploy time (see `README.md` → Deployment), e.g.:

```bash
export OCIR_TENANCY=...        # from local secrets file
export IDCS_DOMAIN_ID=...
envsubst < deploy/kubernetes/gateway/deployment.yaml | kubectl apply -f -
```

### 1.3 Pre-commit gate (add to `.git/hooks/pre-commit`)

```bash
git diff --cached -U0 | grep -nE 'ocid1\.[a-z]+\.oc1|${OCIR_TENANCY}|idcs-[0-9a-f]{32}|apm-agt' \
  && echo "ABORT: real OCI identifier in staged diff" && exit 1
exit 0
```

---

## 2. RLM findings — remediation status

Source: `rlm_deployment_pipeline_report.md` (29 findings). Status as of this pass.

### Critical

| Finding | Status | Notes |
|---------|--------|-------|
| Bearer token in ConfigMap | ✅ Fixed | `configmap.yaml` `static_tokens: {}`; token injected via `MCP_GATEWAY_STATIC_TOKEN` `secretKeyRef` |
| CORS wildcard `*` | ✅ Fixed | `configmap.yaml` lists only `cp/ops.octodemo.cloud` |
| HPA non-functional (no metrics-server) | ⚠️ Operational | Manifest is correct; cluster must run metrics-server. See README → Autoscaling |

### High

| Finding | Status | Notes |
|---------|--------|-------|
| APM data key hardcoded | ✅ Fixed | `OCI_APM_DATA_KEY` via `secretKeyRef` |
| No egress NetworkPolicy | ✅ Fixed | `shared/networkpolicy.yaml` `backend-egress` (DNS, 443, IMDS only) |
| LB plain HTTP, no TLS | ◑ Partial | TLS now terminates on 443 (`oci-load-balancer-tls-secret`). Plaintext **:80 still open** on the LB and used by the API Gateway backend hop. Recommend: API GW → LB:443, then drop :80 |
| Security backend transport mismatch | ✅ N/A | All backends use `MCP_TRANSPORT=streamable-http` consistently |
| Terraform dynamic-group targets wrong type | ◑ Review | `matching_rule` matches **all** compute instances in the compartment. With `instance_principal` this works but is broad — scope to a node-pool tag. Also the SA carries a `workload-identity` annotation that is unused under instance-principal auth — remove for clarity |
| Over-broad "read all-resources" | ✅ Fixed | `iam.tf` now lists per-service resource families, not `all-resources` |
| db-observatory init-at-import ENTRYPOINT | ◑ Review | Still a fragile inline `python -c`. Recommend a committed `entrypoint.py` in the backend repo |

### This pass (newly fixed here)

| Change | File |
|--------|------|
| Gateway probes TCP → HTTP `/health` + `/ready` | `gateway/deployment.yaml` |
| PodDisruptionBudgets (gateway + backends) | `shared/pdb.yaml` |

### Remaining backlog (operational / cross-repo)

- Install **metrics-server** on OKE so the HPA leaves `ScalingActive: False`.
- Pin base image **digests** (`python:3.12-slim@sha256:…`) in all Dockerfiles.
- Backend pods keep **TCP probes** by design — their MCP servers expose only
  `POST /mcp` (no GET health route). The gateway's `/ready` aggregates backend
  health via the registry, which is the correct layer. Adding a GET `/health`
  to the backend MCP servers is an engine-side enhancement.
- Delete the stale unmanaged `mcp-gateway` LB service from the live cluster.

---

## 3. Engine bug fixed during this pass

`mcp_server_oci.gateway.server.create_gateway()` defined `gateway_lifespan`
but never wired it into the `FastMCP` instance. Result: the `BackendRegistry`
was never populated, so `gateway_health` (and any readiness probe reading it)
reported **zero backends** even while proxied tools served correctly. Fixed by
adding `"lifespan": gateway_lifespan` to the FastMCP kwargs. This is what makes
the new `/ready` probe report true backend state.
