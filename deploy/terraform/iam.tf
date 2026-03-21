# IAM: Dynamic group + policies for OKE pods running MCP servers
# These pods need read access to OCI APIs via resource principal auth.

variable "tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment where OKE cluster runs"
  type        = string
}

resource "oci_identity_dynamic_group" "mcp_pods" {
  compartment_id = var.tenancy_ocid
  name           = "oci-mcp-gateway-pods"
  description    = "OKE pods in oci-mcp namespace running MCP servers"
  matching_rule  = "ALL {resource.type='cluster', resource.compartment.id='${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "mcp_policy" {
  compartment_id = var.tenancy_ocid
  name           = "oci-mcp-gateway-policy"
  description    = "Policies for MCP gateway and backend servers"

  statements = [
    # Logging Analytics (logan server)
    "Allow dynamic-group oci-mcp-gateway-pods to read log-analytics-* in tenancy",
    "Allow dynamic-group oci-mcp-gateway-pods to use log-analytics-query in tenancy",

    # General read access (oci server)
    "Allow dynamic-group oci-mcp-gateway-pods to read all-resources in tenancy",

    # Cloud Guard (security server)
    "Allow dynamic-group oci-mcp-gateway-pods to read cloud-guard-* in tenancy",

    # Vulnerability Scanning (security server)
    "Allow dynamic-group oci-mcp-gateway-pods to read vss-* in tenancy",

    # Cost/Usage reports (finops server)
    "Allow dynamic-group oci-mcp-gateway-pods to read usage-reports in tenancy",

    # Operations Insights (db-observatory server)
    "Allow dynamic-group oci-mcp-gateway-pods to read opsi-* in tenancy",

    # APM (observability)
    "Allow dynamic-group oci-mcp-gateway-pods to use apm-domains in tenancy",
  ]
}
