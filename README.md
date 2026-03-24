# Foreman

Foreman is the event-driven backend for managing image-generation requests for AI models.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **Async PostgreSQL** - Raw SQL via `asyncpg`, no ORM
- **Alembic Migrations** - Controllable schema changes with raw SQL
- **OpenTelemetry** - Full distributed tracing and observability
- **Docker** - PostgreSQL + Jaeger + API via docker-compose

## Quick Start

### 1. Clone and start

```bash
docker-compose up -d
```

### 2. Verify

```bash
curl http://localhost:8000/health
```

### 3. Explore

- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Jaeger UI**: http://localhost:16686

---

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.foreman.example .env.foreman.local
# Edit .env.foreman.local with your database credentials
```

### Run Migrations

```bash
alembic upgrade head
```

### Run the App

```bash
uvicorn foreman.main:app --reload
```

### Run Tests

```bash
pytest
```

### Lint & Format

```bash
ruff check .
ruff format .
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `DB_POOL_MIN_SIZE` | Connection pool min | 1 |
| `DB_POOL_MAX_SIZE` | Connection pool max | 10 |
| `DB_COMMAND_TIMEOUT_SECONDS` | Query timeout | 30 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint for tracing | - |
| `CORS_ORIGINS` | Allowed CORS origins | * |

### Docker

Docker Compose loads settings from `.env.foreman`. Create it from the example:

```bash
cp .env.foreman.example .env.foreman
# Edit with your secrets
```

---

## Project Structure

```
foreman/
├── foreman/              # Main application
│   ├── main.py          # FastAPI app entry point
│   ├── db.py            # Async PostgreSQL utilities
│   ├── models/          # Dataclass models
│   ├── schemas/          # Pydantic schemas
│   ├── repositories/    # Database CRUD operations
│   ├── api/             # API endpoints
│   └── telemetry.py     # OpenTelemetry setup
├── tests/               # Test suite
├── migrations/          # Alembic migrations
├── docker-compose.yml   # PostgreSQL + Jaeger + API
└── alembic.ini         # Alembic configuration
```

---

## License

MIT
