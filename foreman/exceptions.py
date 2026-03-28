"""Domain exceptions for Foreman API."""


class ResourceNotFoundError(Exception):
    """Raised when a resource doesn't exist or user doesn't have access."""

    def __init__(self, resource: str, identifier: str | None = None):
        self.resource = resource
        self.identifier = identifier
        msg = f"{resource} not found"
        if identifier:
            msg += f": {identifier}"
        super().__init__(msg)


class DuplicateResourceError(Exception):
    """Raised when creating a resource that already exists."""

    def __init__(self, resource: str, field: str, value: str):
        self.resource = resource
        self.field = field
        self.value = value
        super().__init__(f"{resource} with {field}='{value}' already exists")


class InvalidStateError(Exception):
    """Raised when operation can't be performed due to current resource state."""

    def __init__(self, resource: str, identifier: str, operation: str, valid_states: str):
        self.resource = resource
        self.identifier = identifier
        self.operation = operation
        self.valid_states = valid_states
        super().__init__(f"Cannot {operation} {resource} in state '{valid_states}'")
