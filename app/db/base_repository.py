from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional, Dict, Any
from pydantic import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(ABC, Generic[ModelType]):
    """
    Repositório base abstrato para operações de banco de dados.

    Esta abstração permite trocar implementação de Supabase para PostgreSQL
    no futuro sem modificar a camada de serviço.

    Padrão: Repository Pattern + Adapter Pattern
    """

    @abstractmethod
    async def create(self, obj: ModelType) -> ModelType:
        """Cria um novo registro"""
        pass

    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """Busca registro por ID"""
        pass

    @abstractmethod
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """Lista registros com paginação e filtros"""
        pass

    @abstractmethod
    async def update(self, id: str, obj: ModelType) -> Optional[ModelType]:
        """Atualiza registro existente"""
        pass

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Deleta registro"""
        pass

    @abstractmethod
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Conta registros com filtros opcionais"""
        pass
