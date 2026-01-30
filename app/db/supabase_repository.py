from typing import List, Optional, Dict, Any, Type
from supabase import Client
from pydantic import BaseModel
from app.db.base_repository import BaseRepository, ModelType
import logging

logger = logging.getLogger(__name__)


class SupabaseRepository(BaseRepository[ModelType]):
    """
    Implementação concreta do repositório usando Supabase.

    Args:
        client: Cliente Supabase
        table_name: Nome da tabela no Supabase
        model_class: Classe Pydantic do modelo
    """

    def __init__(
        self,
        client: Client,
        table_name: str,
        model_class: Type[ModelType]
    ):
        self.client = client
        self.table_name = table_name
        self.model_class = model_class

    async def create(self, obj: ModelType) -> ModelType:
        """Cria novo registro no Supabase"""
        try:
            data = obj.model_dump(exclude_unset=True)
            response = self.client.table(self.table_name).insert(data).execute()

            if response.data:
                return self.model_class(**response.data[0])
            raise Exception("Falha ao criar registro")

        except Exception as e:
            logger.error(f"Erro ao criar {self.table_name}: {e}")
            raise

    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """Busca registro por ID"""
        try:
            response = self.client.table(self.table_name)\
                .select("*")\
                .eq("id", id)\
                .single()\
                .execute()

            if response.data:
                return self.model_class(**response.data)
            return None

        except Exception as e:
            logger.error(f"Erro ao buscar {self.table_name} por ID: {e}")
            return None

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """Lista registros com paginação e filtros"""
        try:
            query = self.client.table(self.table_name).select("*")

            # Aplicar filtros dinamicamente
            if filters:
                for key, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(key, value)
                    elif value is not None:
                        query = query.eq(key, value)

            response = query.range(skip, skip + limit - 1).execute()

            return [self.model_class(**item) for item in response.data]

        except Exception as e:
            logger.error(f"Erro ao listar {self.table_name}: {e}")
            return []

    async def update(self, id: str, obj: ModelType) -> Optional[ModelType]:
        """Atualiza registro existente"""
        try:
            data = obj.model_dump(exclude_unset=True, exclude={"id"})
            response = self.client.table(self.table_name)\
                .update(data)\
                .eq("id", id)\
                .execute()

            if response.data:
                return self.model_class(**response.data[0])
            return None

        except Exception as e:
            logger.error(f"Erro ao atualizar {self.table_name}: {e}")
            raise

    async def delete(self, id: str) -> bool:
        """Deleta registro (soft delete se coluna deleted_at existir)"""
        try:
            # Verificar se tabela tem coluna deleted_at para soft delete
            # Por padrão, faz hard delete
            response = self.client.table(self.table_name)\
                .delete()\
                .eq("id", id)\
                .execute()

            return True

        except Exception as e:
            logger.error(f"Erro ao deletar {self.table_name}: {e}")
            return False

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Conta registros"""
        try:
            query = self.client.table(self.table_name).select("*", count="exact")

            if filters:
                for key, value in filters.items():
                    if value is not None:
                        query = query.eq(key, value)

            response = query.execute()
            return response.count if response.count else 0

        except Exception as e:
            logger.error(f"Erro ao contar {self.table_name}: {e}")
            return 0
