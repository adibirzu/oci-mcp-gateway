# RLM Analysis: MCP Gateway Deployment Pipeline
**Date**: 2026-03-21 | **Commit**: 0635063 | **Mode**: Full | **Files Analyzed**: 38

## Executive Summary

The MCP Gateway deployment pipeline has **3 critical**, **7 high**, **10 medium**, and **4 low** severity findings across Dockerfiles, Kubernetes manifests, deploy scripts, and Terraform. The most urgent issues are: a bearer token hardcoded in a ConfigMap (not a Secret), a CORS wildcard that opens the gateway to cross-origin attacks, and a non-functional HPA that has been failing for 10+ hours. The IAM Terraform also has a dynamic group matching rule that targets the wrong resource type.

## Critical Findings (3)

### [CRITICAL] Bearer Token in ConfigMap
- **Location**: `deploy/kubernetes/gateway/configmap.yaml:25-29`
- **Description**: The MCP_STATIC_TOKEN is embedded verbatim in the `static_tokens` map inside the ConfigMap JSON. ConfigMaps are stored unencrypted in etcd.
- **Impact**: Anyone with `kubectl get cm` access reads a valid bearer token granting `read:tools + write:tools`.
- **Fix**: Move token to the existing `oci-mcp-gateway-secrets` Secret and reference via env var or volume mount.
- **Confidence**: High

### [CRITICAL] CORS Wildcard Nullifies Allowlist
- **Location**: `deploy/kubernetes/gateway/configmap.yaml:33`
- **Description**: `cors_origins: ["https://cp.octodemo.cloud", "https://ops.octodemo.cloud", "*"]` — the `*` makes the other entries meaningless.
- **Impact**: Any web page can make cross-origin requests to the gateway, which has real OCI credentials.
- **Fix**: Remove `"*"` from the cors_origins array.
- **Confidence**: High

### [CRITICAL] HPA Non-Functional — Metrics Server Missing
- **Location**: `deploy/kubernetes/gateway/hpa.yaml`
- **Description**: `ScalingActive: False` with 2540+ `FailedGetResourceMetric` events. The OKE cluster lacks a metrics-server.
- **Impact**: Gateway is pinned at 2 replicas regardless of load. No auto-scaling available.
- **Fix**: Install metrics-server on OKE (`kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`) or use OCI Metrics Server addon.
- **Confidence**: High

## High Findings (7)

### [HIGH] APM Data Key Hardcoded in Deployment
- **Location**: `deploy/kubernetes/gateway/deployment.yaml:61`
- **Fix**: Move `OCI_APM_DATA_KEY` to a Secret reference.

### [HIGH] No Egress NetworkPolicy — Backends Can Reach Anything
- **Location**: `deploy/kubernetes/shared/networkpolicy.yaml`
- **Fix**: Add Egress policy restricting backends to OCI API endpoints.

### [HIGH] Gateway LB on Plain HTTP (Port 80, No TLS)
- **Location**: `deploy/kubernetes/gateway/service.yaml:19`
- **Fix**: Add OCI LB SSL certificate annotations or terminate TLS at API Gateway only.

### [HIGH] Security Backend Transport Mismatch
- **Location**: `deploy/kubernetes/backends/security/deployment.yaml:35`
- **Fix**: Verify `MCP_TRANSPORT=http` is correct for oci-mcp-security (it has custom routes at `/health`).

### [HIGH] Terraform Dynamic Group Targets 'cluster' Not Pods
- **Location**: `deploy/terraform/iam.tf:18`
- **Fix**: Change to `resource.type='computeinstance'` or use OKE workload identity matching.

### [HIGH] Overly Broad "read all-resources" Policy
- **Location**: `deploy/terraform/iam.tf:32`
- **Fix**: Replace with specific resource families per backend.

### [HIGH] db-observatory ENTRYPOINT Triggers Observability Init at Import
- **Location**: `dockerfiles/Dockerfile.db-observatory:38-45`
- **Fix**: Guard observability init with try/except or use separate entry script.

## Medium Findings (10)

| # | Finding | Location |
|---|---------|----------|
| 1 | Missing container-level securityContext | All deployment.yaml files |
| 2 | TCP probes instead of HTTP health checks | 4/5 backend deployments |
| 3 | Stale `mcp-gateway` LB service (18 days, unmanaged) | Live cluster only |
| 4 | No PodDisruptionBudget for single-replica backends | All backend deployments |
| 5 | Finops Dockerfile hardcodes host/port in ENTRYPOINT | dockerfiles/Dockerfile.finops |
| 6 | API Gateway backend URL may double-prefix /mcp | deploy/terraform/api_gateway_route.tf |
| 7 | Backend rollout failures silently swallowed | deploy/scripts/deploy.sh:40 |
| 8 | No CI pipeline or automated image scanning | Project-wide |
| 9 | Python 3.11 vs 3.12 inconsistency (security backend) | oci-mcp-security/Dockerfile |
| 10 | Gateway Dockerfile requires manual pre-build copy | Dockerfile:17-19 |

## Low Findings (4)

| # | Finding | Location |
|---|---------|----------|
| 1 | No base image digest pinning | All Dockerfiles |
| 2 | secrets.yaml committed with empty values | gateway/secrets.yaml |
| 3 | deploy.sh grep name extraction is fragile | deploy/scripts/deploy.sh:39 |
| 4 | build-all.sh SSH quoting fragile | deploy/scripts/build-all.sh:89 |

## Statistics

| Category | Files | Findings |
|----------|-------|----------|
| Dockerfiles | 6 | 8 |
| K8s Manifests | 17 | 12 |
| Scripts | 3 | 4 |
| Terraform | 2 | 5 |
| **Total** | **38** | **29** |

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High | 7 |
| Medium | 10 |
| Low | 4 |

## Recommendations (Priority Order)

1. **Immediate**: Move bearer token from ConfigMap to Secret. Remove CORS `"*"`.
2. **This week**: Move APM data key to Secret. Add container securityContext. Delete stale `mcp-gateway` service.
3. **Next sprint**: Install metrics-server for HPA. Add Egress NetworkPolicy. Fix Terraform IAM. Add CI pipeline with image scanning.
4. **Backlog**: Pin base image digests. Add PDBs. Convert TCP probes to HTTP. Standardize Python 3.12 across fleet.
