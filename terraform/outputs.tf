output "r2_endpoint" {
  description = "R2 bucket endpoint URL"
  value       = cloudflare_r2_bucket.foreman.endpoint
}

output "r2_bucket_name" {
  description = "R2 bucket name"
  value       = cloudflare_r2_bucket.foreman.name
}

output "r2_public_url" {
  description = "Public URL for accessing files"
  value       = var.storage_domain != "" ? "https://${var.storage_domain}" : cloudflare_r2_bucket.foreman.bucket_domain_name
}
