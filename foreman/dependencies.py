"""Dependency injection interfaces and container for Foreman."""
from typing import Any, TypeVar, Callable, Union


T = TypeVar('T')


class DependencyContainer:
    """Simple dependency injection container for managing service instances."""
    
    def __init__(self):
        self._services: dict[type, Union[type, Callable[[], Any]]] = {}
        self._instances: dict[type, Any] = {}
    
    def register(self, interface: type[T], factory: Union[type[T], Callable[[], T]], singleton: bool = True) -> None:
        """
        Register a service with the container.
        
        Args:
            interface: The interface/type to register
            factory: Factory function or class that creates the service instance
            singleton: If True, only one instance will be created (default: True)
        """
        self._services[interface] = factory
        if singleton:
            # Pre-create singleton instances
            # Handle both class constructors and factory functions
            if callable(factory):
                self._instances[interface] = factory()
            else:
                self._instances[interface] = factory()
    
    def resolve(self, interface: type[T]) -> T:
        """
        Resolve a service from the container.
        
        Args:
            interface: The interface/type to resolve
            
        Returns:
            The service instance
            
        Raises:
            KeyError: If the service is not registered
        """
        if interface in self._instances:
            return self._instances[interface]
        
        if interface not in self._services:
            raise KeyError(f"Service {interface} not registered")
        
        return self._services[interface]()
    
    def clear(self) -> None:
        """Clear all registered services and instances."""
        self._services.clear()
        self._instances.clear()


# Global container instance
_container = DependencyContainer()


def get_container() -> DependencyContainer:
    """Get the global dependency container."""
    return _container
