"""Tests for audit logging."""

import pytest
from unittest.mock import patch

from foreman.audit import AuditEvent, log_audit


def test_audit_log_user_created():
    """Should log user creation events."""
    with patch("foreman.audit.audit_logger") as mock_logger:
        log_audit(AuditEvent.USER_CREATED, user_id="user-123")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Audit: user.created" in call_args[0][0]
        assert call_args[1]["extra"]["user_id"] == "user-123"


def test_audit_log_project_deleted():
    """Should log project deletion events."""
    with patch("foreman.audit.audit_logger") as mock_logger:
        log_audit(
            AuditEvent.PROJECT_DELETED,
            user_id="user-123",
            resource_id="project-456",
            resource_type="project",
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Audit: project.deleted" in call_args[0][0]
        assert call_args[1]["extra"]["user_id"] == "user-123"
        assert call_args[1]["extra"]["resource_id"] == "project-456"
        assert call_args[1]["extra"]["resource_type"] == "project"


def test_audit_event_values():
    """AuditEvent enum should have correct string values."""
    assert AuditEvent.USER_CREATED == "user.created"
    assert AuditEvent.USER_DELETED == "user.deleted"
    assert AuditEvent.PROJECT_DELETED == "project.deleted"
    assert AuditEvent.GENERATION_CANCELLED == "generation.cancelled"
    assert AuditEvent.IMAGE_DELETED == "image.deleted"
