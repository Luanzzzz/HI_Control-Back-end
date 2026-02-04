"""
Serviço de cache para consultas de notas fiscais.

Implementa cache no Supabase com TTL de 24 horas.
Reduz consultas à SEFAZ e melhora tempo de resposta.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.db.supabase_client import supabase_admin
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Serviço de cache para consultas SEFAZ.
    
    Armazena resultados no Supabase com TTL de 24h.
    Utiliza hash MD5 dos filtros como chave para evitar duplicação.
    """
    
    def __init__(self):
        self.db = supabase_admin
        self.default_ttl_hours = 24
    
    def gerar_chave_cache(
        self, 
        empresa_id: str, 
        filtros: Dict[str, Any]
    ) -> str:
        """
        Gera chave única para cache baseada em empresa + filtros.
        
        Args:
            empresa_id: ID da empresa
            filtros: Dicionário com filtros da busca
        
        Returns:
            Chave no formato: {empresa_id}:{hash_filtros}:{data}
        
        Exemplo:
            "550e8400-e29b-41d4-a716-446655440000:a3f2b1:2025-02-04"
        """
        # Normalizar filtros (ordenar keys para consistência)
        filtros_normalizados = {
            k: v for k, v in sorted(filtros.items()) 
            if v is not None and v != ""
        }
        
        # Gerar hash MD5
        filtros_json = json.dumps(filtros_normalizados, sort_keys=True)
        hash_filtros = hashlib.md5(filtros_json.encode()).hexdigest()[:6]
        
        # Data atual (para agrupar cache por dia)
        data_atual = datetime.now().strftime("%Y-%m-%d")
        
        return f"{empresa_id}:{hash_filtros}:{data_atual}"
    
    async def buscar(
        self, 
        chave: str
    ) -> Optional[Dict[str, Any]]:
        """
        Busca dados do cache (ignora expirados).
        
        Args:
            chave: Chave de cache gerada por gerar_chave_cache()
        
        Returns:
            Dict com dados se encontrado e válido, None caso contrário
        """
        try:
            resultado = self.db.table("cache_notas_fiscais")\
                .select("dados, created_at, quantidade_notas")\
                .eq("chave_busca", chave)\
                .gt("expires_at", datetime.now().isoformat())\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            
            if resultado.data and len(resultado.data) > 0:
                cache_entry = resultado.data[0]
                logger.info(f"✅ Cache HIT para chave {chave[:20]}...")
                return {
                    "dados": cache_entry["dados"],
                    "cached_at": cache_entry["created_at"],
                    "quantidade": cache_entry.get("quantidade_notas", 0)
                }
            
            logger.info(f"❌ Cache MISS para chave {chave[:20]}...")
            return None
            
        except Exception as e:
            logger.error(f"Erro ao buscar cache: {e}")
            return None
    
    async def salvar(
        self,
        empresa_id: str,
        chave: str,
        dados: Dict[str, Any],
        ttl_hours: int = None
    ) -> bool:
        """
        Salva dados no cache com TTL.
        
        Args:
            empresa_id: ID da empresa
            chave: Chave de cache
            dados: Dados a serem cacheados
            ttl_hours: Tempo de vida em horas (default: 24)
        
        Returns:
            True se salvo com sucesso
        """
        if ttl_hours is None:
            ttl_hours = self.default_ttl_hours
        
        try:
            expires_at = datetime.now() + timedelta(hours=ttl_hours)
            
            # Calcular quantidade de notas
            quantidade_notas = 0
            if isinstance(dados, dict):
                if "notas" in dados:
                    quantidade_notas = len(dados.get("notas", []))
                elif "quantidade" in dados:
                    quantidade_notas = dados.get("quantidade", 0)
            
            # Upsert para evitar duplicatas
            self.db.table("cache_notas_fiscais").upsert({
                "empresa_id": empresa_id,
                "chave_busca": chave,
                "dados": dados,
                "fonte": "sefaz",
                "quantidade_notas": quantidade_notas,
                "expires_at": expires_at.isoformat(),
                "created_at": datetime.now().isoformat()
            }, on_conflict="empresa_id,chave_busca").execute()
            
            logger.info(
                f"💾 Cache salvo: {chave[:20]}... | "
                f"{quantidade_notas} notas | "
                f"Expira em {ttl_hours}h"
            )
            return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
            return False
    
    async def invalidar(
        self, 
        empresa_id: str = None,
        chave: str = None
    ) -> int:
        """
        Invalida cache (força nova consulta à SEFAZ).
        
        Args:
            empresa_id: ID da empresa (invalida todo cache da empresa)
            chave: Chave específica (invalida apenas essa chave)
        
        Returns:
            Número de registros invalidados
        """
        try:
            query = self.db.table("cache_notas_fiscais")
            
            if chave:
                query = query.eq("chave_busca", chave)
            elif empresa_id:
                query = query.eq("empresa_id", empresa_id)
            else:
                logger.warning("invalidar() chamado sem parâmetros")
                return 0
            
            # Definir expires_at para o passado (invalidar)
            resultado = query.update({
                "expires_at": datetime.now().isoformat()
            }).execute()
            
            count = len(resultado.data) if resultado.data else 0
            logger.info(f"🗑️ Cache invalidado: {count} registros")
            return count
            
        except Exception as e:
            logger.error(f"Erro ao invalidar cache: {e}")
            return 0
    
    async def limpar_expirados(self) -> int:
        """
        Remove registros de cache expirados.
        Chamado automaticamente pelo job de limpeza.
        
        Returns:
            Número de registros removidos
        """
        try:
            resultado = self.db.table("cache_notas_fiscais")\
                .delete()\
                .lt("expires_at", datetime.now().isoformat())\
                .execute()
            
            count = len(resultado.data) if resultado.data else 0
            logger.info(f"🧹 Limpeza de cache: {count} registros expirados removidos")
            return count
            
        except Exception as e:
            logger.error(f"Erro ao limpar cache expirado: {e}")
            return 0


# Instância singleton
cache_service = CacheService()
