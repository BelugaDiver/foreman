"""Tests for worker/config.py – get_allowed_image_domains."""

from worker.config import WorkerConfig


def test_get_allowed_image_domains_empty():
    """Both r2_public_url and r2_endpoint empty → empty set."""
    config = WorkerConfig()
    config.r2_public_url = ""
    config.r2_endpoint = ""
    assert config.get_allowed_image_domains() == set()


def test_get_allowed_image_domains_r2_public_url():
    """r2_public_url with hostname → hostname in set."""
    config = WorkerConfig()
    config.r2_public_url = "https://cdn.example.com"
    config.r2_endpoint = ""
    domains = config.get_allowed_image_domains()
    assert "cdn.example.com" in domains


def test_get_allowed_image_domains_r2_endpoint():
    """r2_endpoint with hostname → hostname in set."""
    config = WorkerConfig()
    config.r2_public_url = ""
    config.r2_endpoint = "https://account-id.r2.cloudflarestorage.com"
    domains = config.get_allowed_image_domains()
    assert "account-id.r2.cloudflarestorage.com" in domains


def test_get_allowed_image_domains_both():
    """Both set → both hostnames in set."""
    config = WorkerConfig()
    config.r2_public_url = "https://cdn.example.com"
    config.r2_endpoint = "https://account-id.r2.cloudflarestorage.com"
    domains = config.get_allowed_image_domains()
    assert "cdn.example.com" in domains
    assert "account-id.r2.cloudflarestorage.com" in domains
    assert len(domains) == 2


def test_get_allowed_image_domains_url_without_hostname():
    """URL that parses without a hostname → not added."""
    config = WorkerConfig()
    config.r2_public_url = "not-a-url"
    config.r2_endpoint = ""
    # urllib.parse.urlparse("not-a-url").hostname is None → nothing added
    assert config.get_allowed_image_domains() == set()
