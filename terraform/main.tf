terraform {
  required_providers = {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

resource "cloudflare_r2_bucket" "foreman" {
  account_id = var.cloudflare_account_id
  name       = "foreman-images"
}

resource "cloudflare_r2_custom_domain" "foreman" {
  count       = var.storage_domain != "" ? 1 : 0
  bucket_name = cloudflare_r2_bucket.foreman.name
  domain      = var.storage_domain
}
