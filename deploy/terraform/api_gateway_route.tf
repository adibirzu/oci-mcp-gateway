# API Gateway route: forward /mcp/* to the gateway LoadBalancer
# This extends the existing C20 API Gateway deployment.

variable "api_gateway_id" {
  description = "OCID of the existing OCI API Gateway (C20)"
  type        = string
}

variable "gateway_lb_ip" {
  description = "IP address of the oci-mcp-gateway LoadBalancer service"
  type        = string
}

resource "oci_apigateway_deployment" "mcp_route" {
  compartment_id = var.compartment_ocid
  gateway_id     = var.api_gateway_id
  path_prefix    = "/mcp"
  display_name   = "oci-mcp-gateway-route"

  specification {
    routes {
      path    = "/{path*}"
      methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

      backend {
        type = "HTTP_BACKEND"
        url  = "http://${var.gateway_lb_ip}:80/mcp/$${request.path[path]}"

        connect_timeout_in_seconds = 10
        read_timeout_in_seconds    = 60
        send_timeout_in_seconds    = 60
      }

      request_policies {
        cors {
          allowed_origins = [
            "https://cp.octodemo.cloud",
            "https://ops.octodemo.cloud",
          ]
          allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
          allowed_headers = ["*"]
          max_age_in_seconds = 3600
        }
      }
    }
  }
}
