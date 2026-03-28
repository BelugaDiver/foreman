"""Tests for image schemas."""

import pytest

from foreman.schemas.image import ImageUpdate, ImageUploadRequest


class TestImageUploadRequestValidators:
    """Tests for ImageUploadRequest field validators."""

    def test_filename_no_path_separators_forward_slash(self):
        """Validator should reject filename with forward slash."""
        with pytest.raises(ValueError, match="path separators"):
            ImageUploadRequest(
                filename="path/to/file.jpg",
                content_type="image/jpeg",
                size_bytes=1024,
            )

    def test_filename_no_path_separators_backslash(self):
        """Validator should reject filename with backslash."""
        with pytest.raises(ValueError, match="path separators"):
            ImageUploadRequest(
                filename="path\\to\\file.jpg",
                content_type="image/jpeg",
                size_bytes=1024,
            )

    def test_filename_no_double_dots(self):
        """Validator should reject filename with .."""
        with pytest.raises(ValueError, match=r"\.\."):
            ImageUploadRequest(
                filename="../etc/passwd",
                content_type="image/jpeg",
                size_bytes=1024,
            )

    def test_filename_empty_raises(self):
        """Validator should reject empty filename."""
        with pytest.raises(Exception, match="at least 1 character"):
            ImageUploadRequest(
                filename="",
                content_type="image/jpeg",
                size_bytes=1024,
            )

    def test_content_type_not_allowed(self):
        """Validator should reject non-image content types."""
        with pytest.raises(Exception, match="pattern"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="application/json",
                size_bytes=1024,
            )

    def test_content_type_case_insensitive(self):
        """Validator should reject uppercase content types (pattern requires lowercase)."""
        with pytest.raises(Exception, match="pattern"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="IMAGE/JPEG",
                size_bytes=1024,
            )

    def test_size_bytes_zero(self):
        """Validator should reject size_bytes of 0."""
        with pytest.raises(Exception, match="greater than 0"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="image/jpeg",
                size_bytes=0,
            )

    def test_size_bytes_negative(self):
        """Validator should reject negative size_bytes."""
        with pytest.raises(Exception, match="greater than 0"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="image/jpeg",
                size_bytes=-1,
            )

    def test_size_bytes_exceeds_limit(self):
        """Validator should reject size_bytes > 50MB."""
        with pytest.raises(ValueError, match="50MB"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="image/jpeg",
                size_bytes=100_000_000,
            )

    def test_valid_request_all_fields(self):
        """Validator should accept valid request with all fields."""
        request = ImageUploadRequest(
            filename="test.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
        )
        assert request.filename == "test.jpg"
        assert request.content_type == "image/jpeg"
        assert request.size_bytes == 1024

    def test_valid_request_png(self):
        """Validator should accept image/png."""
        request = ImageUploadRequest(
            filename="test.png",
            content_type="image/png",
            size_bytes=2048,
        )
        assert request.content_type == "image/png"

    def test_valid_request_webp(self):
        """Validator should accept image/webp."""
        request = ImageUploadRequest(
            filename="test.webp",
            content_type="image/webp",
            size_bytes=3072,
        )
        assert request.content_type == "image/webp"

    def test_valid_request_gif(self):
        """Validator should accept image/gif."""
        request = ImageUploadRequest(
            filename="test.gif",
            content_type="image/gif",
            size_bytes=4096,
        )
        assert request.content_type == "image/gif"


class TestImageUpdate:
    """Tests for ImageUpdate schema."""

    def test_allows_url_field(self):
        """ImageUpdate should allow url field."""
        update = ImageUpdate(url="https://example.com/image.jpg")
        assert update.url == "https://example.com/image.jpg"

    def test_url_defaults_to_none(self):
        """ImageUpdate should default url to None."""
        update = ImageUpdate()
        assert update.url is None

    def test_rejects_extra_fields(self):
        """ImageUpdate should reject extra fields."""
        with pytest.raises(ValueError):
            ImageUpdate(unknown_field="value")
