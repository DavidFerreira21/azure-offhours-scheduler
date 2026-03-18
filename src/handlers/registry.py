from __future__ import annotations

from handlers.base_handler import ResourceHandler


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ResourceHandler] = {}

    def register(self, resource_types: set[str], handler: ResourceHandler) -> None:
        for resource_type in resource_types:
            self._handlers[resource_type.lower()] = handler

    def get_handler(self, resource_type: str) -> ResourceHandler | None:
        return self._handlers.get(resource_type.lower())
