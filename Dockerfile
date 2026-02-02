FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY foreman ./foreman

# Install build dependencies, then install the package
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "foreman.main:app", "--host", "0.0.0.0", "--port", "8000"]
