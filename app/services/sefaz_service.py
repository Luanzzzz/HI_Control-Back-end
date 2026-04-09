"""
Serviço para comunicação com SEFAZ (Secretaria da Fazenda).

Funcionalidades:
- Autorização de NF-e/NFC-e
- Consulta de status de NF-e
- Cancelamento de NF-e
- Inutilização de numeração
- Integração com PyNFE

Ambiente: Homologação (decisão do usuário)
Cache: In-memory com TTL de 5 minutos (decisão do usuário)
"""
import base64
import gzip
import html
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, List
from decimal import Decimal

try:
    from lxml import etree
except ImportError:
    etree = None  # Será necessário em produção

try:
    from nfe.core import NFe
    from nfe.core import NotaFiscal as PyNFeNotaFiscal
    from nfe.core.emissor import Emitente
    from nfe.core.destinatario import Destinatario
    from nfe.core.produto import Produto
    from nfe.core.transporte import Transporte
    from nfe.core.cobranca import Cobranca, Duplicata
except ImportError:
    NFe = None  # Mock para desenvolvimento

from app.core.sefaz_config import (
    AMBIENTE_PADRAO,
    SEFAZ_ENDPOINTS_HOMOLOGACAO,
    SEFAZ_ENDPOINTS_PRODUCAO,
    DISTRIBUICAO_DFE_ENDPOINTS,
    TIMEOUT_SEFAZ,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF,
    CACHE_TTL_SECONDS,
    SEFAZ_STATUS_CODES,
    _query_cache,
    obter_mensagem_sefaz,
    obter_endpoints_por_ambiente,
    obter_endpoint_distribuicao,
)
from app.core.config import settings
from app.services.certificado_service import certificado_service
from app.models.nfe_completa import (
    NotaFiscalCompletaCreate,
    SefazResponseModel,
    SefazRejeicao,
)
from app.adapters.pynfe_adapter import PyNFeAdapter

logger = logging.getLogger(__name__)

# ============================================
# EXCEÇÕES CUSTOMIZADAS
# ============================================

class SefazException(Exception):
    """Erro base para comunicação com SEFAZ"""
    def __init__(self, codigo: str, mensagem: str, campo_erro: Optional[str] = None):
        self.codigo = codigo
        self.mensagem = mensagem
        self.campo_erro = campo_erro
        super().__init__(f"[{codigo}] {mensagem}")


class SefazTimeoutError(SefazException):
    """Timeout ao comunicar com SEFAZ"""
    pass


class SefazValidationError(SefazException):
    """Erro de validação de dados"""
    pass


class SefazAuthorizationError(SefazException):
    """Erro de autenticação/certificado"""
    pass


# ============================================
# SERVIÇO SEFAZ
# ============================================

class SefazService:
    """
    Serviço para comunicação com SEFAZ.

    Implementa cache in-memory conforme decisão do usuário.
    Ambiente fixo: homologação.
    """

    def __init__(self):
        """Inicializa serviço SEFAZ"""
        ambiente_configurado = (
            (getattr(settings, "SEFAZ_AMBIENTE", None) or AMBIENTE_PADRAO or "homologacao")
            .strip()
            .lower()
        )
        self.ambiente = (
            ambiente_configurado
            if ambiente_configurado in {"producao", "homologacao"}
            else "homologacao"
        )
        self._cache = _query_cache
        logger.info(f"SefazService inicializado - Ambiente: {self.ambiente}")

    # ============================================
    # AUTORIZAÇÃO DE NF-E
    # ============================================

    def autorizar_nfe(
        self,
        nfe_data: NotaFiscalCompletaCreate,
        cert_bytes: bytes,
        senha_cert: str,
        empresa_cnpj: str,
        empresa_ie: str,
        empresa_razao_social: str,
        empresa_uf: str,
        empresa_id: Optional[str] = None,
    ) -> SefazResponseModel:
        """
        Autoriza NF-e junto à SEFAZ.

        Args:
            nfe_data: Dados completos da NF-e
            cert_bytes: Certificado digital em bytes
            senha_cert: Senha do certificado
            empresa_cnpj: CNPJ do emitente
            empresa_ie: Inscrição Estadual
            empresa_razao_social: Razão social
            empresa_uf: UF do emitente
            empresa_id: UUID da empresa (para auditoria e proteção)

        Returns:
            SefazResponseModel com resultado da autorização

        Raises:
            SefazException: Em caso de erro
            EmissionBlockedError: Se emissão em produção bloqueada
        """
        # PROTEÇÃO: Verificar permissão de emissão em produção
        from app.utils.emission_guard import verificar_permissao_emissao
        verificar_permissao_emissao(
            empresa_id=empresa_id or empresa_cnpj,
            tipo_documento="NFe"
        )

        logger.info(
            f"Autorizando NF-e {nfe_data.numero_nf} série {nfe_data.serie} "
            f"para empresa {empresa_cnpj}"
        )

        # Validar PyNFE disponível
        if NFe is None:
            raise SefazException(
                "999",
                "PyNFE não instalado. Execute: pip install PyNFe",
                None
            )

        try:
            # 1. Obter URL do SEFAZ
            url_autorizacao = self._obter_url_sefaz(empresa_uf, "autorizacao")

            # 2. Construir XML usando PyNFE
            xml_nfe = self._construir_xml_nfe(
                nfe_data,
                empresa_cnpj,
                empresa_ie,
                empresa_razao_social,
                empresa_uf,
            )

            # 2.5. VALIDAR XML CONTRA XSD ANTES DE ASSINAR
            self._validar_xml_antes_assinatura(xml_nfe, nfe_data.modelo)

            # 3. Assinar XML com certificado
            xml_assinado = self._assinar_xml(xml_nfe, cert_bytes, senha_cert)

            # 4. Enviar para SEFAZ
            response_xml = self._enviar_para_sefaz(
                url_autorizacao,
                xml_assinado,
                "autorizacao"
            )

            # 5. Parsear resposta
            sefaz_response = self._parsear_resposta_autorizacao(response_xml, empresa_uf)

            # 6. Log da operação
            self._log_operacao(
                "autorizacao",
                empresa_cnpj,
                nfe_data.numero_nf,
                nfe_data.serie,
                xml_assinado,
                response_xml,
                sefaz_response.status_codigo,
            )

            logger.info(
                f"Autorização NF-e {nfe_data.numero_nf}: "
                f"Status {sefaz_response.status_codigo} - {sefaz_response.status_descricao}"
            )

            return sefaz_response

        except SefazException:
            raise
        except Exception as e:
            logger.error(f"Erro ao autorizar NF-e: {e}", exc_info=True)
            raise SefazException("999", f"Erro interno: {str(e)}", None)

    # ============================================
    # CONSULTA DE NF-E
    # ============================================

    def consultar_nfe(
        self,
        chave_acesso: str,
        empresa_uf: str,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> SefazResponseModel:
        """
        Consulta status de NF-e por chave de acesso.

        Args:
            chave_acesso: Chave de acesso de 44 dígitos
            empresa_uf: UF do emitente
            cert_bytes: Certificado digital
            senha_cert: Senha do certificado

        Returns:
            SefazResponseModel com status da NF-e

        Note:
            Usa cache in-memory com TTL de 5 minutos
        """
        logger.info(f"Consultando NF-e: {chave_acesso}")

        # Verificar cache
        cached = self._get_cache(chave_acesso)
        if cached:
            logger.info(f"Consulta em cache para {chave_acesso}")
            return cached

        try:
            # 1. Obter URL
            url_consulta = self._obter_url_sefaz(empresa_uf, "consulta")

            # 2. Construir XML de consulta
            xml_consulta = self._construir_xml_consulta(chave_acesso)

            # 3. Assinar
            xml_assinado = self._assinar_xml(xml_consulta, cert_bytes, senha_cert)

            # 4. Enviar
            response_xml = self._enviar_para_sefaz(
                url_consulta,
                xml_assinado,
                "consulta"
            )

            # 5. Parsear
            sefaz_response = self._parsear_resposta_consulta(response_xml)

            # 6. Cache
            self._set_cache(chave_acesso, sefaz_response)

            # 7. Log
            self._log_operacao(
                "consulta",
                chave_acesso[:14],  # CNPJ
                chave_acesso[25:34],  # Número
                chave_acesso[22:25],  # Série
                xml_assinado,
                response_xml,
                sefaz_response.status_codigo,
            )

            return sefaz_response

        except SefazException:
            raise
        except Exception as e:
            logger.error(f"Erro ao consultar NF-e: {e}", exc_info=True)
            raise SefazException("999", f"Erro interno: {str(e)}", None)

    # ============================================
    # CANCELAMENTO DE NF-E
    # ============================================

    def cancelar_nfe(
        self,
        chave_acesso: str,
        protocolo: str,
        motivo: str,
        empresa_cnpj: str,
        empresa_uf: str,
        cert_bytes: bytes,
        senha_cert: str,
        data_autorizacao: datetime,
    ) -> SefazResponseModel:
        """
        Cancela NF-e autorizada.

        Args:
            chave_acesso: Chave de acesso
            protocolo: Protocolo de autorização
            motivo: Motivo do cancelamento (mín 15 caracteres)
            empresa_cnpj: CNPJ emitente
            empresa_uf: UF emitente
            cert_bytes: Certificado
            senha_cert: Senha
            data_autorizacao: Data/hora da autorização

        Returns:
            SefazResponseModel

        Raises:
            SefazValidationError: Se condições não atendidas
        """
        logger.info(f"Cancelando NF-e: {chave_acesso}")

        # Validar condições de cancelamento
        self._validar_cancelamento(data_autorizacao, motivo)

        try:
            # 1. Obter URL
            url_cancelamento = self._obter_url_sefaz(empresa_uf, "cancelamento")

            # 2. Construir evento de cancelamento
            xml_cancelamento = self._construir_xml_cancelamento(
                chave_acesso,
                protocolo,
                motivo,
                empresa_cnpj,
            )

            # 3. Assinar
            xml_assinado = self._assinar_xml(xml_cancelamento, cert_bytes, senha_cert)

            # 4. Enviar
            response_xml = self._enviar_para_sefaz(
                url_cancelamento,
                xml_assinado,
                "cancelamento"
            )

            # 5. Parsear
            sefaz_response = self._parsear_resposta_cancelamento(response_xml)

            # 6. Invalidar cache
            self._invalidate_cache(chave_acesso)

            # 7. Log
            self._log_operacao(
                "cancelamento",
                empresa_cnpj,
                chave_acesso[25:34],
                chave_acesso[22:25],
                xml_assinado,
                response_xml,
                sefaz_response.status_codigo,
            )

            return sefaz_response

        except SefazException:
            raise
        except Exception as e:
            logger.error(f"Erro ao cancelar NF-e: {e}", exc_info=True)
            raise SefazException("999", f"Erro interno: {str(e)}", None)

    # ============================================
    # INUTILIZAÇÃO DE NUMERAÇÃO
    # ============================================

    def inutilizar_numeracao(
        self,
        empresa_cnpj: str,
        empresa_uf: str,
        serie: str,
        numero_inicial: int,
        numero_final: int,
        ano: int,
        motivo: str,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> SefazResponseModel:
        """
        Inutiliza faixa de numeração de NF-e.

        Args:
            empresa_cnpj: CNPJ emitente
            empresa_uf: UF emitente
            serie: Série da NF-e
            numero_inicial: Número inicial
            numero_final: Número final
            ano: Ano (2 dígitos)
            motivo: Justificativa (mín 15 caracteres)
            cert_bytes: Certificado
            senha_cert: Senha

        Returns:
            SefazResponseModel
        """
        logger.info(
            f"Inutilizando numeração: {numero_inicial}-{numero_final} "
            f"série {serie} para {empresa_cnpj}"
        )

        # Validar motivo
        if len(motivo) < 15:
            raise SefazValidationError(
                "204",
                "Motivo deve ter no mínimo 15 caracteres",
                "motivo"
            )

        try:
            # 1. Obter URL
            url_inutilizacao = self._obter_url_sefaz(empresa_uf, "inutilizacao")

            # 2. Construir XML
            xml_inutilizacao = self._construir_xml_inutilizacao(
                empresa_cnpj,
                empresa_uf,
                serie,
                numero_inicial,
                numero_final,
                ano,
                motivo,
            )

            # 3. Assinar
            xml_assinado = self._assinar_xml(xml_inutilizacao, cert_bytes, senha_cert)

            # 4. Enviar
            response_xml = self._enviar_para_sefaz(
                url_inutilizacao,
                xml_assinado,
                "inutilizacao"
            )

            # 5. Parsear
            sefaz_response = self._parsear_resposta_inutilizacao(response_xml)

            # 6. Log
            self._log_operacao(
                "inutilizacao",
                empresa_cnpj,
                f"{numero_inicial}-{numero_final}",
                serie,
                xml_assinado,
                response_xml,
                sefaz_response.status_codigo,
            )

            return sefaz_response

        except SefazException:
            raise
        except Exception as e:
            logger.error(f"Erro ao inutilizar numeração: {e}", exc_info=True)
            raise SefazException("999", f"Erro interno: {str(e)}", None)

    # ============================================
    # MÉTODOS AUXILIARES - CONSTRUÇÃO XML
    # ============================================

    def _construir_xml_nfe(
        self,
        nfe_data: NotaFiscalCompletaCreate,
        cnpj: str,
        ie: str,
        razao_social: str,
        uf: str,
    ) -> str:
        """
        Constrói XML da NF-e usando PyNFE via adapter.

        Usa o PynfeAdapter para converter modelos Pydantic para objetos PyNFE
        e gerar XML conforme layout SEFAZ 4.0.
        """
        try:
            logger.info("Construindo XML da NF-e com PyNFE adapter")

            # Montar dados da empresa para conversão
            empresa_dados = {
                'cnpj': cnpj,
                'razao_social': razao_social,
                'inscricao_estadual': ie,
                'uf': uf,
                # Campos adicionais podem ser passados se disponíveis
            }

            # Verificar disponibilidade do PyNFE
            if not PyNFeAdapter.is_available():
                raise SefazException(
                    "PyNFE não disponível - sistema de emissão NF-e indisponível",
                    codigo_erro="PYNFE_INDISPONIVEL"
                )

            # Criar adapter instance
            adapter = PyNFeAdapter()

            # Converter para objetos PyNFE
            emitente = adapter.to_pynfe_emitente(empresa_dados)
            cliente = adapter.to_pynfe_cliente(nfe_data.destinatario)
            nota_fiscal = adapter.to_pynfe_nota_fiscal(
                nfe_data=nfe_data,
                emitente=emitente,
                cliente=cliente,
                empresa_dados=empresa_dados
            )

            # Gerar XML usando PyNFE
            xml_nfe = adapter.gerar_xml_nfe(
                nota_fiscal=nota_fiscal,
                ambiente=nfe_data.ambiente
            )

            logger.info(f"XML da NF-e gerado com sucesso ({len(xml_nfe)} bytes)")
            return xml_nfe

        except Exception as e:
            logger.error(f"Erro ao construir XML da NF-e: {e}", exc_info=True)
            raise SefazException(
                "999",
                f"Erro ao gerar XML: {str(e)}",
                None
            )

    def _construir_xml_consulta(self, chave_acesso: str) -> str:
        """Constrói XML de consulta de protocolo"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<consSitNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
    <tpAmb>{self.ambiente == 'homologacao' and '2' or '1'}</tpAmb>
    <xServ>CONSULTAR</xServ>
    <chNFe>{chave_acesso}</chNFe>
</consSitNFe>"""

    def _construir_xml_cancelamento(
        self,
        chave_acesso: str,
        protocolo: str,
        motivo: str,
        cnpj: str,
    ) -> str:
        """Constrói XML de evento de cancelamento"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<envEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
    <evento versao="1.00">
        <infEvento>
            <tpAmb>{self.ambiente == 'homologacao' and '2' or '1'}</tpAmb>
            <CNPJ>{cnpj}</CNPJ>
            <chNFe>{chave_acesso}</chNFe>
            <dhEvento>{datetime.now().isoformat()}</dhEvento>
            <tpEvento>110111</tpEvento>
            <nSeqEvento>1</nSeqEvento>
            <detEvento versao="1.00">
                <descEvento>Cancelamento</descEvento>
                <nProt>{protocolo}</nProt>
                <xJust>{motivo}</xJust>
            </detEvento>
        </infEvento>
    </evento>
</envEvento>"""

    def _construir_xml_inutilizacao(
        self,
        cnpj: str,
        uf: str,
        serie: str,
        numero_inicial: int,
        numero_final: int,
        ano: int,
        motivo: str,
    ) -> str:
        """Constrói XML de inutilização"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<inutNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
    <infInut>
        <tpAmb>{self.ambiente == 'homologacao' and '2' or '1'}</tpAmb>
        <xServ>INUTILIZAR</xServ>
        <cUF>{self._obter_codigo_uf(uf)}</cUF>
        <ano>{ano}</ano>
        <CNPJ>{cnpj}</CNPJ>
        <mod>55</mod>
        <serie>{serie}</serie>
        <nNFIni>{numero_inicial}</nNFIni>
        <nNFFin>{numero_final}</nNFFin>
        <xJust>{motivo}</xJust>
    </infInut>
</inutNFe>"""

    # ============================================
    # MÉTODOS AUXILIARES - VALIDAÇÃO XSD
    # ============================================

    def _validar_xml_antes_assinatura(self, xml_string: str, modelo: str) -> None:
        """
        Valida XML contra schema XSD ANTES de assinar e enviar ao SEFAZ.

        Isso evita erros genéricos do SEFAZ (cStat 225) e permite correção
        antecipada de problemas de estrutura do XML.

        Args:
            xml_string: XML a ser validado
            modelo: Modelo do documento ("55"=NF-e, "65"=NFC-e, "57"=CT-e)

        Raises:
            SefazValidationError: Se validação XSD falhar
        """
        try:
            from app.utils.xml_validator import validar_xml_contra_xsd
            from app.core.config import settings

            # Obter ambiente (para permitir bypass em desenvolvimento)
            ambiente = getattr(settings, 'ENVIRONMENT', 'production')

            logger.info(f"🔍 Validando XML modelo {modelo} contra XSD...")

            # Validar XML
            valido, erros = validar_xml_contra_xsd(
                xml_string=xml_string,
                tipo_documento=modelo,
                ambiente=ambiente
            )

            if not valido:
                # Formatar erros para o usuário
                erros_formatados = "\n".join(f"  {i+1}. {erro}" for i, erro in enumerate(erros[:10]))
                if len(erros) > 10:
                    erros_formatados += f"\n  ... e mais {len(erros) - 10} erro(s)"

                mensagem_erro = (
                    f"XML inválido segundo schema XSD oficial (modelo {modelo}):\n"
                    f"{erros_formatados}\n\n"
                    f"Corrija os erros acima antes de emitir a nota fiscal."
                )

                logger.error(f"❌ Validação XSD falhou:\n{erros_formatados}")

                # Retornar erro 422 (Unprocessable Entity) com detalhes
                raise SefazValidationError(
                    "422",
                    mensagem_erro,
                    campo_erro="xml_estrutura"
                )

            logger.info(f"✅ Validação XSD bem-sucedida (modelo {modelo})")

        except SefazValidationError:
            # Re-raise validação XSD (já formatada)
            raise

        except FileNotFoundError as e:
            # Schema XSD não encontrado
            logger.error(f"Schema XSD não encontrado: {e}")

            # Em produção, bloquear emissão
            if ambiente == "production":
                raise SefazException(
                    "999",
                    f"Schema XSD não configurado. Contate o administrador do sistema.",
                    campo_erro="configuracao_xsd"
                )

            # Em desenvolvimento, apenas warning
            logger.warning(
                "⚠️ DESENVOLVIMENTO: Validação XSD pulada (schema ausente). "
                "Configure schemas em backend/app/schemas/xsd/"
            )

        except Exception as e:
            # Erro inesperado na validação
            logger.error(f"Erro ao validar XML contra XSD: {e}", exc_info=True)

            # Não bloquear emissão por erro de validação (failsafe)
            logger.warning(
                f"⚠️ Validação XSD falhou com erro inesperado: {e}. "
                f"Prosseguindo com emissão (failsafe)."
            )

    # ============================================
    # MÉTODOS AUXILIARES - ASSINATURA E ENVIO
    # ============================================

    def _assinar_xml(self, xml: str, cert_bytes: bytes, senha: str) -> str:
        """
        Assina XML digitalmente usando certificado A1.

        Usa o PynfeAdapter que gerencia a assinatura com pyOpenSSL/signxml.
        
        SEGURANÇA: Este método NÃO loga dados sensíveis (cert_bytes, senha).
        Apenas loga hash SHA256 do certificado para rastreamento.
        """
        try:
            import hashlib

            # Hash do certificado para rastreamento (seguro para logs)
            cert_fingerprint = hashlib.sha256(cert_bytes).hexdigest()[:16]

            logger.info(f"Assinando XML digitalmente (cert fingerprint: {cert_fingerprint})")

            # Verificar disponibilidade do PyNFE
            if not PyNFeAdapter.is_available():
                raise SefazException(
                    "PyNFE não disponível - sistema de assinatura NF-e indisponível",
                    codigo_erro="PYNFE_INDISPONIVEL"
                )

            adapter = PyNFeAdapter()
            xml_assinado = adapter.assinar_xml(
                xml_string=xml,
                cert_bytes=cert_bytes,
                senha_cert=senha
            )

            logger.info(
                f"XML assinado com sucesso (tamanho: {len(xml_assinado)} bytes, "
                f"cert: {cert_fingerprint})"
            )
            return xml_assinado

        except Exception as e:
            # Sanitizar erro para evitar leak de informações sensíveis
            error_msg = str(e)
            if 'password' in error_msg.lower() or 'senha' in error_msg.lower():
                error_msg = "Erro de autenticação do certificado (senha ou formato inválido)"
            
            logger.error(f"Erro ao assinar XML: {error_msg}")
            raise SefazAuthorizationError(
                "539",
                f"Falha na assinatura digital: {error_msg}",
                "certificado"
            )

    def _enviar_para_sefaz(
        self,
        url: str,
        xml: str,
        operacao: str,
    ) -> str:
        """
        Envia XML para SEFAZ via SOAP/HTTP.

        Args:
            url: URL do webservice SEFAZ
            xml: XML assinado
            operacao: Tipo de operação

        Returns:
            XML de resposta

        Raises:
            SefazTimeoutError: Em caso de timeout
            SefazException: Em caso de erro de comunicação
        """
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            logger.info(f"Enviando {operacao} para SEFAZ: {url}")

            # Configurar retry strategy
            retry_strategy = Retry(
                total=RETRY_ATTEMPTS,
                backoff_factor=RETRY_BACKOFF,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST"]
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            session = requests.Session()
            session.mount("https://", adapter)

            # Headers SOAP para NF-e 4.0
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'SOAPAction': f'"{operacao}"',
            }

            # Garantir declaração XML
            if not xml.startswith('<?xml'):
                xml = f'<?xml version="1.0" encoding="UTF-8"?>{xml}'

            # Log seguro (sem dados sensíveis)
            logger.debug(f"Tamanho do XML: {len(xml)} bytes")
            logger.debug(f"Headers: {headers}")

            # Fazer requisição
            response = session.post(
                url,
                data=xml.encode('utf-8'),
                headers=headers,
                timeout=TIMEOUT_SEFAZ,
                verify=True  # Verificar certificado SSL do servidor
            )

            # Verificar status HTTP
            response.raise_for_status()

            logger.info(
                f"Resposta SEFAZ recebida: HTTP {response.status_code} "
                f"({len(response.content)} bytes)"
            )

            return response.text

        except requests.Timeout as e:
            logger.error(f"Timeout ao comunicar com SEFAZ: {e}")
            raise SefazTimeoutError(
                "999",
                f"Timeout ao aguardar resposta da SEFAZ ({TIMEOUT_SEFAZ}s)",
                None
            )

        except requests.RequestException as e:
            logger.error(f"Erro HTTP ao comunicar com SEFAZ: {e}")
            raise SefazException(
                "999",
                f"Erro de comunicação com SEFAZ: {str(e)}",
                None
            )

        except Exception as e:
            logger.error(f"Erro ao enviar para SEFAZ: {e}", exc_info=True)
            raise SefazException(
                "999",
                f"Erro ao enviar requisição: {str(e)}",
                None
            )

    # ============================================
    # MÉTODOS AUXILIARES - PARSE RESPOSTAS
    # ============================================

    def _parsear_resposta_autorizacao(self, xml: str, empresa_uf: str) -> SefazResponseModel:
        """
        Parseia resposta de autorização usando adapter.

        Extrai código de status, protocolo, chave de acesso e rejeições.
        
        Args:
            xml: XML de resposta da SEFAZ
            empresa_uf: UF do emitente (ex: 'SP', 'RJ')
        """
        try:
            logger.info("Parseando resposta de autorização SEFAZ")

            # Verificar disponibilidade do PyNFE
            if not PyNFeAdapter.is_available():
                raise SefazException(
                    "PyNFE não disponível - sistema de parse NF-e indisponível",
                    codigo_erro="PYNFE_INDISPONIVEL"
                )

            adapter = PyNFeAdapter()
            response = adapter.parsear_resposta_sefaz(
                xml_retorno=xml,
                uf=empresa_uf,  # Corrigido: passar UF do emitente, não o ambiente
                ambiente='2' if self.ambiente == 'homologacao' else '1'
            )

            return response

        except Exception as e:
            logger.error(f"Erro ao parsear resposta: {e}", exc_info=True)
            # Retornar erro genérico
            return SefazResponseModel(
                status_codigo='999',
                status_descricao=f'Erro ao processar resposta: {str(e)}',
                rejeicoes=[
                    SefazRejeicao(
                        codigo='999',
                        motivo=str(e),
                        correcao='Verifique os logs do servidor'
                    )
                ],
            )

    def _parsear_resposta_consulta(self, xml: str, empresa_uf: str = 'SP') -> SefazResponseModel:
        """Parseia resposta de consulta"""
        return self._parsear_resposta_autorizacao(xml, empresa_uf)

    def _parsear_resposta_cancelamento(self, xml: str, empresa_uf: str = 'SP') -> SefazResponseModel:
        """Parseia resposta de cancelamento"""
        return self._parsear_resposta_autorizacao(xml, empresa_uf)

    def _parsear_resposta_inutilizacao(self, xml: str) -> SefazResponseModel:
        """Parseia resposta de inutilização"""
        return SefazResponseModel(
            status_codigo="102",
            status_descricao="Inutilização de número homologado",
            rejeicoes=[],
        )

    # ============================================
    # MÉTODOS AUXILIARES - CACHE
    # ============================================

    def _get_cache(self, chave: str) -> Optional[SefazResponseModel]:
        """Obtém resposta do cache in-memory"""
        if chave in self._cache:
            response, timestamp = self._cache[chave]
            if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL_SECONDS):
                return response
            else:
                del self._cache[chave]
        return None

    def _set_cache(self, chave: str, response: SefazResponseModel):
        """Armazena resposta no cache"""
        self._cache[chave] = (response, datetime.now())

    def _invalidate_cache(self, chave: str):
        """Invalida cache de uma chave"""
        if chave in self._cache:
            del self._cache[chave]

    # ============================================
    # MÉTODOS AUXILIARES - VALIDAÇÃO E UTILITÁRIOS
    # ============================================

    def _validar_cancelamento(self, data_autorizacao: datetime, motivo: str):
        """Valida condições para cancelamento"""
        # Verificar 24 horas
        if datetime.now() - data_autorizacao > timedelta(hours=24):
            raise SefazValidationError(
                "218",
                "Cancelamento não permitido após 24 horas da autorização",
                "data_autorizacao"
            )

        # Verificar motivo
        if len(motivo) < 15:
            raise SefazValidationError(
                "204",
                "Motivo deve ter no mínimo 15 caracteres",
                "motivo"
            )

    def _obter_url_sefaz(self, uf: str, operacao: str) -> str:
        """
        Obtem URL do webservice SEFAZ conforme o ambiente configurado.

        Args:
            uf: Sigla do estado
            operacao: autorizacao, consulta, cancelamento, inutilizacao, distribuicao

        Returns:
            URL do webservice

        Raises:
            SefazException: Se UF/operacao invalida
        """
        # DistribuicaoDFe e centralizado (Ambiente Nacional), nao por UF
        if operacao == "distribuicao":
            return self._obter_url_distribuicao()

        endpoints_map = obter_endpoints_por_ambiente(self.ambiente)

        if uf not in endpoints_map:
            raise SefazException(
                "999",
                f"UF nao suportada: {uf}",
                "uf"
            )

        endpoints = endpoints_map[uf]

        if operacao not in endpoints:
            raise SefazException(
                "999",
                f"Operacao nao suportada: {operacao}. "
                f"Operacoes validas: {', '.join(endpoints.keys())}",
                "operacao"
            )

        return endpoints[operacao]

    def _obter_url_distribuicao(self, ambiente: Optional[str] = None) -> str:
        """Resolve o endpoint nacional de distribuicao para o ambiente informado."""
        ambiente_resolvido = (ambiente or self.ambiente or "homologacao").strip().lower()
        if ambiente_resolvido not in {"producao", "homologacao"}:
            ambiente_resolvido = "homologacao"
        return obter_endpoint_distribuicao(ambiente_resolvido)

    def _ambientes_consulta_distribuicao(self) -> List[str]:
        """
        Define os ambientes candidatos para distribuicao.

        Quando o sistema estiver em homologacao, tenta producao em seguida
        para manter a busca funcional mesmo sem configuracao explicita.
        """
        ambientes: List[str] = []
        for ambiente in [self.ambiente, "producao"]:
            ambiente_normalizado = (ambiente or "").strip().lower()
            if ambiente_normalizado in {"producao", "homologacao"} and ambiente_normalizado not in ambientes:
                ambientes.append(ambiente_normalizado)
        return ambientes or ["homologacao"]

    def _obter_codigo_uf(self, uf: str) -> str:
        """Obtém código IBGE da UF"""
        codigos = {
            "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
            "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
            "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
            "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
            "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
            "SE": "28", "TO": "17",
        }
        return codigos.get(uf, "00")

    def _log_operacao(
        self,
        operacao: str,
        cnpj: str,
        numero: str,
        serie: str,
        xml_request: str,
        xml_response: str,
        status: str,
    ):
        """
        Registra operação no log do SEFAZ.

        Note:
            Em produção, armazenar na tabela sefaz_log
        """
        logger.info(
            f"Log SEFAZ: {operacao} | CNPJ: {cnpj} | "
            f"Nota: {numero}/{serie} | Status: {status}"
        )
        # TODO: Inserir no banco de dados na tabela sefaz_log

    def _normalizar_cnpj(self, valor: Optional[str]) -> str:
        """Remove formatacao e mantem apenas os digitos do CNPJ."""
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    def _safe_int(self, valor: Optional[str]) -> int:
        """Converte string numerica para int sem propagar erro."""
        try:
            return int(str(valor or "0").strip())
        except (TypeError, ValueError):
            return 0

    def _tag_localname(self, element: Any) -> str:
        """Retorna o localname da tag XML, com ou sem namespace."""
        if element is None:
            return ""
        try:
            return etree.QName(element).localname
        except Exception:
            tag = getattr(element, "tag", "")
            return str(tag).split("}", 1)[-1]

    def _find_first(self, element: Any, *local_names: str) -> Any:
        """Busca o primeiro elemento por localname ignorando namespace."""
        if element is None:
            return None

        nomes = set(local_names)
        for child in element.iter():
            if self._tag_localname(child) in nomes:
                return child
        return None

    def _find_text(self, element: Any, *local_names: str) -> Optional[str]:
        """Extrai o texto do primeiro elemento encontrado."""
        found = self._find_first(element, *local_names)
        if found is None or found.text is None:
            return None
        texto = found.text.strip()
        return texto or None

    def _parse_datetime(self, valor: Optional[str]) -> datetime:
        """Converte string ISO para datetime com fallback seguro."""
        if not valor:
            return datetime.now()

        normalizado = valor.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalizado)
        except ValueError:
            try:
                return datetime.strptime(normalizado[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                logger.warning("Nao foi possivel converter data SEFAZ: %s", valor)
                return datetime.now()

    def _obter_uf_empresa(self, empresa_id: str) -> str:
        """Obtém a UF da empresa para montar a consulta de distribuicao."""
        from app.db.supabase_client import supabase_admin

        try:
            response = supabase_admin.table("empresas")\
                .select("estado")\
                .eq("id", empresa_id)\
                .limit(1)\
                .execute()

            if response.data:
                uf = (response.data[0].get("estado") or "SP").upper()
                if len(uf) == 2:
                    return uf
        except Exception as exc:
            logger.warning(
                "Nao foi possivel obter UF da empresa %s para distribuicao: %s",
                empresa_id,
                exc,
            )

        return "SP"

    def _obter_maior_nsu_empresa(self, empresa_id: str) -> int:
        """Lê o maior NSU ja persistido para retomar a distribuicao."""
        from app.db.supabase_client import supabase_admin

        try:
            response = supabase_admin.table("notas_fiscais")\
                .select("nsu,chave_acesso")\
                .eq("empresa_id", empresa_id)\
                .in_("tipo_nf", ["NFe", "NFCe"])\
                .gt("nsu", 0)\
                .order("nsu", desc=True)\
                .limit(500)\
                .execute()

            for row in response.data or []:
                chave_acesso = str(row.get("chave_acesso") or "").strip()
                nsu = self._safe_int(row.get("nsu"))

                if nsu <= 0:
                    continue

                if chave_acesso.isdigit() and len(chave_acesso) == 44:
                    return nsu
        except Exception as exc:
            logger.warning(
                "Nao foi possivel recuperar NSU da empresa %s. "
                "A busca automatica vai reiniciar do zero: %s",
                empresa_id,
                exc,
            )

        return 0

    def _construir_xml_distribuicao(
        self,
        cnpj: str,
        empresa_uf: str,
        ult_nsu: int,
        ambiente: Optional[str] = None,
    ) -> str:
        """Monta o payload distDFeInt para consulta incremental."""
        ambiente_resolvido = (ambiente or self.ambiente or "homologacao").strip().lower()
        tp_amb = "1" if ambiente_resolvido == "producao" else "2"
        c_uf = self._obter_codigo_uf((empresa_uf or "SP").upper())
        ult_nsu_formatado = f"{max(0, int(ult_nsu)):015d}"

        return (
            f'<distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
            f"<tpAmb>{tp_amb}</tpAmb>"
            f"<cUFAutor>{c_uf}</cUFAutor>"
            f"<CNPJ>{cnpj}</CNPJ>"
            f"<distNSU><ultNSU>{ult_nsu_formatado}</ultNSU></distNSU>"
            f"</distDFeInt>"
        )

    def _construir_envelope_soap_distribuicao(self, xml_distribuicao: str) -> str:
        """Envolve o distDFeInt no envelope SOAP 1.1 esperado pelo AN."""
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
        {xml_distribuicao}
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap:Body>
</soap:Envelope>"""

    def _enviar_distribuicao_dfe(
        self,
        url: str,
        xml_distribuicao: str,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> str:
        """
        Envia o envelope de distribuicao ao Ambiente Nacional usando mTLS.
        """
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        cert_pem_path = None
        key_pem_path = None

        try:
            cert_pem, key_pem = certificado_service.pfx_para_pem(cert_bytes, senha_cert)
            envelope = self._construir_envelope_soap_distribuicao(xml_distribuicao)

            cert_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
            key_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")

            cert_pem_file.write(cert_pem)
            cert_pem_file.flush()
            cert_pem_path = cert_pem_file.name
            cert_pem_file.close()

            key_pem_file.write(key_pem)
            key_pem_file.flush()
            key_pem_path = key_pem_file.name
            key_pem_file.close()

            retry_strategy = Retry(
                total=RETRY_ATTEMPTS,
                backoff_factor=RETRY_BACKOFF,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST"],
            )

            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": (
                    '"http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/'
                    'nfeDistDFeInteresse"'
                ),
            }

            response = session.post(
                url,
                data=envelope.encode("utf-8"),
                headers=headers,
                timeout=TIMEOUT_SEFAZ,
                verify=True,
                cert=(cert_pem_path, key_pem_path),
            )
            response.raise_for_status()
            return response.text

        except requests.Timeout as exc:
            raise SefazTimeoutError(
                "999",
                f"Timeout ao consultar distribuicao DF-e ({TIMEOUT_SEFAZ}s)",
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise SefazAuthorizationError(
                "539",
                f"Falha no uso do certificado digital para distribuicao: {exc}",
            ) from exc
        except requests.RequestException as exc:
            raise SefazException(
                "999",
                f"Erro HTTP ao consultar distribuicao DF-e: {exc}",
            ) from exc
        finally:
            for path in (cert_pem_path, key_pem_path):
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        logger.warning("Nao foi possivel remover arquivo temporario: %s", path)

    def _extrair_xml_doczip(self, doc_zip: Any) -> Optional[str]:
        """Extrai o XML interno do docZip real ou do mock inline."""
        if doc_zip is None:
            return None

        for child in doc_zip:
            if getattr(child, "tag", None) and self._tag_localname(child) != "NSU":
                return etree.tostring(child, encoding="unicode")

        conteudo = (doc_zip.text or "").strip()
        if not conteudo:
            return None

        try:
            payload = base64.b64decode(conteudo)
            try:
                payload = gzip.decompress(payload)
            except OSError:
                pass
            return payload.decode("utf-8", errors="ignore")
        except Exception:
            return conteudo

    def _parsear_resumo_ou_proc_nfe(
        self,
        xml_nota: str,
        nsu: int,
    ):
        """Converte resNFe/procNFe em NFeBuscadaMetadata."""
        from app.models.nfe_busca import NFeBuscadaMetadata, mapear_situacao_nfe

        if etree is None:
            raise SefazException("999", "lxml nao disponivel para parse da distribuicao")

        root = etree.fromstring(xml_nota.encode("utf-8"))

        resumo = self._find_first(root, "resNFe")
        if resumo is not None:
            chave = (self._find_text(resumo, "chNFe") or "").strip()
            cnpj_emitente = self._normalizar_cnpj(self._find_text(resumo, "CNPJEmit"))
            tipo_operacao = (self._find_text(resumo, "tpNF") or "1").strip()
            valor_total = Decimal(str(self._find_text(resumo, "vNF") or "0"))
            situacao_codigo = (self._find_text(resumo, "cSitNFe") or "1").strip()

            if len(chave) != 44 or not chave.isdigit() or len(cnpj_emitente) != 14:
                return None

            cnpj_dest = self._normalizar_cnpj(self._find_text(resumo, "CNPJDest"))
            cpf_dest = self._normalizar_cnpj(self._find_text(resumo, "CPFDest"))

            return NFeBuscadaMetadata(
                chave_acesso=chave,
                nsu=nsu,
                data_emissao=self._parse_datetime(self._find_text(resumo, "dhEmi")),
                tipo_operacao="0" if tipo_operacao == "0" else "1",
                valor_total=valor_total,
                cnpj_emitente=cnpj_emitente,
                nome_emitente=(self._find_text(resumo, "xNomeEmit") or "Emitente nao informado")[:255],
                cnpj_destinatario=cnpj_dest if len(cnpj_dest) == 14 else None,
                cpf_destinatario=cpf_dest if len(cpf_dest) == 11 else None,
                nome_destinatario=(self._find_text(resumo, "xNomeDest") or None),
                situacao=mapear_situacao_nfe(situacao_codigo),
                situacao_codigo=situacao_codigo,
                protocolo=self._find_text(resumo, "nProt"),
                xml_resumo=xml_nota,
            )

        emit = self._find_first(root, "emit")
        inf_prot = self._find_first(root, "infProt")
        chave = (self._find_text(root, "chNFe") or "").strip()
        cnpj_emitente = self._normalizar_cnpj(self._find_text(emit, "CNPJ"))

        if len(chave) != 44 or not chave.isdigit() or len(cnpj_emitente) != 14:
            return None

        dest = self._find_first(root, "dest")
        c_stat = (self._find_text(inf_prot, "cStat") or "100").strip()
        situacao_codigo_map = {
            "100": "1",
            "150": "1",
            "101": "3",
            "151": "3",
            "155": "3",
            "301": "2",
            "302": "2",
            "303": "2",
        }
        situacao_codigo = situacao_codigo_map.get(c_stat, "1")
        cnpj_dest = self._normalizar_cnpj(self._find_text(dest, "CNPJ"))
        cpf_dest = self._normalizar_cnpj(self._find_text(dest, "CPF"))

        return NFeBuscadaMetadata(
            chave_acesso=chave,
            nsu=nsu,
            data_emissao=self._parse_datetime(
                self._find_text(root, "dhEmi") or self._find_text(root, "dhRecbto")
            ),
            tipo_operacao="0" if (self._find_text(root, "tpNF") or "1").strip() == "0" else "1",
            valor_total=Decimal(str(self._find_text(root, "vNF") or "0")),
            cnpj_emitente=cnpj_emitente,
            nome_emitente=(self._find_text(emit, "xNome") or "Emitente nao informado")[:255],
            cnpj_destinatario=cnpj_dest if len(cnpj_dest) == 14 else None,
            cpf_destinatario=cpf_dest if len(cpf_dest) == 11 else None,
            nome_destinatario=(self._find_text(dest, "xNome") or None),
            situacao={"1": "autorizada", "2": "denegada", "3": "cancelada"}.get(
                situacao_codigo,
                "autorizada",
            ),
            situacao_codigo=situacao_codigo,
            protocolo=self._find_text(inf_prot, "nProt"),
            xml_resumo=xml_nota,
        )

    def _parsear_resposta_distribuicao(self, xml_response: str):
        """Parseia o SOAP/XML da distribuicao DF-e e extrai os resumos."""
        from app.models.nfe_busca import DistribuicaoResponseModel

        if etree is None:
            raise SefazException("999", "lxml nao disponivel para parse da distribuicao")

        root = etree.fromstring(xml_response.encode("utf-8"))
        retorno = self._find_first(root, "retDistDFeInt")
        if retorno is None:
            resultado_msg = self._find_first(root, "nfeResultMsg")
            xml_embutido = (resultado_msg.text or "").strip() if resultado_msg is not None else ""

            if xml_embutido:
                root_embutido = etree.fromstring(html.unescape(xml_embutido).encode("utf-8"))
                retorno = self._find_first(root_embutido, "retDistDFeInt")

            if retorno is None:
                raise SefazException(
                    "999",
                    "Resposta da distribuicao DF-e nao contem retDistDFeInt",
                )

        status_codigo = (self._find_text(retorno, "cStat") or "999").strip()
        motivo = (
            self._find_text(retorno, "xMotivo")
            or obter_mensagem_sefaz(status_codigo)
            or "Resposta da distribuicao processada"
        )
        ultimo_nsu = self._safe_int(self._find_text(retorno, "ultNSU"))
        max_nsu = self._safe_int(self._find_text(retorno, "maxNSU"))

        notas_encontradas = []
        for doc_zip in retorno.iter():
            if self._tag_localname(doc_zip) != "docZip":
                continue

            nsu = self._safe_int(doc_zip.get("NSU") or self._find_text(doc_zip, "NSU"))
            xml_nota = self._extrair_xml_doczip(doc_zip)
            if not xml_nota:
                continue

            try:
                nota = self._parsear_resumo_ou_proc_nfe(xml_nota, nsu)
                if nota is not None:
                    notas_encontradas.append(nota)
            except Exception as exc:
                logger.warning("Documento distribuido ignorado por falha no parse: %s", exc)

        return DistribuicaoResponseModel(
            status_codigo=status_codigo,
            motivo=motivo,
            notas_encontradas=notas_encontradas,
            ultimo_nsu=ultimo_nsu,
            max_nsu=max_nsu,
            total_notas=len(notas_encontradas),
        )

    def _persistir_notas_distribuicao(
        self,
        empresa_id: str,
        notas_encontradas: List[Any],
    ) -> int:
        """Persiste as notas retornadas pela distribuicao antes da leitura final."""
        if not notas_encontradas:
            return 0

        from app.db.supabase_client import supabase_admin
        from app.repositories.nota_fiscal_repository import NotaFiscalRepository
        from app.services.nfe_mapper import map_nfe_buscada_to_nota_fiscal

        repository = NotaFiscalRepository(supabase_admin)
        notas_para_upsert = []

        for nota in notas_encontradas:
            try:
                nota_create = map_nfe_buscada_to_nota_fiscal(nota, empresa_id).model_copy(
                    update={
                        "tipo_operacao": "saida" if nota.tipo_operacao == "1" else "entrada",
                        "cpf_destinatario": nota.cpf_destinatario,
                        "fonte": "sefaz",
                        "xml_completo": nota.xml_resumo,
                    }
                )
                notas_para_upsert.append(nota_create)
            except Exception as exc:
                logger.warning(
                    "Nota distribuida ignorada durante persistencia (%s): %s",
                    getattr(nota, "chave_acesso", "sem_chave"),
                    exc,
                )

        if not notas_para_upsert:
            return 0

        repository.upsert_lote(notas_para_upsert)
        self._atualizar_nsu_persistido(empresa_id, notas_encontradas)
        return len(notas_para_upsert)

    def _atualizar_nsu_persistido(
        self,
        empresa_id: str,
        notas_encontradas: List[Any],
    ) -> None:
        """Atualiza o NSU persistido quando a coluna existir no banco."""
        from app.db.supabase_client import supabase_admin

        coluna_nsu_indisponivel = False
        for nota in notas_encontradas:
            if coluna_nsu_indisponivel:
                break

            try:
                supabase_admin.table("notas_fiscais").update({
                    "nsu": nota.nsu,
                }).eq("empresa_id", empresa_id)\
                    .eq("chave_acesso", nota.chave_acesso)\
                    .execute()
            except Exception as exc:
                mensagem = str(exc).lower()
                if "nsu" in mensagem and ("column" in mensagem or "schema" in mensagem):
                    coluna_nsu_indisponivel = True
                    logger.warning(
                        "Coluna nsu ausente em notas_fiscais. "
                        "Execute a migration 011 para sincronizacao incremental completa."
                    )
                else:
                    logger.warning(
                        "Falha ao atualizar NSU da nota %s: %s",
                        nota.chave_acesso,
                        exc,
                    )

    def _registrar_log_distribuicao(
        self,
        empresa_id: str,
        uf: str,
        request_xml: Optional[str],
        response_xml: Optional[str],
        status_codigo: str,
        status_descricao: str,
        sucesso: bool,
        tempo_resposta_ms: int,
        mensagem_erro: Optional[str] = None,
        ambiente_consulta: Optional[str] = None,
    ) -> None:
        """Registra auditoria basica da consulta de distribuicao."""
        from app.db.supabase_client import supabase_admin

        try:
            supabase_admin.table("sefaz_log").insert({
                "empresa_id": empresa_id,
                "operacao": "consulta_distribuicao",
                "uf": uf,
                "ambiente": ambiente_consulta or self.ambiente,
                "request_xml": request_xml,
                "response_xml": response_xml,
                "status_codigo": status_codigo,
                "status_descricao": status_descricao,
                "sucesso": sucesso,
                "mensagem_erro": mensagem_erro,
                "tempo_resposta_ms": tempo_resposta_ms,
                "response_timestamp": datetime.now().isoformat(),
            }).execute()
        except Exception as exc:
            logger.warning("Nao foi possivel registrar sefaz_log de distribuicao: %s", exc)

    async def _sincronizar_notas_novas(
        self,
        cnpj: str,
        empresa_id: str,
        contador_id: str,
    ) -> Dict[str, Any]:
        """
        Consulta a SEFAZ primeiro e persiste as notas novas antes da leitura do banco.
        """
        from app.adapters.mock_sefaz_client import get_distribuicao_client
        from app.services.certificado_service import (
            CertificadoAusenteError,
            CertificadoError,
            CertificadoExpiradoError,
        )

        empresa_uf = self._obter_uf_empresa(empresa_id)
        ultimo_nsu_local = self._obter_maior_nsu_empresa(empresa_id)
        inicio = datetime.now()
        ambiente_utilizado = self.ambiente
        xml_request = self._construir_xml_distribuicao(
            cnpj,
            empresa_uf,
            ultimo_nsu_local,
            ambiente=ambiente_utilizado,
        )

        try:
            mock_client = get_distribuicao_client()
            certificado_usado = "mock"

            if mock_client is not None:
                xml_response = mock_client.consultar(
                    cnpj=cnpj,
                    nsu_inicial=ultimo_nsu_local,
                    uf=empresa_uf,
                )
                distribuicao = self._parsear_resposta_distribuicao(xml_response)
                novas_notas = 0
                if distribuicao.notas_encontradas:
                    novas_notas = self._persistir_notas_distribuicao(
                        empresa_id,
                        distribuicao.notas_encontradas,
                    )
            else:
                cert_bytes, senha_cert, certificado_usado = await certificado_service.obter_certificado_para_busca(
                    empresa_id=empresa_id,
                    contador_id=contador_id,
                )
                distribuicao = None
                xml_response = None
                novas_notas = 0
                # Limite de segurança: evita loop infinito (200 páginas × ~50 notas = ~10k notas)
                MAX_PAGINAS_SYNC = 200

                for ambiente_consulta in self._ambientes_consulta_distribuicao():
                    ambiente_utilizado = ambiente_consulta
                    nsu_consulta = ultimo_nsu_local
                    pagina = 0
                    ambiente_teve_erro = False

                    while pagina < MAX_PAGINAS_SYNC:
                        pagina += 1
                        xml_request = self._construir_xml_distribuicao(
                            cnpj,
                            empresa_uf,
                            nsu_consulta,
                            ambiente=ambiente_consulta,
                        )
                        try:
                            xml_response = self._enviar_distribuicao_dfe(
                                self._obter_url_distribuicao(ambiente_consulta),
                                xml_request,
                                cert_bytes,
                                senha_cert,
                            )
                            distribuicao = self._parsear_resposta_distribuicao(xml_response)
                        except Exception as req_exc:
                            logger.warning(
                                "[SYNC SEFAZ] Erro no ambiente %s (tentando próximo): %s",
                                ambiente_consulta,
                                req_exc,
                            )
                            ambiente_teve_erro = True
                            break

                        if distribuicao.status_codigo == "589" and nsu_consulta > 0:
                            logger.warning(
                                "SEFAZ retornou cStat 589 para empresa %s no ambiente %s. "
                                "Reiniciando distribuicao a partir do NSU zero.",
                                empresa_id,
                                ambiente_consulta,
                            )
                            nsu_consulta = 0
                            pagina = 0
                            continue

                        # Códigos de erro SEFAZ — tentar próximo ambiente
                        if distribuicao.status_codigo not in {"137", "138"}:
                            logger.warning(
                                "[SYNC SEFAZ] Ambiente %s retornou cStat %s (%s) — "
                                "tentando próximo ambiente.",
                                ambiente_consulta,
                                distribuicao.status_codigo,
                                distribuicao.motivo,
                            )
                            ambiente_teve_erro = True
                            break

                        # Persistir batch atual (deduplicação via upsert por chave_acesso)
                        if distribuicao.notas_encontradas:
                            batch = self._persistir_notas_distribuicao(
                                empresa_id,
                                distribuicao.notas_encontradas,
                            )
                            novas_notas += batch
                            logger.info(
                                "[SYNC SEFAZ] Página %d: %d notas salvas "
                                "(NSU %d → %d / max %d, empresa %s, ambiente %s)",
                                pagina,
                                batch,
                                nsu_consulta,
                                distribuicao.ultimo_nsu,
                                distribuicao.max_nsu,
                                empresa_id,
                                ambiente_consulta,
                            )

                        # Sem mais páginas — encerrar paginação
                        if distribuicao.status_codigo == "137" or not distribuicao.tem_mais_notas:
                            break

                        # Avançar para a próxima página
                        nsu_consulta = distribuicao.ultimo_nsu

                    # Parar de tentar ambientes só se teve sucesso real (138)
                    if not ambiente_teve_erro and distribuicao is not None and distribuicao.status_codigo in {"137", "138"}:
                        break

                if distribuicao is None or xml_response is None:
                    raise SefazException(
                        "999",
                        "Nao foi possivel obter resposta da distribuicao DF-e",
                    )

            sincronizacao_ok = distribuicao.status_codigo in {"137", "138"}

            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            self._registrar_log_distribuicao(
                empresa_id=empresa_id,
                uf=empresa_uf,
                request_xml=xml_request,
                response_xml=xml_response,
                status_codigo=distribuicao.status_codigo,
                status_descricao=distribuicao.motivo,
                sucesso=sincronizacao_ok,
                tempo_resposta_ms=tempo_ms,
                mensagem_erro=None if sincronizacao_ok else distribuicao.motivo,
                ambiente_consulta=ambiente_utilizado,
            )

            return {
                "fonte": "sefaz" if sincronizacao_ok else "banco_local",
                "sincronizacao_realizada": sincronizacao_ok,
                "certificado_usado": certificado_usado,
                "novas_notas_sincronizadas": novas_notas,
                "mensagem_sincronizacao": distribuicao.motivo,
                "status_codigo_sincronizacao": distribuicao.status_codigo,
                "ultimo_nsu_sincronizacao": distribuicao.ultimo_nsu,
                "max_nsu_sincronizacao": distribuicao.max_nsu,
                "ambiente_consulta": ambiente_utilizado,
            }

        except (CertificadoAusenteError, CertificadoExpiradoError, CertificadoError) as exc:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            self._registrar_log_distribuicao(
                empresa_id=empresa_id,
                uf=empresa_uf,
                request_xml=xml_request,
                response_xml=None,
                status_codigo="0",
                status_descricao="Certificado indisponivel para distribuicao",
                sucesso=False,
                tempo_resposta_ms=tempo_ms,
                mensagem_erro=str(exc),
                ambiente_consulta=ambiente_utilizado,
            )
            return {
                "fonte": "banco_local",
                "sincronizacao_realizada": False,
                "certificado_usado": "indisponivel",
                "novas_notas_sincronizadas": 0,
                "mensagem_sincronizacao": str(exc),
                "status_codigo_sincronizacao": "0",
                "ultimo_nsu_sincronizacao": ultimo_nsu_local,
                "max_nsu_sincronizacao": ultimo_nsu_local,
                "ambiente_consulta": ambiente_utilizado,
            }
        except Exception as exc:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            self._registrar_log_distribuicao(
                empresa_id=empresa_id,
                uf=empresa_uf,
                request_xml=xml_request,
                response_xml=None,
                status_codigo="999",
                status_descricao="Falha tecnica na distribuicao",
                sucesso=False,
                tempo_resposta_ms=tempo_ms,
                mensagem_erro=str(exc),
                ambiente_consulta=ambiente_utilizado,
            )
            logger.warning(
                "Falha na sincronizacao automatica SEFAZ da empresa %s: %s",
                empresa_id,
                exc,
                exc_info=True,
            )
            return {
                "fonte": "banco_local",
                "sincronizacao_realizada": False,
                "certificado_usado": certificado_usado,
                "novas_notas_sincronizadas": 0,
                "mensagem_sincronizacao": f"Falha tecnica ao consultar SEFAZ: {exc}",
                "status_codigo_sincronizacao": "999",
                "ultimo_nsu_sincronizacao": ultimo_nsu_local,
                "max_nsu_sincronizacao": ultimo_nsu_local,
                "ambiente_consulta": ambiente_utilizado,
            }

    async def sincronizar_e_buscar_notas_por_cnpj(
        self,
        cnpj: str,
        empresa_id: str,
        contador_id: str,
        nsu_inicial: Optional[int] = None,
        max_notas: int = 50,
    ) -> Dict[str, Any]:
        """
        Fluxo principal: sincroniza notas novas na SEFAZ e depois consulta o banco.

        A sincronizacao automatica so roda na primeira pagina para manter a
        paginacao estavel durante o carregamento de resultados adicionais.
        """
        metadata = {
            "fonte": "banco_local",
            "sincronizacao_realizada": False,
            "certificado_usado": "nao_aplicado",
            "novas_notas_sincronizadas": 0,
            "mensagem_sincronizacao": None,
            "status_codigo_sincronizacao": None,
            "ultimo_nsu_sincronizacao": None,
            "max_nsu_sincronizacao": None,
            "ambiente_consulta": None,
        }

        consulta_inicial = nsu_inicial in (None, 0)
        cnpj_normalizado = self._normalizar_cnpj(cnpj)

        if consulta_inicial:
            metadata.update(
                await self._sincronizar_notas_novas(
                    cnpj=cnpj_normalizado,
                    empresa_id=empresa_id,
                    contador_id=contador_id,
                )
            )

        response = self.buscar_notas_por_cnpj(
            cnpj=cnpj_normalizado,
            empresa_id=empresa_id,
            nsu_inicial=nsu_inicial,
            max_notas=max_notas,
        )

        return {
            "response": response,
            **metadata,
        }

    # ============================================
    # BUSCA DE NOTAS (BANCO DE DADOS LOCAL)
    # ============================================

    def buscar_notas_por_cnpj(
        self,
        cnpj: str,
        empresa_id: str,
        nsu_inicial: Optional[int] = None,
        max_notas: int = 50,
    ):
        """
        Busca notas fiscais cadastradas no BANCO DE DADOS LOCAL para um CNPJ/Empresa.

        IMPORTANTE: Este metodo consulta APENAS o banco de dados local (Supabase).
        Ele NAO faz chamadas ao SEFAZ e NAO chama _obter_url_sefaz().

        Para popular o banco com notas reais:
        1. Importe XMLs via endpoint POST /nfe/importar-xml
        2. Importe lote via endpoint POST /nfe/importar-lote
        3. Consulte nota especifica via GET /nfe/consultar-chave/{chave}

        Args:
            cnpj: CNPJ para consultar (14 digitos sem formatacao)
            empresa_id: UUID da empresa no banco
            nsu_inicial: Offset para paginacao

        Returns:
            DistribuicaoResponseModel com lista de notas do banco
        """
        from app.models.nfe_busca import (
            DistribuicaoResponseModel,
            NFeBuscadaMetadata,
        )
        from decimal import Decimal
        from datetime import datetime
        # SEGURANÇA: Usa supabase_admin mas query é filtrada por empresa_id
        # para prevenir vazamento entre tenants.
        from app.db.supabase_client import supabase_admin

        logger.info(
            f"[BUSCA LOCAL] Buscando notas no banco de dados | "
            f"Empresa: {empresa_id} | CNPJ: {cnpj}"
        )

        try:
            # 1. Consultar banco de dados (APENAS banco local, sem SEFAZ)
            offset = nsu_inicial if nsu_inicial else 0

            limite = max(1, min(max_notas, 500))  # Entre 1 e 500
            resultado = supabase_admin.table("notas_fiscais")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .in_("tipo_nf", ["NFe", "NFCe"])\
                .order("data_emissao", desc=True)\
                .range(offset, offset + limite - 1)\
                .execute()

            # 2. Contar total de notas
            total_notas = 0
            try:
                count_result = supabase_admin.table("notas_fiscais")\
                    .select("id", count="exact")\
                    .eq("empresa_id", empresa_id)\
                    .in_("tipo_nf", ["NFe", "NFCe"])\
                    .execute()
                total_notas = count_result.count if hasattr(count_result, 'count') and count_result.count is not None else len(resultado.data or [])
            except Exception:
                total_notas = len(resultado.data or [])

            # 3. Converter para NFeBuscadaMetadata
            notas_encontradas = []

            if resultado.data:
                for row in resultado.data:
                    try:
                        # Determinar tipo_operacao (1=saida, 0=entrada)
                        tipo_op = row.get("tipo_operacao", "saida")
                        tipo_operacao_codigo = "1" if tipo_op == "saida" else "0"

                        # Parse data_emissao
                        data_str = row.get("data_emissao")
                        if data_str:
                            if isinstance(data_str, str):
                                data_emissao = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
                            else:
                                data_emissao = data_str
                        else:
                            data_emissao = datetime.now()

                        # Validar chave_acesso (deve ter 44 digitos)
                        chave_acesso = row.get("chave_acesso", "")
                        if not chave_acesso or len(chave_acesso) != 44 or not chave_acesso.isdigit():
                            logger.warning(f"Nota com chave invalida ignorada: {chave_acesso[:20]}...")
                            continue

                        # Normalizar cnpj_emitente (remover formatacao)
                        cnpj_emit = (row.get("cnpj_emitente") or "").replace(".", "").replace("/", "").replace("-", "")
                        if len(cnpj_emit) != 14:
                            cnpj_emit = cnpj_emit.ljust(14, "0")

                        cnpj_dest = self._normalizar_cnpj(row.get("cnpj_destinatario"))
                        cpf_dest = self._normalizar_cnpj(row.get("cpf_destinatario"))

                        nfe_metadata = NFeBuscadaMetadata(
                            chave_acesso=chave_acesso,
                            nsu=row.get("nsu", 0) or 0,
                            data_emissao=data_emissao,
                            tipo_operacao=tipo_operacao_codigo,
                            valor_total=Decimal(str(row.get("valor_total", 0))),
                            cnpj_emitente=cnpj_emit,
                            nome_emitente=row.get("nome_emitente", ""),
                            cnpj_destinatario=cnpj_dest if len(cnpj_dest) == 14 else None,
                            cpf_destinatario=cpf_dest if len(cpf_dest) == 11 else None,
                            nome_destinatario=row.get("nome_destinatario"),
                            situacao=row.get("situacao", "autorizada"),
                            situacao_codigo="1" if row.get("situacao") == "autorizada" else "3",
                            protocolo=row.get("protocolo"),
                            xml_resumo=row.get("xml_resumo") or row.get("xml_completo"),
                        )

                        notas_encontradas.append(nfe_metadata)

                    except Exception as e:
                        logger.warning(f"Nota ignorada por erro de conversao: {e}")
                        continue

            # 4. Calcular NSUs para paginacao
            ultimo_nsu = offset + len(notas_encontradas)
            max_nsu = total_notas

            # 5. Preparar resposta
            if notas_encontradas:
                status_codigo = "138"  # Sucesso
                motivo = f"Encontradas {len(notas_encontradas)} notas no banco de dados"
            else:
                status_codigo = "137"  # Nenhum documento
                motivo = (
                    "Nenhuma nota encontrada no banco de dados. "
                    "Importe XMLs usando /importar-xml ou /importar-lote"
                )

            response = DistribuicaoResponseModel(
                status_codigo=status_codigo,
                motivo=motivo,
                notas_encontradas=notas_encontradas,
                ultimo_nsu=ultimo_nsu,
                max_nsu=max_nsu,
                total_notas=len(notas_encontradas)
            )

            logger.info(
                f"[BUSCA LOCAL] Concluida: {len(notas_encontradas)} notas encontradas "
                f"(total no banco: {total_notas})"
            )

            return response

        except Exception as e:
            logger.error(f"[BUSCA LOCAL] Erro ao consultar banco: {e}", exc_info=True)
            # IMPORTANTE: NAO lancar SefazException aqui.
            # Retornar resposta vazia em vez de erro 502.
            from app.models.nfe_busca import DistribuicaoResponseModel
            return DistribuicaoResponseModel(
                status_codigo="137",
                motivo=f"Erro ao consultar banco de dados: {str(e)}. Tente novamente.",
                notas_encontradas=[],
                ultimo_nsu=0,
                max_nsu=0,
                total_notas=0
            )


    # ============================================
    # BACKGROUND TASKS (POLLING)
    # ============================================

    def executar_busca_assincrona(
        self,
        job_id: str,
        cnpj: str,
        empresa_id: str,
        nsu_inicial: Optional[int],
    ):
        """
        Wrapper para execucao assincrona via BackgroundTasks.
        Gerencia ciclo de vida do Job (processing -> completed/failed).

        IMPORTANTE: Esta busca consulta o BANCO DE DADOS local.
        Para novas notas, use /importar-xml ou /importar-lote.
        """
        from app.db.supabase_client import supabase_admin

        logger.info(f"[JOB] Iniciando Job {job_id} para empresa {empresa_id}")

        try:
            # 1. Atualizar status para PROCESSING
            supabase_admin.table("background_jobs").update({
                "status": "processing",
                "updated_at": datetime.now().isoformat()
            }).eq("id", job_id).execute()

            # 2. Executar busca no banco de dados (nunca lanca SefazException)
            response = self.buscar_notas_por_cnpj(
                cnpj=cnpj,
                empresa_id=empresa_id,
                nsu_inicial=nsu_inicial
            )

            # 3. Atualizar status para COMPLETED
            result_payload = {
                "success": response.status_codigo == "138",
                "total_notas": response.total_notas,
                "ultimo_nsu": response.ultimo_nsu,
                "max_nsu": response.max_nsu,
                "mensagem": response.motivo,
                "fonte": "banco_de_dados",
                "notas_resumo": [
                    {"chave": n.chave_acesso, "valor": float(n.valor_total)}
                    for n in response.notas_encontradas[:50]
                ]
            }

            supabase_admin.table("background_jobs").update({
                "status": "completed",
                "result": result_payload,
                "updated_at": datetime.now().isoformat()
            }).eq("id", job_id).execute()

            logger.info(f"[JOB] Job {job_id} concluido - {response.total_notas} notas")

        except Exception as e:
            logger.error(f"[JOB] Job {job_id} falhou: {e}", exc_info=True)

            try:
                supabase_admin.table("background_jobs").update({
                    "status": "failed",
                    "error": str(e),
                    "updated_at": datetime.now().isoformat()
                }).eq("id", job_id).execute()
            except Exception as db_err:
                logger.error(f"[JOB] Erro ao atualizar status do job: {db_err}")


# ============================================
# INSTÂNCIA SINGLETON
# ============================================

sefaz_service = SefazService()

