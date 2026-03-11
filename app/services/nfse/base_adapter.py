"""
Interface base para adapters de NFS-e.

Cada município/sistema implementa esta interface para padronizar:
- Autenticação nas APIs municipais
- Busca de notas fiscais de serviço
- Processamento de respostas para formato padrão Hi-Control
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)


# ============================================
# EXCEÇÕES CUSTOMIZADAS
# ============================================

class NFSeException(Exception):
    """Exceção base para erros NFS-e."""

    def __init__(self, codigo: str, mensagem: str, detalhes: Optional[str] = None):
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes
        super().__init__(f"[{codigo}] {mensagem}")


class NFSeAuthException(NFSeException):
    """Erro de autenticação na API municipal."""

    def __init__(self, mensagem: str, detalhes: Optional[str] = None):
        super().__init__("NFSE_AUTH_ERROR", mensagem, detalhes)


class NFSeSearchException(NFSeException):
    """Erro na busca de notas fiscais."""

    def __init__(self, mensagem: str, detalhes: Optional[str] = None):
        super().__init__("NFSE_SEARCH_ERROR", mensagem, detalhes)


class NFSeConfigException(NFSeException):
    """Erro de configuração (credenciais ausentes, URL inválida, etc)."""

    def __init__(self, mensagem: str, detalhes: Optional[str] = None):
        super().__init__("NFSE_CONFIG_ERROR", mensagem, detalhes)


# ============================================
# FORMATO PADRÃO DE NOTA
# ============================================

NOTA_PADRAO_CAMPOS = {
    "tipo": "NFS-e",
    "numero": "",
    "serie": "",
    "data_emissao": None,
    "valor_total": 0.0,
    "valor_servicos": 0.0,
    "valor_deducoes": 0.0,
    "valor_iss": 0.0,
    "aliquota_iss": 0.0,
    "cnpj_prestador": "",
    "prestador_nome": "",
    "cnpj_tomador": "",
    "tomador_nome": "",
    "descricao_servico": "",
    "codigo_servico": "",
    "codigo_verificacao": "",
    "link_visualizacao": "",
    "xml_content": "",
    "municipio_codigo": "",
    "municipio_nome": "",
    "status": "Autorizada",
}


# ============================================
# INTERFACE BASE
# ============================================

class BaseNFSeAdapter(ABC):
    """
    Interface base para adapters de NFS-e.
    Cada município/sistema implementa esta interface.
    """

    # Nome do sistema para logs
    SISTEMA_NOME: str = "Base"

    def __init__(self, credentials: Dict[str, str]):
        """
        Args:
            credentials: Dicionário com credenciais (usuario, senha, token, cnpj, etc.)
        """
        self.credentials = credentials
        self.token: Optional[str] = None

    @abstractmethod
    async def autenticar(self) -> str:
        """
        Realiza autenticação na API municipal.

        Returns:
            Token de autenticação

        Raises:
            NFSeAuthException: Erro na autenticação
        """
        pass

    @abstractmethod
    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100
    ) -> List[Dict]:
        """
        Busca notas fiscais emitidas por CNPJ no período.

        Args:
            cnpj: CNPJ do prestador (sem pontuação)
            data_inicio: Data inicial da consulta
            data_fim: Data final da consulta
            limite: Limite de notas por consulta

        Returns:
            Lista de dicionários com dados das notas no formato padrão

        Raises:
            NFSeSearchException: Erro na busca
        """
        pass

    @abstractmethod
    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Processa resposta da API para formato padrão Hi-Control.

        Args:
            resposta: Resposta bruta da API

        Returns:
            Lista de notas no formato padrão
        """
        pass

    # ============================================
    # MÉTODOS UTILITÁRIOS (COMPARTILHADOS)
    # ============================================

    def limpar_cnpj(self, cnpj: str) -> str:
        """Remove formatação do CNPJ, mantendo apenas dígitos."""
        return re.sub(r"[^0-9]", "", cnpj)

    def validar_cnpj(self, cnpj: str) -> bool:
        """
        Valida formato do CNPJ (apenas formato, não dígito verificador).

        Args:
            cnpj: CNPJ com ou sem formatação

        Returns:
            True se CNPJ tem 14 dígitos numéricos
        """
        cnpj_limpo = self.limpar_cnpj(cnpj)
        return len(cnpj_limpo) == 14

    def criar_nota_padrao(self, **kwargs) -> Dict:
        """
        Cria dicionário de nota no formato padrão Hi-Control.
        Preenche campos não fornecidos com valores padrão.

        Args:
            **kwargs: Campos da nota

        Returns:
            Dicionário com todos os campos padrão preenchidos
        """
        nota = NOTA_PADRAO_CAMPOS.copy()
        nota.update(kwargs)
        return nota

    def log_info(self, msg: str):
        """Log informativo com prefixo do sistema."""
        logger.info(f"[NFS-e {self.SISTEMA_NOME}] {msg}")

    def log_warning(self, msg: str):
        """Log de aviso com prefixo do sistema."""
        logger.warning(f"[NFS-e {self.SISTEMA_NOME}] {msg}")

    def log_error(self, msg: str, exc_info: bool = False):
        """Log de erro com prefixo do sistema."""
        logger.error(f"[NFS-e {self.SISTEMA_NOME}] {msg}", exc_info=exc_info)
