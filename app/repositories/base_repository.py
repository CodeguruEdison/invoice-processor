from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):

    @abstractmethod
    async def create(self, entity: T) -> T:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:
        raise NotImplementedError

    @abstractmethod
    async def get_all(self) -> list[T]:
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity: T) -> T:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        raise NotImplementedError