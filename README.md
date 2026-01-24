# Foreman

Foreman is the event-driven backend for managing image-generation requests for AI models.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **OpenTelemetry Integration** - Full distributed tracing and observability
- **RESTful API** - Complete CRUD operations for image generation requests
- **Async Support** - Asynchronous request handling for better performance
- **Docker Ready** - Includes Dockerfile and docker-compose for easy deployment

## Installation

### Using pip

```bash
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

## Running the Application

### Local Development

```bash
uvicorn foreman.main:app --reload
```

The API will be available at `http://localhost:8000`

### With Docker Compose (includes Jaeger for tracing)

```bash
docker-compose up
```

- API: `http://localhost:8000`
- Jaeger UI: `http://localhost:16686`

## API Documentation

Once the application is running, you can access:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## API Endpoints

### Health Check
- `GET /` - Root endpoint with health check
- `GET /health` - Health check endpoint

### Image Generation Requests
- `POST /requests` - Create a new image generation request
- `GET /requests` - List all requests
- `GET /requests/{request_id}` - Get a specific request
- `PUT /requests/{request_id}/status` - Update request status
- `DELETE /requests/{request_id}` - Delete a request

## Example Usage

### Create a Request

```bash
curl -X POST "http://localhost:8000/requests" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A beautiful sunset over mountains",
    "model": "stable-diffusion-v1",
    "width": 512,
    "height": 512,
    "num_images": 1
  }'
```

### List All Requests

```bash
curl "http://localhost:8000/requests"
```

### Get a Specific Request

```bash
curl "http://localhost:8000/requests/{request_id}"
```

## OpenTelemetry Configuration

The application supports OpenTelemetry instrumentation. Configure the OTLP endpoint using environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
uvicorn foreman.main:app
```

If no endpoint is configured, the application will run without exporting traces.

## Testing

Run tests with pytest:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=foreman tests/
```

## Development

### Code Formatting

The project uses Ruff for linting and formatting:

```bash
ruff check .
ruff format .
```

## Project Structure

```
foreman/
├── foreman/
│   ├── __init__.py       # Package initialization
│   ├── main.py           # FastAPI application
│   ├── models.py         # Pydantic models
│   └── telemetry.py      # OpenTelemetry configuration
├── tests/
│   ├── __init__.py
│   └── test_main.py      # Application tests
├── Dockerfile            # Docker image configuration
├── docker-compose.yml    # Docker compose with Jaeger
├── pyproject.toml        # Project dependencies
└── README.md            # This file
```

## License

MIT
