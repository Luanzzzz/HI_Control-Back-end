"""
Repository para operações de persistência de Notas Fiscais no Supabase.

Implementa estratégia de upsert atômico para evitar duplicidades.
"""
from supabase import Client
from app.models.nota_fiscal import NotaFiscalCreate, NotaFiscalResponse
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class NotaFiscalRepository:
    """
    Repository para notas_fiscais com upsert atômico.
    
    Utiliza função nativa .upsert() do Supabase para garantir
    atomicidade e performance na detecção de duplicidades.
    """
    
    def __init__(self, db: Client):
        """
        Inicializa repository com cliente Supabase.
        
        Args:
            db: Cliente Supabase (preferencialmente admin para bypass RLS)
        """
        self.db = db
        self.table_name = "notas_fiscais"
    
    def upsert_nota(self, nota: NotaFiscalCreate) -> NotaFiscalResponse:
        """
        Insere ou atualiza nota fiscal baseado na chave_acesso (UPSERT ATÔMICO).
        
        Strategy:
        - Usa .upsert() nativo do Supabase
        - Conflict resolution em chave_acesso
        - Atualiza apenas campos relevantes se já existe
        
        Args:
            nota: Modelo de criação da nota fiscal
        
        Returns:
            Nota fiscal persistida/atualizada
        
        Raises:
            Exception: Em caso de erro na persistência
        """
        try:
            # Preparar dados para upsert
            # mode='json' garante que datetime seja serializado corretamente
            nota_dict = nota.model_dump(
                exclude={"id", "created_at", "updated_at", "deleted_at"},
                mode='json'  # Serializa datetime como ISO string
            )
            
            logger.info(f"Executando upsert para nota: {nota.chave_acesso}")
            
            # UPSERT ATÔMICO usando função nativa do Supabase
            # on_conflict especifica qual coluna usar para detectar conflito
            response = self.db.table(self.table_name)\
                .upsert(
                    nota_dict,
                    on_conflict="chave_acesso"  # Coluna UNIQUE constraint
                )\
                .execute()
            
            if not response.data or len(response.data) == 0:
                raise Exception("Upsert não retornou dados")
            
            nota_persistida = response.data[0]
            
            logger.info(
                f"Nota {nota.chave_acesso} persistida com sucesso | "
                f"ID: {nota_persistida.get('id')}"
            )
            
            return NotaFiscalResponse(**nota_persistida)
            
        except Exception as e:
            logger.error(f"Erro ao fazer upsert da nota {nota.chave_acesso}: {e}")
            raise
    
    def upsert_lote(self, notas: List[NotaFiscalCreate]) -> List[NotaFiscalResponse]:
        """
        Insere ou atualiza múltiplas notas em batch (mais eficiente).
        
        Args:
            notas: Lista de notas para persistir
        
        Returns:
            Lista de notas persistidas
        """
        if not notas:
            return []
        
        try:
            # mode='json' serializa datetime corretamente
            notas_dict = [
                nota.model_dump(
                    exclude={"id", "created_at", "updated_at", "deleted_at"},
                    mode='json'  # Importante para serializar datetime
                )
                for nota in notas
            ]
            
            logger.info(f"Executando upsert em lote de {len(notas)} notas")
            
            response = self.db.table(self.table_name)\
                .upsert(
                    notas_dict,
                    on_conflict="chave_acesso"
                )\
                .execute()
            
            if not response.data:
                logger.warning("Upsert em lote não retornou dados")
                return []
            
            logger.info(f"Lote de {len(response.data)} notas persistido com sucesso")
            
            return [NotaFiscalResponse(**nota) for nota in response.data]
            
        except Exception as e:
            logger.error(f"Erro ao fazer upsert em lote: {e}")
            raise
    
    def buscar_por_chave(
        self, 
        chave_acesso: str, 
        empresa_id: Optional[str] = None
    ) -> Optional[NotaFiscalResponse]:
        """
        Busca nota por chave de acesso.
        
        Args:
            chave_acesso: Chave de 44 dígitos
            empresa_id: Filtro opcional por empresa
        
        Returns:
            Nota encontrada ou None
        """
        try:
            query = self.db.table(self.table_name)\
                .select("*")\
                .eq("chave_acesso", chave_acesso)
            
            if empresa_id:
                query = query.eq("empresa_id", empresa_id)
            
            response = query.execute()
            
            if response.data and len(response.data) > 0:
                return NotaFiscalResponse(**response.data[0])
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao buscar nota por chave {chave_acesso}: {e}")
            return None
    
    def listar_por_empresa(
        self,
        empresa_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[NotaFiscalResponse]:
        """
        Lista notas de uma empresa com paginação.
        
        Args:
            empresa_id: UUID da empresa
            limit: Máximo de resultados
            offset: Offset para paginação
        
        Returns:
            Lista de notas
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .order("data_emissao", desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            if not response.data:
                return []
            
            return [NotaFiscalResponse(**nota) for nota in response.data]
            
        except Exception as e:
            logger.error(f"Erro ao listar notas da empresa {empresa_id}: {e}")
            return []
    
    def contar_por_empresa(self, empresa_id: str) -> int:
        """
        Conta total de notas de uma empresa.
        
        Args:
            empresa_id: UUID da empresa
        
        Returns:
            Quantidade de notas
        """
        try:
            response = self.db.table(self.table_name)\
                .select("id", count="exact")\
                .eq("empresa_id", empresa_id)\
                .execute()
            
            return response.count if response.count else 0
            
        except Exception as e:
            logger.error(f"Erro ao contar notas da empresa {empresa_id}: {e}")
            return 0
