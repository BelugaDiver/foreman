FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY foreman ./foreman

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "foreman.main:app", "--host", "0.0.0.0", "--port", "8000"]
