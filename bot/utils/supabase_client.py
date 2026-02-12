"""
Cliente Supabase para o Bot

Seguindo padrões MCP Resource Pattern:
- Acesso centralizado a recursos (dados)
- Error handling robusto
- Logging estruturado
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging
from supabase import create_client, Client

from bot.config import config

logger = logging.getLogger(__name__)


class SupabaseResource:
    """
    Cliente Supabase seguindo padrão MCP Resource.
    
    Gerencia acesso a recursos (dados) do Supabase de forma centralizada.
    """
    
    _client: Optional[Client] = None
    
    @classmethod
    def get_client(cls) -> Client:
        """
        Retorna cliente Supabase singleton.
        
        Returns:
            Cliente Supabase configurado
            
        Raises:
            ValueError: Se configurações estiverem inválidas
        """
        if cls._client is None:
            config.validate_supabase()
            cls._client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
            logger.info("✅ Cliente Supabase inicializado")
        return cls._client
    
    @classmethod
    def buscar_empresas_ativas(cls, apenas_com_certificado: bool = True) -> List[Dict]:
        """
        Busca empresas ativas no sistema.
        
        Args:
            apenas_com_certificado: Se True, retorna apenas empresas com certificado A1 valido.
                                   Se False, retorna todas as ativas.
        
        Returns:
            Lista de empresas com dados completos
        """
        try:
            client = cls.get_client()
            
            response = client.table("empresas")\
                .select("*")\
                .eq("ativa", True)\
                .execute()
            
            todas_empresas = response.data or []
            logger.info(f"📊 {len(todas_empresas)} empresas ativas encontradas")
            
            if not apenas_com_certificado:
                return todas_empresas
            
            # Filtrar apenas empresas com certificado valido (nao expirado)
            agora = datetime.now()
            empresas_validas = []
            empresas_sem_cert = []
            empresas_cert_expirado = []
            
            for emp in todas_empresas:
                cert_validade = emp.get("certificado_validade")
                cert_a1 = emp.get("certificado_a1")
                
                if not cert_a1 and not cert_validade:
                    empresas_sem_cert.append(emp.get("razao_social", emp.get("id")))
                    continue
                
                if cert_validade:
                    try:
                        validade_dt = datetime.fromisoformat(
                            str(cert_validade).replace("Z", "+00:00")
                        )
                        # Remover timezone para comparacao simples
                        if validade_dt.tzinfo:
                            validade_naive = validade_dt.replace(tzinfo=None)
                        else:
                            validade_naive = validade_dt
                        
                        if validade_naive < agora:
                            empresas_cert_expirado.append(
                                emp.get("razao_social", emp.get("id"))
                            )
                            continue
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"⚠️ Erro ao parsear validade do certificado de "
                            f"{emp.get('razao_social')}: {e}"
                        )
                
                empresas_validas.append(emp)
            
            if empresas_sem_cert:
                logger.warning(
                    f"⚠️ {len(empresas_sem_cert)} empresas sem certificado: "
                    f"{', '.join(empresas_sem_cert[:5])}"
                )
            
            if empresas_cert_expirado:
                logger.warning(
                    f"⚠️ {len(empresas_cert_expirado)} empresas com certificado expirado: "
                    f"{', '.join(empresas_cert_expirado[:5])}"
                )
            
            logger.info(
                f"✅ {len(empresas_validas)} empresas com certificado valido "
                f"(de {len(todas_empresas)} ativas)"
            )
            
            return empresas_validas
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar empresas: {e}", exc_info=True)
            return []
    
    @classmethod
    def buscar_credenciais_nfse(cls, empresa_id: str, municipio_codigo: str) -> Optional[Dict]:
        """
        Busca credenciais NFS-e de uma empresa.
        
        Args:
            empresa_id: UUID da empresa
            municipio_codigo: Código IBGE do município
            
        Returns:
            Dicionário com credenciais ou None
        """
        try:
            client = cls.get_client()
            
            response = client.table("credenciais_nfse")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .eq("municipio_codigo", municipio_codigo)\
                .maybe_single()\
                .execute()
            
            if response.data:
                logger.debug(f"✅ Credenciais NFS-e encontradas para empresa {empresa_id}")
                return response.data
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar credenciais NFS-e: {e}", exc_info=True)
            return None
    
    @classmethod
    def salvar_nota(cls, nota: Dict, empresa_id: str) -> bool:
        """
        Salva nota no banco (UPSERT por chave_acesso).
        
        Seguindo padrão MCP: operação idempotente e segura.
        
        Args:
            nota: Dicionário com dados da nota
            empresa_id: UUID da empresa
            
        Returns:
            True se salvou com sucesso, False caso contrário
        """
        try:
            client = cls.get_client()
            
            # Preparar dados no formato do banco (usando nomes de colunas do schema)
            nota_data = {
                "empresa_id": empresa_id,
                "chave_acesso": nota.get("chave_acesso", ""),
                "numero_nf": nota.get("numero") or nota.get("numero_nf", ""),
                "serie": nota.get("serie", "ÚNICA"),
                "tipo_nf": nota.get("tipo") or nota.get("tipo_nf", "NFS-e"),
                "data_emissao": nota.get("data_emissao"),
                "valor_total": float(nota.get("valor_total", 0)),
                "cnpj_emitente": (
                    nota.get("cnpj_prestador")
                    or nota.get("prestador_cnpj")
                    or nota.get("cnpj_emitente", "")
                ),
                "nome_emitente": (
                    nota.get("prestador_nome")
                    or nota.get("nome_emitente", "")
                ),
                "cnpj_destinatario": (
                    nota.get("cnpj_tomador")
                    or nota.get("tomador_cnpj")
                    or nota.get("cnpj_destinatario", "")
                ),
                "nome_destinatario": (
                    nota.get("tomador_nome")
                    or nota.get("nome_destinatario", "")
                ),
                "xml_url": nota.get("xml_url") or nota.get("xml_content", ""),
                "situacao": nota.get("status") or nota.get("situacao", "autorizada"),
                "municipio_codigo": nota.get("municipio_codigo", ""),
                "codigo_verificacao": nota.get("codigo_verificacao", ""),
                "link_visualizacao": nota.get("link_visualizacao", ""),
                "descricao_servico": nota.get("descricao_servico", ""),
                "codigo_servico": nota.get("codigo_servico", ""),
                "valor_iss": float(nota.get("valor_iss", 0)),
                "aliquota_iss": float(nota.get("aliquota_iss", 0)),
            }
            
            # UPSERT (insert or update) - idempotente
            response = client.table("notas_fiscais")\
                .upsert(nota_data, on_conflict="chave_acesso")\
                .execute()
            
            logger.debug(f"✅ Nota {nota.get('numero')} salva/atualizada")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Erro ao salvar nota {nota.get('numero', '?')}: {e}",
                exc_info=True
            )
            return False
    
    @classmethod
    def salvar_lote_notas(cls, notas: List[Dict], empresa_id: str) -> int:
        """
        Salva múltiplas notas em lote.
        
        Args:
            notas: Lista de notas
            empresa_id: UUID da empresa
            
        Returns:
            Quantidade salva com sucesso
        """
        salvos = 0
        
        for nota in notas:
            if cls.salvar_nota(nota, empresa_id):
                salvos += 1
        
        logger.info(f"💾 {salvos}/{len(notas)} notas salvas para empresa {empresa_id}")
        return salvos
    
    @classmethod
    def buscar_credenciais_nfse_por_empresa(cls, empresa_id: str) -> Optional[Dict]:
        """
        Busca qualquer credencial ativa da empresa (fallback sem município).

        Usado quando a empresa não tem municipio_codigo configurado.

        Args:
            empresa_id: UUID da empresa

        Returns:
            Dicionário com credenciais ou None
        """
        try:
            client = cls.get_client()

            response = client.table("credenciais_nfse")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .eq("ativo", True)\
                .limit(1)\
                .execute()

            if response.data:
                logger.info(f"✅ Credencial encontrada (fallback): empresa={empresa_id}")
                return response.data[0]

            logger.warning(f"⚠️ Nenhuma credencial ativa: empresa={empresa_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Erro ao buscar credenciais: {e}")
            return None

    @classmethod
    def verificar_nota_existe(cls, chave_acesso: str) -> bool:
        """
        Verifica se nota já existe no banco.

        Args:
            chave_acesso: Chave única da nota

        Returns:
            True se nota existe, False caso contrário
        """
        try:
            client = cls.get_client()

            response = client.table("notas_fiscais")\
                .select("id")\
                .eq("chave_acesso", chave_acesso)\
                .limit(1)\
                .execute()

            return len(response.data or []) > 0

        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar nota {chave_acesso}: {e}")
            return False
