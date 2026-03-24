# AGENTS.md – Essential Developer Guidelines

## Commands
- Install deps: `pip install -e ".[dev]"`
- Run tests: `pytest`
- Single test: `pytest tests/test_main.py::test_health_endpoint -v`
- Lint: `ruff check .`
- Format: `ruff format .`

## Code Style
- Imports: stdlib → third-party → local (alphabetical)
- Naming: snake_case (vars/functions), PascalCase (classes), UPPER_CASE (constants)
- Line length: 100 chars (ruff enforced)
- Types: Pydantic v2 for schemas, @dataclass for domain objects
- Error handling: Use HTTPException for API errors, try/except for external calls

## Key References
- Detailed architecture: `instructions/ARCHITECTURE.md`
- Testing standards: `instructions/TESTING.md`
- Security practices: `.github/copilot-instructions.md`

## Repository Structure
```
/foreman
├── foreman/          # Main app (models, schemas, repositories, etc.)
├── tests/            # Test suite
├── migrations/       # DB migrations
├── instructions/     # Detailed guidelines (moved from root)
└── config files...
```