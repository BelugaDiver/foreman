# Copilot Instructions for Foreman

## Project Overview
Foreman is an event-driven backend for managing image-generation requests for AI models. The project is built with Python and focuses on asynchronous event processing.

## General Coding Standards

### Python Code Style
- Use Python 3.8+ features and syntax
- Follow PEP 8 style guidelines for all Python code
- Use type hints for function signatures and class attributes
- Prefer `pathlib` over `os.path` for file operations
- Use f-strings for string formatting

### Naming Conventions
- Use `snake_case` for functions, variables, and module names
- Use `PascalCase` for class names
- Use `UPPER_CASE` for constants
- Prefix private methods and attributes with a single underscore (`_`)

### Documentation
- Add docstrings to all public functions, classes, and modules
- Use Google-style or NumPy-style docstrings consistently
- Include type information in docstrings when not using type hints
- Document exceptions that functions may raise

### Code Organization
- Keep functions focused and small (ideally under 50 lines)
- Group related functionality into modules
- Avoid circular imports
- Use `__init__.py` files to expose public APIs

## Event-Driven Architecture

### Event Handling
- Use asynchronous patterns (`async`/`await`) for event handlers
- Implement proper error handling and retry logic for event processing
- Log all significant events with appropriate log levels
- Use message queues (e.g., RabbitMQ, Redis, Kafka) for event communication

### AI Model Integration
- Abstract AI model interactions behind interfaces
- Handle API rate limits and timeouts gracefully
- Implement fallback mechanisms for model failures
- Cache model responses when appropriate

## Testing

### Test Requirements
- Write unit tests for all business logic
- Use `pytest` as the testing framework
- Aim for >80% code coverage
- Mock external dependencies (APIs, databases, queues)
- Include integration tests for critical paths

### Test Organization
- Place tests in a `tests/` directory mirroring the source structure
- Name test files with `test_` prefix
- Name test functions with `test_` prefix
- Use fixtures for common test setup

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_module.py
```

## Dependencies

### Dependency Management
- Use `pyproject.toml` for tracking all dependencies
- Use `>=` for dependency version specifications to allow compatible updates
- Regularly update dependencies for security patches
- Check for known vulnerabilities before adding new dependencies

### Virtual Environments
- Always use virtual environments (venv, virtualenv, or conda)
- Document Python version requirements
- Include instructions for setting up the development environment

## Error Handling

### Exception Handling
- Use specific exception types for known error cases
- In request handlers, include a base `Exception` catch after specific exceptions
- Log exceptions with full stack traces
- Provide meaningful error messages
- Handle edge cases explicitly
- Use context managers (`with` statements) for resource management

### Logging
- Use Python's `logging` module, not `print()` statements
- Set appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Include contextual information in log messages
- Configure logging in a centralized location
- Use structured logging for production environments

## Security

### Security Best Practices
- Never commit secrets, API keys, or credentials to the repository
- Use environment variables or secret management systems for sensitive data
- Validate and sanitize all external inputs
- Use parameterized queries for database operations
- Keep dependencies updated to patch security vulnerabilities
- Implement proper authentication and authorization

## Performance

### Optimization Guidelines
- Profile code before optimizing
- Use appropriate data structures (e.g., sets for membership tests)
- Implement caching for expensive operations
- Use database connection pooling
- Optimize I/O operations with async patterns
- Monitor and log performance metrics

## Git Workflow

### Commit Guidelines
- Write clear, descriptive commit messages
- Keep commits focused on a single change
- Reference issue numbers in commit messages
- Avoid committing build artifacts or temporary files

### Code Review
- Ensure all tests pass before requesting review
- Address linting and formatting issues
- Provide context in pull request descriptions
- Respond to review feedback promptly

## Examples

### Good Code Example
```python
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class ImageGenerationRequest:
    """Represents a request to generate an image using an AI model."""
    
    def __init__(self, prompt: str, model_id: str, user_id: str) -> None:
        self.prompt = prompt
        self.model_id = model_id
        self.user_id = user_id
    
    async def process(self) -> Optional[str]:
        """
        Process the image generation request.
        
        Returns:
            str: URL of the generated image, or None if generation failed.
        
        Raises:
            ValueError: If the prompt is empty or invalid.
        """
        if not self.prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        logger.info(f"Processing image generation request for user {self.user_id}")
        
        try:
            # Process the request
            image_url = await self._generate_image()
            logger.info(f"Image generated successfully: {image_url}")
            return image_url
        except Exception as e:
            logger.error(f"Failed to generate image: {e}", exc_info=True)
            return None
    
    async def _generate_image(self) -> str:
        """Generate image using AI model."""
        # Implementation details
        pass
```

### Code to Avoid
```python
# Bad: No type hints, poor naming, no error handling
def process(req):
    print("processing...")
    result = req.do_stuff()
    return result

# Bad: Using bare except (no exception type specified)
try:
    dangerous_operation()
except:
    pass

# Bad: Synchronous code in async context
def handle_event(event):
    time.sleep(5)  # Blocks the event loop
    return process_event(event)
```

## Tools and Commands

### Linting and Formatting
```bash
# Format code with black
black .

# Check code style with flake8
flake8 .

# Type check with mypy
mypy src/

# Sort imports with isort
isort .
```

### Development Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Unix/macOS
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e .
pip install -e ".[dev]"
```
