# Foreman

Foreman is the event-driven backend for managing image-generation requests for AI models.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **OpenTelemetry Integration** - Full distributed tracing and observability
- **Health Check Endpoints** - Simple health monitoring
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

Configure the service to talk to your external PostgreSQL instance via environment variables before starting the server:

```bash
export DATABASE_URL=postgresql://username:password@db-hostname:5432/foreman
export DB_POOL_MIN_SIZE=1         # Optional, defaults to 1
export DB_POOL_MAX_SIZE=10        # Optional, defaults to 10
export DB_COMMAND_TIMEOUT_SECONDS=30  # Optional
```

If `DATABASE_URL` is omitted, the API will start but database helpers remain unavailable. This is useful for quick local smoke tests, but production deployments **must** provide a valid PostgreSQL DSN.

### With Docker Compose (includes Jaeger for tracing)

```bash
docker-compose up
```

- API: `http://localhost:8000`
- Jaeger UI: `http://localhost:16686`

Docker Compose loads sensitive settings from `.env.foreman`, which you should create locally (or in CI) by copying `.env.foreman.example` and filling in the real credentials. The file is ignored by git, so each environment can manage its own secrets without exposing them in `docker-compose.yml`.

## API Documentation

Once the application is running, you can access:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## API Endpoints

### Health Check

- `GET /` - Root endpoint with health check
- `GET /health` - Health check endpoint

## Example Usage

### Check Health

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "service": "foreman"
}
```

## Database Migrations

Foreman ships with Alembic configured for raw-SQL migrations while the application itself talks directly to PostgreSQL using `asyncpg` (no ORM layer).

1. Install the dev/migrations tooling:

  ```bash
  pip install -e ".[dev]"
  ```

2. Ensure `DATABASE_URL` points at the database you want to mutate.
3. Create a new revision (edit the generated file under `migrations/versions/`):

  ```bash
  alembic revision -m "create jobs table"
  ```

4. Apply the latest schema:

  ```bash
  alembic upgrade head
  ```

All migration files are plain Python functions; express the desired DDL with `op.execute("... SQL ...")` or `op.create_table(...)` helpers. Since PostgreSQL is expected to run as an external service, ensure your network/security rules allow Alembic to connect from your workstation or CI runner.

## OpenTelemetry Configuration

The application supports OpenTelemetry instrumentation. Configure the OTLP endpoint using environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
uvicorn foreman.main:app
```

If no endpoint is configured, the application will run without exporting traces.

### Security Configuration

For production deployments, configure these environment variables:

```bash
# Use specific allowed origins instead of wildcard
export CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Use secure OTLP connections with TLS
export OTEL_EXPORTER_OTLP_INSECURE=false
export OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector:4317
```

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
│   ├── test_main.py      # Application tests
│   └── test_telemetry.py # Telemetry tests
├── Dockerfile            # Docker image configuration
├── docker-compose.yml    # Docker compose with Jaeger
├── pyproject.toml        # Project dependencies
└── README.md            # This file
```

## License

MIT
