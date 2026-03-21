# IAM: Dynamic group + policies for OKE nodes running MCP server pods.
# Uses instance principal auth (pods inherit node identity via oci-demo-cp-oke).

variable "tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment where OKE cluster runs"
  type        = string
}

# Dynamic group matching OKE worker nodes (instance principal).
# OKE pods on these nodes inherit the instance's identity.
resource "oci_identity_dynamic_group" "mcp_pods" {
  compartment_id = var.tenancy_ocid
  name           = "oci-mcp-gateway-pods"
  description    = "OKE worker nodes running MCP server pods"
  matching_rule  = "ANY {instance.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "mcp_policy" {
  compartment_id = var.tenancy_ocid
  name           = "oci-mcp-gateway-policy"
  description    = "Least-privilege policies for MCP gateway backends"

  statements = [
    # Logging Analytics (logan server)
    "Allow dynamic-group oci-mcp-gateway-pods to read log-analytics-log-group in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read log-analytics-entity in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read log-analytics-lookup in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to use log-analytics-query in tenancy",

    # Compute, networking, identity (oci server — read only)
    "Allow dynamic-group oci-mcp-gateway-pods to read instances in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read vcns in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read subnets in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read compartments in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read domains in tenancy",

    # Cloud Guard (security server)
    "Allow dynamic-group oci-mcp-gateway-pods to read cloud-guard-problems in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read cloud-guard-detectors in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read cloud-guard-targets in tenancy",

    # Vulnerability Scanning (security server)
    "Allow dynamic-group oci-mcp-gateway-pods to read vss-family in tenancy",

    # Cost/Usage reports (finops server)
    "Allow dynamic-group oci-mcp-gateway-pods to read usage-reports in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read usage-budgets in tenancy",

    # Operations Insights (db-observatory server)
    "Allow dynamic-group oci-mcp-gateway-pods to read opsi-database-insights in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to read opsi-host-insights in tenancy",

    # Object Storage (namespace resolution for logan)
    "Allow dynamic-group oci-mcp-gateway-pods to read objectstorage-namespaces in tenancy",

    # APM (observability)
    "Allow dynamic-group oci-mcp-gateway-pods to use apm-domains in tenancy",
  ]
}
