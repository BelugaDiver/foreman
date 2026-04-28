"""Tests for worker/providers/vertex.py – GeminiProvider."""

from __future__ import annotations

import asyncio
import io
import os
import socket
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.providers.vertex import GeminiProvider, ImageResult, MAX_DOWNLOAD_BYTES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(**kwargs) -> GeminiProvider:
    defaults = dict(
        project_id="test-project",
        location="us-central1",
        image_model="gemini-3.1-flash-image-preview",
        enhancement_model="gemini-2.0-flash",
        allowed_image_domains=None,
    )
    defaults.update(kwargs)
    return GeminiProvider(**defaults)


def _make_genai_client_mock(image_bytes: bytes = b"PNG_FAKE_DATA") -> MagicMock:
    """Build a mock genai.Client whose generate_content returns an image part."""
    part = MagicMock()
    part.inline_data = MagicMock()
    part.inline_data.data = image_bytes

    candidate = MagicMock()
    candidate.content.parts = [part]

    response = MagicMock()
    response.candidates = [candidate]

    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

def test_init_defaults():
    """Default values are set correctly."""
    provider = GeminiProvider()
    assert provider.location == "us-central1"
    assert provider.image_model == "gemini-3.1-flash-image-preview"
    assert provider.enhancement_model == "gemini-2.0-flash"
    assert provider.allowed_image_domains == set()
    assert provider._client is None


def test_init_project_id_from_param():
    """project_id from constructor param is stored."""
    provider = GeminiProvider(project_id="my-proj")
    assert provider.project_id == "my-proj"


def test_init_project_id_from_env(monkeypatch):
    """project_id falls back to GOOGLE_PROJECT_ID env var."""
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "env-proj")
    # Clear cached value by creating new instance without param
    provider = GeminiProvider(project_id=None)
    assert provider.project_id == "env-proj"


# ---------------------------------------------------------------------------
# _get_client
# ---------------------------------------------------------------------------

def test_get_client_creates_client():
    """_get_client calls genai.Client with vertexai=True."""
    provider = _make_provider()
    mock_client = MagicMock()
    with patch("worker.providers.vertex.genai.Client", return_value=mock_client) as mock_cls:
        client = provider._get_client()
        mock_cls.assert_called_once_with(
            vertexai=True,
            project="test-project",
            location="us-central1",
        )
        assert client is mock_client


def test_get_client_lazy_init_called_once():
    """_get_client caches the client and only creates it once."""
    provider = _make_provider()
    mock_client = MagicMock()
    with patch("worker.providers.vertex.genai.Client", return_value=mock_client) as mock_cls:
        c1 = provider._get_client()
        c2 = provider._get_client()
        assert c1 is c2
        mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# enhance_prompt
# ---------------------------------------------------------------------------

async def test_enhance_prompt_calls_model():
    """enhance_prompt calls generate_content and returns text."""
    provider = _make_provider()
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = "enhanced prompt"

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        result = await provider.enhance_prompt("my prompt", "https://example.com/img.jpg")

    assert result == "enhanced prompt"
    mock_client.models.generate_content.assert_called_once()


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

async def test_generate_no_input_image():
    """generate() with no input image calls model and returns ImageResult."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock()

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        result = await provider.generate(prompt="draw something", input_image_url=None)

    assert isinstance(result, ImageResult)
    assert result.output_image_url.startswith("file://")
    assert result.model_used == "gemini-3.1-flash-image-preview"

    # Cleanup temp file
    path = result.output_image_url.replace("file://", "")
    if os.path.exists(path):
        os.unlink(path)


async def test_generate_with_gs_uri():
    """generate() with gs:// URI uses types.Part.from_uri."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock()

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        with patch("worker.providers.vertex.types.Part.from_uri") as mock_from_uri:
            mock_from_uri.return_value = MagicMock()
            result = await provider.generate(
                prompt="draw",
                input_image_url="gs://my-bucket/img.jpg",
                enhance_prompt=False,
            )

    mock_from_uri.assert_called_once()
    path = result.output_image_url.replace("file://", "")
    if os.path.exists(path):
        os.unlink(path)


async def test_generate_with_gs_uri_bad_mime_raises():
    """generate() with non-image MIME type raises ValueError."""
    provider = _make_provider()

    with pytest.raises(ValueError, match="unrecognised image extension"):
        await provider.generate(
            prompt="draw",
            input_image_url="gs://my-bucket/file.pdf",
            enhance_prompt=False,
        )


async def test_generate_http_url_calls_download_image():
    """generate() with http URL calls _download_image."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock()

    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.write(fd, b"FAKE_IMAGE")
    os.close(fd)

    try:
        with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
            with patch.object(provider, "_download_image", new=AsyncMock(return_value=(tmp_path, "image/jpeg"))):
                result = await provider.generate(
                    prompt="draw",
                    input_image_url="https://example.com/img.jpg",
                    enhance_prompt=False,
                )
        assert isinstance(result, ImageResult)
        path = result.output_image_url.replace("file://", "")
        if os.path.exists(path):
            os.unlink(path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def test_generate_no_candidates_raises():
    """generate() raises ValueError when model returns no candidates."""
    provider = _make_provider()
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.candidates = []

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        with pytest.raises(ValueError, match="No candidates"):
            await provider.generate(prompt="draw", input_image_url=None)


async def test_generate_no_image_data_raises():
    """generate() raises ValueError when response has no image inline_data."""
    provider = _make_provider()
    mock_client = MagicMock()

    part = MagicMock()
    part.inline_data = None  # no image data

    candidate = MagicMock()
    candidate.content.parts = [part]
    mock_client.models.generate_content.return_value.candidates = [candidate]

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        with pytest.raises(ValueError, match="No image generated"):
            await provider.generate(prompt="draw", input_image_url=None)


# ---------------------------------------------------------------------------
# _download_image
# ---------------------------------------------------------------------------

async def test_download_image_rejects_non_https():
    """_download_image raises ValueError for non-HTTPS URLs."""
    provider = _make_provider()
    with pytest.raises(ValueError, match="HTTPS"):
        await provider._download_image("http://example.com/img.jpg")


async def test_download_image_dns_failure():
    """_download_image raises ValueError when DNS resolution fails."""
    provider = _make_provider()
    with patch("worker.providers.vertex.socket.getaddrinfo", side_effect=socket.gaierror("no such host")):
        with pytest.raises(ValueError, match="Cannot resolve"):
            await provider._download_image("https://nonexistent.invalid/img.jpg")


async def test_download_image_private_ip_blocked():
    """_download_image raises ValueError for private/non-global IPs."""
    provider = _make_provider()
    # Simulate DNS resolving to a private IP
    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("192.168.1.1", 0))
    ]):
        with pytest.raises(ValueError, match="non-global IP"):
            await provider._download_image("https://internal.corp/img.jpg")


async def test_download_image_domain_not_in_allowlist():
    """_download_image raises ValueError when domain is not in allowlist."""
    provider = _make_provider(allowed_image_domains={"allowed.example.com"})
    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("1.2.3.4", 0))
    ]):
        with pytest.raises(ValueError, match="not in allowlist"):
            await provider._download_image("https://notallowed.example.com/img.jpg")


async def test_download_image_content_length_too_large():
    """_download_image raises ValueError when Content-Length exceeds limit."""
    provider = _make_provider()

    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_response.headers.get = lambda key, default=None: (
        str(MAX_DOWNLOAD_BYTES + 1) if key == "Content-Length" else default
    )

    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("1.2.3.4", 0))
    ]):
        with patch("worker.providers.vertex.urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(ValueError, match="Content-Length"):
                await provider._download_image("https://example.com/huge.jpg")


async def test_download_image_streaming_cap_exceeded():
    """_download_image raises ValueError when streaming data exceeds limit."""
    provider = _make_provider()

    # Build a mock response with no Content-Length but oversized body
    oversized_chunk = b"X" * (MAX_DOWNLOAD_BYTES + 1)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        class headers:
            @staticmethod
            def get(key, default=None):
                return default  # No Content-Length

        def read(self, size):
            return oversized_chunk

    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("1.2.3.4", 0))
    ]):
        with patch("worker.providers.vertex.urllib.request.urlopen", return_value=FakeResponse()):
            with pytest.raises(ValueError, match="exceeded"):
                await provider._download_image("https://example.com/huge.jpg")


async def test_download_image_success():
    """_download_image downloads content and returns (path, mime_type)."""
    provider = _make_provider()
    image_bytes = b"FAKE_PNG"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        class headers:
            @staticmethod
            def get(key, default=None):
                if key == "Content-Type":
                    return "image/png; charset=utf-8"
                return default

        _chunks = [image_bytes, b""]

        def read(self, size):
            return self._chunks.pop(0) if self._chunks else b""

    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("1.2.3.4", 0))
    ]):
        with patch("worker.providers.vertex.urllib.request.urlopen", return_value=FakeResponse()):
            path, mime = await provider._download_image("https://example.com/img.png")

    assert mime == "image/png"
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == image_bytes
    os.unlink(path)


async def test_generate_with_enhance_prompt_and_image_url():
    """generate() calls enhance_prompt when enhance_prompt=True and input_image_url is set."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock()

    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.write(fd, b"FAKE")
    os.close(fd)

    try:
        with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
            with patch.object(provider, "_download_image", new=AsyncMock(return_value=(tmp_path, "image/jpeg"))):
                with patch.object(provider, "enhance_prompt", new=AsyncMock(return_value="enhanced!")) as mock_enhance:
                    result = await provider.generate(
                        prompt="original",
                        input_image_url="https://example.com/img.jpg",
                        enhance_prompt=True,
                    )
        mock_enhance.assert_called_once_with("original", "https://example.com/img.jpg")
        path = result.output_image_url.replace("file://", "")
        if os.path.exists(path):
            os.unlink(path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def test_generate_http_url_unlink_oserror_swallowed():
    """OSError from os.unlink after HTTP image download is swallowed."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock()

    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.write(fd, b"FAKE")
    os.close(fd)

    try:
        with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
            with patch.object(provider, "_download_image", new=AsyncMock(return_value=(tmp_path, "image/jpeg"))):
                with patch("worker.providers.vertex.os.unlink", side_effect=OSError("busy")):
                    result = await provider.generate(
                        prompt="draw",
                        input_image_url="https://example.com/img.jpg",
                        enhance_prompt=False,
                    )
        assert isinstance(result, ImageResult)
        # Unlink was patched, so tmp_path still exists
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        path = result.output_image_url.replace("file://", "")
        if os.path.exists(path):
            os.unlink(path)


async def test_download_image_empty_addr_infos():
    """_download_image raises ValueError when getaddrinfo returns empty list."""
    provider = _make_provider()
    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[]):
        with pytest.raises(ValueError, match="No addresses resolved"):
            await provider._download_image("https://weird.host/img.jpg")


async def test_download_image_invalid_ip_address():
    """_download_image raises ValueError when resolved IP cannot be parsed."""
    provider = _make_provider()
    # Return an unparseable IP string
    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("not-an-ip", 0))
    ]):
        with pytest.raises(ValueError, match="could not be validated"):
            await provider._download_image("https://example.com/img.jpg")


async def test_download_image_malformed_content_length_header():
    """Malformed Content-Length header is ignored and streaming proceeds."""
    provider = _make_provider()
    image_bytes = b"SMALL_IMAGE"

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

        class headers:
            @staticmethod
            def get(key, default=None):
                if key == "Content-Type":
                    return "image/png"
                if key == "Content-Length":
                    return "not-a-number"  # malformed
                return default

        _data = [image_bytes, b""]
        def read(self, size):
            return self._data.pop(0) if self._data else b""

    with patch("worker.providers.vertex.socket.getaddrinfo", return_value=[
        (None, None, None, None, ("1.2.3.4", 0))
    ]):
        with patch("worker.providers.vertex.urllib.request.urlopen", return_value=FakeResponse()):
            path, mime = await provider._download_image("https://example.com/img.png")

    assert mime == "image/png"
    assert os.path.exists(path)
    os.unlink(path)


async def test_generate_temp_file_write_exception_cleanup():
    """Exception writing temp file → cleanup attempted and exception re-raised."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock(image_bytes=b"PNG")

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        with patch("worker.providers.vertex.os.fdopen", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                await provider.generate(prompt="draw", input_image_url=None)


async def test_generate_temp_file_write_exception_unlink_oserror():
    """Exception writing temp file + OSError on cleanup unlink → exception still re-raised."""
    provider = _make_provider()
    mock_client = _make_genai_client_mock(image_bytes=b"PNG")

    with patch("worker.providers.vertex.genai.Client", return_value=mock_client):
        with patch("worker.providers.vertex.os.fdopen", side_effect=OSError("disk full")):
            with patch("worker.providers.vertex.os.unlink", side_effect=OSError("unlink failed")):
                with pytest.raises(OSError, match="disk full"):
                    await provider.generate(prompt="draw", input_image_url=None)
