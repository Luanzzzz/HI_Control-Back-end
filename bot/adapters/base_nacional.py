"""
Adapter para Base Nacional de NFS-e (ABRASF)

Seguindo padrões MCP Tool Pattern:
- Interface bem definida
- Error handling robusto
- Logging estruturado

Reutiliza lógica do backend/app/services/nfse/sistema_nacional.py
"""

import httpx
from datetime import date
from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)


# ============================================
# EXCEÇÕES (Padrões MCP)
# ============================================

class NFSeException(Exception):
    """Exceção base para erros NFS-e."""
    pass


class NFSeAuthException(NFSeException):
    """Erro de autenticação."""
    pass


class NFSeSearchException(NFSeException):
    """Erro na busca."""
    pass


# ============================================
# ADAPTER BASE NACIONAL
# ============================================

class BaseNacionalAdapter:
    """
    Adapter para Sistema Nacional de NFS-e (ABRASF).
    
    Seguindo padrão MCP Tool: interface bem definida e error handling robusto.
    
    Portal: https://www.gov.br/nfse
    Cobre aproximadamente 3.000+ municípios brasileiros.
    """
    
    SISTEMA_NOME = "Sistema Nacional"
    
    # URLs oficiais
    URL_PRODUCAO = "https://sefin.nfse.gov.br/sefinnacional"
    URL_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"
    
    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        """
        Args:
            credentials: Dicionário com credenciais (usuario, senha, cnpj)
            homologacao: Se True, usa ambiente de homologação
        """
        self.credentials = credentials
        self.homologacao = homologacao
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.token: Optional[str] = None
    
    def limpar_cnpj(self, cnpj: str) -> str:
        """Remove formatação do CNPJ."""
        return re.sub(r"[^0-9]", "", cnpj)
    
    def validar_cnpj(self, cnpj: str) -> bool:
        """Valida formato do CNPJ."""
        cnpj_limpo = self.limpar_cnpj(cnpj)
        return len(cnpj_limpo) == 14
    
    async def autenticar(self) -> str:
        """
        Autentica no Sistema Nacional de NFS-e.
        
        Returns:
            Token de autenticação
            
        Raises:
            NFSeAuthException: Falha na autenticação
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                payload = {
                    "login": self.credentials.get("usuario"),
                    "senha": self.credentials.get("senha"),
                }
                
                cnpj = self.credentials.get("cnpj")
                if cnpj:
                    payload["cnpj"] = self.limpar_cnpj(cnpj)
                
                response = await client.post(
                    f"{self.base_url}/autenticar",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 401:
                    raise NFSeAuthException(
                        "Credenciais inválidas para o Sistema Nacional de NFS-e"
                    )
                
                if response.status_code != 200:
                    raise NFSeAuthException(
                        f"Falha na autenticação: HTTP {response.status_code}"
                    )
                
                data = response.json()
                self.token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("chaveAutenticacao")
                )
                
                if not self.token:
                    raise NFSeAuthException(
                        "Resposta de autenticação não contém token válido"
                    )
                
                logger.info(f"✅ Autenticado no Sistema Nacional")
                return self.token
                
        except NFSeAuthException:
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Timeout na autenticação: {e}")
            raise NFSeAuthException("Timeout ao conectar com Sistema Nacional")
        except httpx.HTTPError as e:
            logger.error(f"Erro HTTP na autenticação: {e}")
            raise NFSeAuthException(f"Erro de rede: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado na autenticação: {e}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {e}")
    
    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100
    ) -> List[Dict]:
        """
        Busca NFS-e no Sistema Nacional por CNPJ e período.
        
        Args:
            cnpj: CNPJ do prestador
            data_inicio: Data inicial
            data_fim: Data final
            limite: Limite de notas
            
        Returns:
            Lista de notas no formato padrão
            
        Raises:
            NFSeSearchException: Erro na busca
        """
        if not self.token:
            await self.autenticar()
        
        cnpj_limpo = self.limpar_cnpj(cnpj)
        if not self.validar_cnpj(cnpj_limpo):
            raise NFSeSearchException(f"CNPJ inválido: {cnpj}")
        
        try:
            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                params = {
                    "cnpjPrestador": cnpj_limpo,
                    "dataInicial": data_inicio.strftime("%Y-%m-%d"),
                    "dataFinal": data_fim.strftime("%Y-%m-%d"),
                    "pagina": 1,
                    "itensPorPagina": limite,
                }
                
                response = await client.get(
                    f"{self.base_url}/nfse/consultar",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                    params=params,
                )
                
                # Token expirado - reautenticar
                if response.status_code == 401:
                    logger.warning("Token expirado, reautenticando...")
                    self.token = None
                    await self.autenticar()
                    return await self.buscar_notas(cnpj, data_inicio, data_fim, limite)
                
                if response.status_code == 404:
                    logger.info(f"Nenhuma NFS-e encontrada para CNPJ {cnpj_limpo}")
                    return []
                
                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca: HTTP {response.status_code}"
                    )
                
                data = response.json()
                notas_processadas = self.processar_resposta(data)
                
                logger.info(
                    f"✅ {len(notas_processadas)} NFS-e encontradas para CNPJ {cnpj_limpo}"
                )
                return notas_processadas
                
        except NFSeSearchException:
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Timeout na busca: {e}")
            raise NFSeSearchException("Timeout ao buscar NFS-e")
        except httpx.HTTPError as e:
            logger.error(f"Erro HTTP na busca: {e}")
            raise NFSeSearchException(f"Erro de rede: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado na busca: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro inesperado: {e}")
    
    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Processa resposta do Sistema Nacional para formato padrão.
        
        Args:
            resposta: Resposta bruta da API
            
        Returns:
            Lista de notas no formato padrão
        """
        notas = []
        
        # O Sistema Nacional pode retornar em diferentes chaves
        lista_notas = (
            resposta.get("nfse")
            or resposta.get("notas")
            or resposta.get("listaNfse")
            or resposta.get("compNfse")
            or []
        )
        
        for nota_raw in lista_notas:
            try:
                prestador = nota_raw.get("prestador") or {}
                if isinstance(prestador, str):
                    prestador = {}
                
                tomador = nota_raw.get("tomador") or {}
                if isinstance(tomador, str):
                    tomador = {}
                
                valores = nota_raw.get("valores") or nota_raw.get("servico") or {}
                if isinstance(valores, str):
                    valores = {}
                
                # Gerar chave única para NFS-e
                municipio = str(nota_raw.get("codigoMunicipio", ""))
                numero = str(nota_raw.get("numero", ""))
                codigo_verif = str(nota_raw.get("codigoVerificacao", ""))
                chave_acesso = f"NFSE-{municipio}-{numero}-{codigo_verif}"
                
                nota = {
                    "tipo": "NFS-e",
                    "numero": str(nota_raw.get("numero") or nota_raw.get("numeroNfse") or ""),
                    "serie": str(nota_raw.get("serie") or ""),
                    "chave_acesso": chave_acesso,
                    "data_emissao": (
                        nota_raw.get("dataEmissao")
                        or nota_raw.get("data_emissao")
                        or nota_raw.get("dhEmissao")
                    ),
                    "valor_total": float(
                        nota_raw.get("valorTotal")
                        or nota_raw.get("valor_total")
                        or valores.get("valorServicos")
                        or valores.get("valorTotal")
                        or 0
                    ),
                    "valor_servicos": float(
                        valores.get("valorServicos")
                        or nota_raw.get("valorServicos")
                        or 0
                    ),
                    "valor_iss": float(
                        valores.get("valorIss")
                        or nota_raw.get("valorIss")
                        or 0
                    ),
                    "aliquota_iss": float(
                        valores.get("aliquota")
                        or nota_raw.get("aliquotaIss")
                        or 0
                    ),
                    "cnpj_prestador": self.limpar_cnpj(
                        str(
                            prestador.get("cnpj")
                            or nota_raw.get("cnpjPrestador")
                            or ""
                        )
                    ),
                    "prestador_nome": (
                        prestador.get("razaoSocial")
                        or prestador.get("nome")
                        or nota_raw.get("razaoSocialPrestador")
                        or ""
                    ),
                    "cnpj_tomador": self.limpar_cnpj(
                        str(
                            tomador.get("cnpj")
                            or nota_raw.get("cnpjTomador")
                            or ""
                        )
                    ),
                    "tomador_nome": (
                        tomador.get("razaoSocial")
                        or tomador.get("nome")
                        or nota_raw.get("razaoSocialTomador")
                        or ""
                    ),
                    "descricao_servico": (
                        nota_raw.get("discriminacao")
                        or nota_raw.get("descricaoServico")
                        or valores.get("discriminacao")
                        or ""
                    ),
                    "codigo_servico": (
                        nota_raw.get("codigoServico")
                        or nota_raw.get("itemListaServico")
                        or valores.get("itemListaServico")
                        or ""
                    ),
                    "codigo_verificacao": str(nota_raw.get("codigoVerificacao") or ""),
                    "link_visualizacao": nota_raw.get("linkVisualizacao", ""),
                    "xml_content": nota_raw.get("xml") or nota_raw.get("xmlNfse") or "",
                    "municipio_codigo": str(
                        nota_raw.get("codigoMunicipio")
                        or prestador.get("codigoMunicipio")
                        or ""
                    ),
                    "municipio_nome": (
                        nota_raw.get("municipioNome")
                        or prestador.get("municipio")
                        or ""
                    ),
                    "status": (
                        nota_raw.get("situacao")
                        or nota_raw.get("status")
                        or "Autorizada"
                    ),
                }
                
                notas.append(nota)
                
            except Exception as e:
                logger.warning(
                    f"⚠️ Erro ao processar nota {nota_raw.get('numero', '?')}: {e}"
                )
                continue
        
        return notas
