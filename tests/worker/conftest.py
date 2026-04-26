"""Worker test configuration.

All dependencies (foreman, boto3, google-genai, opentelemetry) are installed
in the dev environment, so no sys.modules stubs are needed. Tests mock at the
fixture level using MagicMock/AsyncMock.
"""
