variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with R2 write access"
  type        = string
  sensitive   = true
}

variable "storage_domain" {
  description = "Custom domain for R2 (optional)"
  type        = string
  default     = ""
}
