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
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
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
        self.ambiente = AMBIENTE_PADRAO  # "homologacao"
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

        Returns:
            SefazResponseModel com resultado da autorização

        Raises:
            SefazException: Em caso de erro
        """
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
    <tpAmb>{AMBIENTE_PADRAO == 'homologacao' and '2' or '1'}</tpAmb>
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
            <tpAmb>{AMBIENTE_PADRAO == 'homologacao' and '2' or '1'}</tpAmb>
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
        <tpAmb>{AMBIENTE_PADRAO == 'homologacao' and '2' or '1'}</tpAmb>
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
        from app.core.sefaz_config import (
            obter_endpoints_por_ambiente,
            obter_endpoint_distribuicao,
            AMBIENTE_PADRAO,
        )

        # DistribuicaoDFe e centralizado (Ambiente Nacional), nao por UF
        if operacao == "distribuicao":
            return obter_endpoint_distribuicao(AMBIENTE_PADRAO)

        endpoints_map = obter_endpoints_por_ambiente(AMBIENTE_PADRAO)

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

    # ============================================
    # BUSCA DE NOTAS (BANCO DE DADOS LOCAL)
    # ============================================

    def buscar_notas_por_cnpj(
        self,
        cnpj: str,
        empresa_id: str,
        nsu_inicial: Optional[int] = None,
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
        from app.db.supabase_client import supabase_admin

        logger.info(
            f"[BUSCA LOCAL] Buscando notas no banco de dados | "
            f"Empresa: {empresa_id} | CNPJ: {cnpj}"
        )

        try:
            # 1. Consultar banco de dados (APENAS banco local, sem SEFAZ)
            offset = nsu_inicial if nsu_inicial else 0

            resultado = supabase_admin.table("notas_fiscais")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .order("data_emissao", desc=True)\
                .range(offset, offset + 49)\
                .execute()

            # 2. Contar total de notas
            total_notas = 0
            try:
                count_result = supabase_admin.table("notas_fiscais")\
                    .select("id", count="exact")\
                    .eq("empresa_id", empresa_id)\
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

                        nfe_metadata = NFeBuscadaMetadata(
                            chave_acesso=chave_acesso,
                            nsu=row.get("nsu", 0) or 0,
                            data_emissao=data_emissao,
                            tipo_operacao=tipo_operacao_codigo,
                            valor_total=Decimal(str(row.get("valor_total", 0))),
                            cnpj_emitente=cnpj_emit,
                            nome_emitente=row.get("nome_emitente", ""),
                            cnpj_destinatario=row.get("cnpj_destinatario"),
                            cpf_destinatario=row.get("cpf_destinatario"),
                            nome_destinatario=row.get("nome_destinatario"),
                            situacao=row.get("situacao", "autorizada"),
                            situacao_codigo="1" if row.get("situacao") == "autorizada" else "2" if row.get("situacao") == "denegada" else "3",
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

