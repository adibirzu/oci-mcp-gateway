# OCI MCP Gateway

A single, authenticated **[Model Context Protocol](https://modelcontextprotocol.io)
endpoint** that aggregates several OCI-focused MCP servers behind one URL,
deployable to **Oracle Kubernetes Engine (OKE)**.

One agent connects to `https://<gateway>/mcp` and transparently gets the tools
of every backend — OCI infrastructure, Logging Analytics, security, FinOps, and
database observability — with per-tool namespacing, JWT/static-token auth,
health aggregation, and OpenTelemetry tracing into OCI APM.

```
                              ┌─────────────────────────────┐
   agent / client  ──HTTPS──▶ │  OCI MCP Gateway  (:9000)   │
   (one /mcp URL)             │  • auth (JWT / static token)│
                              │  • tool namespacing         │
                              │  • health + audit + OTEL    │
                              └───────────────┬─────────────┘
                                              │ streamable-http (in-cluster)
        ┌──────────────┬──────────────┬───────┴──────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼
     logan            oci          security        finops          dbobs
  (LogAnalytics) (infra/compute) (CloudGuard…)  (cost/FinOps)  (DB observ.)
        └──────────────┴──────────────┴──────────────┴──────────────┘
                  each a standalone MCP server, tools exposed as
                  backendname_toolname  (e.g. logan_search_logs)
```

---

## Why this exists (design rationale)

Running one MCP server per OCI domain is clean for development but painful for
consumers: every agent must be configured with five URLs, five sets of
credentials, and five health checks. The gateway collapses that into **one
endpoint, one auth boundary, one observability surface**:

- **One auth boundary.** Clients present a single bearer token (IDCS JWT in
  prod, static token in dev). The gateway enforces scopes; backends trust only
  in-cluster traffic and authenticate to OCI with their own resource/instance
  principal.
- **Namespacing prevents tool collisions.** Two backends can both define a
  `list_resources` tool; the gateway exposes them as `oci_list_resources` and
  `security_list_resources`.
- **Health is aggregated, not guessed.** The gateway maintains a live registry
  of backend health and exposes it both as an MCP tool (`gateway_health`) and as
  HTTP probes (`/ready`) that Kubernetes can act on.
- **Stateless + horizontally scalable.** With `stateless_http`, any replica can
  serve any request, so the gateway scales behind a LoadBalancer/HPA.

### This repo is a thin wrapper

The heavy lifting (registry, proxying, auth, middleware) lives in the
**`mcp-server-oci`** package's `gateway` module. This repo adds only what OKE
deployment needs:

| File | Responsibility |
|------|----------------|
| `src/oci_mcp_gateway/app.py` | Builds the engine's FastMCP app and attaches `/health` + `/ready` probe routes; wires the backend registry into the health module |
| `src/oci_mcp_gateway/health.py` | Liveness/readiness logic backed by the live `BackendRegistry` |
| `src/oci_mcp_gateway/observability.py` | OpenTelemetry → OCI APM (traces + metrics) |
| `src/oci_mcp_gateway/__main__.py` | Entry point: init OTEL → build → serve |
| `config/`, `deploy/`, `Dockerfile` | Config, K8s manifests, Terraform, images |

> **Build/serve split.** The engine's `run_gateway()` builds *and* serves in one
> blocking call, leaving no seam to attach K8s probes. The wrapper drops one
> level to `create_gateway()` (build) → attach probes → `gateway.run()` (serve).
> See `app.py` for the rationale.

---

## Repositories in this system

| Repo | Role |
|------|------|
| **oci-mcp-gateway** (this) | OKE deployment wrapper + manifests |
| **mcp-server-oci** | The gateway engine *and* the `oci` infrastructure backend |
| oci-logan / oci-mcp-security / finopsai-mcp / mcp-oci-database-observatory | The other four backends |

---

## Quickstart — local development

This is the fastest way to see the gateway multiplex real tools. It needs the
gateway engine (`mcp-server-oci`) available locally.

```bash
# 1. Create a venv and install the engine + this wrapper (editable)
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e /path/to/mcp-oci          # the gateway engine
uv pip install -e ".[otel,dev]"             # this wrapper

# 2. Minimal config: one backend (the oci server itself), auth off
cat > /tmp/gw.json <<JSON
{
  "name": "oci-mcp-gateway-local",
  "host": "127.0.0.1", "port": 9001, "path": "/mcp", "stateless": true,
  "auth": { "enabled": false, "cors_origins": [] },
  "backends": [
    { "name": "oci", "transport": "stdio",
      "command": "$(which python)", "args": ["-m", "mcp_server_oci.server"],
      "auth_method": "oci_config", "oci_profile": "DEFAULT",
      "namespace_tools": true, "health_check_interval": 60 }
  ],
  "enable_audit_log": true, "enable_metrics": false
}
JSON

# 3. Run it
MCP_GATEWAY_CONFIG=/tmp/gw.json python -m oci_mcp_gateway
```

In another shell:

```bash
curl -s localhost:9001/health   # {"status":"ok",...}
curl -s localhost:9001/ready    # {"status":"ready","total":1,"healthy":1,...}
```

List the aggregated tools through MCP:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:9001/mcp") as c:
        names = [t.name for t in await c.list_tools()]
        print(len(names), "tools")          # ~47
        print([n for n in names if n.startswith("gateway_")])
        print([n for n in names if n.startswith("oci_")][:5])

asyncio.run(main())
```

The full local stdio config for all five backends lives in
`config/gateway.dev.json` (each backend points at its sibling repo).

### Run the tests

```bash
source .venv/bin/activate
ruff check src tests
pytest                  # 8 tests; test_app.py self-skips if engine is absent
```

---

## Configuration reference

Config is a JSON file referenced by `MCP_GATEWAY_CONFIG` (env vars override
individual fields — see `mcp_server_oci.gateway.config`).

| Key | Meaning |
|-----|---------|
| `host` / `port` / `path` | Bind address and MCP path (`/mcp`) |
| `stateless` | `true` for horizontal scaling (no per-session state) |
| `auth.enabled` | Master switch for token enforcement |
| `auth.jwt_public_key_file` | PEM public key for verifying IDCS RS256 JWTs |
| `auth.jwt_issuer` / `jwt_audience` | Expected `iss` / `aud` claims |
| `auth.static_tokens` | `{token: {client_id, scopes}}` — dev only |
| `auth.required_scopes` / `tool_scopes` | Coarse and per-tool scope gates |
| `auth.cors_origins` | Allowed browser origins (**never** `*` in prod) |
| `backends[]` | Backend list (see below) |
| `enable_audit_log` / `enable_metrics` | Audit buffer + metrics toggles |

**Backend entry:**

| Key | Meaning |
|-----|---------|
| `name` | Namespace prefix for the backend's tools |
| `transport` | `streamable_http` (prod) or `stdio` (local) |
| `url` | For HTTP transport: in-cluster service URL |
| `command` / `args` / `cwd` / `pythonpath` | For stdio transport |
| `auth_method` | `resource_principal` / `instance_principal` / `oci_config` |
| `namespace_tools` | Prefix tools with `name_` (recommended `true`) |
| `health_check_interval` | Seconds between backend health checks |

---

## Authentication

- **Production:** IDCS-issued OAuth2 JWTs (RS256). The gateway verifies the
  signature against a PEM public key mounted from the
  `oci-mcp-gateway-secrets` Secret, and checks `iss`/`aud`/scopes. See
  `deploy/scripts/setup-idcs-app.sh` for the IDCS confidential-app setup and
  JWKS export steps.
- **Development:** static tokens declared in config under
  `auth.static_tokens`, or via `MCP_GATEWAY_STATIC_TOKEN`.

Clients send `Authorization: Bearer <token>`. Backends never see the client
token — they authenticate to OCI independently via resource/instance principal.

---

## Observability

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OpenTelemetry. With
`OCI_APM_DATA_KEY` set, the exporter targets OCI APM's private upload endpoint
(`dataKey` auth header); without it, it speaks plain OTLP/HTTP to any collector.

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://<APM_UPLOAD_ENDPOINT>"
export OCI_APM_DATA_KEY="<from K8s secret, never commit>"
export OTEL_SERVICE_NAME="oci-mcp-gateway"
```

Traces (per tool call, from the guardrail middleware) and metrics (tool-call
counts + latency) appear in the APM dashboard. The data key is injected via
`secretKeyRef`, never inlined.

---

## Deployment to OKE

> **Tenancy values are placeholders.** OCIR namespace, IDCS domain, subnet
> OCID, and APM endpoint must be supplied at deploy time, never committed. See
> `docs/SECURITY.md`.

```bash
# 1. Build & push all images on an x86_64 build VM (ARM Macs must not build
#    amd64 images locally). Tags with a timestamp + latest.
./deploy/scripts/build-all.sh                 # or: build-all.sh gateway oci

# 2. Create the secret (JWT key, static token, APM data key).
#    Generate a random dev token first:  openssl rand -hex 32
kubectl create secret generic oci-mcp-gateway-secrets \
  --from-file=jwt-public-key.pem=./jwt-public-key.pem \
  --from-literal=static-token=PASTE_GENERATED_TOKEN \
  --from-literal=apm-data-key=APM_DATA_KEY \
  -n oci-mcp --dry-run=client -o yaml | kubectl apply -f -

# 3. Deploy shared resources, backends, then the gateway
./deploy/scripts/deploy.sh                     # or: deploy.sh backends | gateway
```

Layout under `deploy/kubernetes/`:

- `shared/` — namespace, ServiceAccount (workload identity), RBAC,
  NetworkPolicies (gateway-only ingress to backends; egress limited to DNS +
  OCI 443 + IMDS), and PodDisruptionBudgets.
- `backends/<name>/` — Deployment + Service per backend (port 8000).
- `gateway/` — ConfigMap, Secret template, Deployment, Service (LB, TLS on
  443), HPA.

### Health, probes, autoscaling

- The gateway serves `/health` (liveness) and `/ready` (readiness, HTTP 503 if
  no backend is healthy) on the MCP port. Kubernetes probes use these.
- Backends keep **TCP** probes — their MCP servers expose only `POST /mcp`. The
  gateway's `/ready` is the authoritative aggregate of backend health.
- The HPA needs **metrics-server** on the cluster; without it the HPA stays
  `ScalingActive: False` and replicas are pinned. Install:
  `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `mcp_server_oci_not_installed` on startup | Engine not installed: `pip install -e /path/to/mcp-oci` |
| `/ready` returns `not_ready: registry_not_initialized` | Probe hit before the lifespan registered backends; expected for the first ~10s after start |
| `/ready` returns `total: 0` while tools work | Engine missing the lifespan wiring — see `docs/SECURITY.md` §3 (fixed) |
| `/mcp` returns 405 to `curl` | Correct — `/mcp` is POST-only; use an MCP client |
| HPA `FailedGetResourceMetric` | metrics-server not installed (see above) |
| Backend shows `unhealthy` in `/ready` | Check the backend pod logs and its OCI auth (resource/instance principal policy) |

---

## Security

See **[`docs/SECURITY.md`](docs/SECURITY.md)** for the identifier-leak
remediation plan (history rewrite recipe) and the full status of the RLM audit
findings. Highlights: secrets via `secretKeyRef` only, scoped IAM policy per
backend, restricted egress, TLS at the LB, non-root read-only containers.

## License

MIT.
