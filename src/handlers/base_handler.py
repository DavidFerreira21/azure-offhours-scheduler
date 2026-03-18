from __future__ import annotations

from abc import ABC, abstractmethod

from discovery.resource_graph import ScheduledResource


class ResourceHandler(ABC):
    @abstractmethod
    def get_state(self, resource: ScheduledResource) -> str:
        raise NotImplementedError

    @abstractmethod
    def start(self, resource: ScheduledResource) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self, resource: ScheduledResource) -> None:
        raise NotImplementedError
