"""
Serviço de emissão de NFS-e no padrão Nacional (Lei Complementar nº 214/2025).

Implementa emissão de NFS-e através do SEFIN Nacional, seguindo o padrão
ABRASF 2.04 com os novos tributos IBS e CBS obrigatórios desde 01/01/2026.

Portal: https://www.gov.br/nfse
SEFIN Produção: https://sefin.nfse.gov.br/SefinNacional
SEFIN Homologação: https://sefin.producaorestrita.nfse.gov.br/SefinNacional

Referência: backend/NFSE_NACIONAL_API_REFERENCE.md
"""
import httpx
import gzip
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from lxml import etree

logger = logging.getLogger(__name__)


class NFSeNacionalService:
    """
    Serviço para emissão de NFS-e no padrão nacional (SEFIN).

    Implementa:
    - Montagem do DPS (Documento Padrão de Serviço)
    - Emissão via POST /nfse (síncrono)
    - Consulta por chave GET /nfse/{chave}
    - Autenticação mTLS com certificado A1
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # Namespace XML ABRASF
    NS_ABRASF = "http://www.abrasf.org.br/nfse"

    def _obter_url_base(self, ambiente: str) -> str:
        """Obtém URL base do SEFIN a partir do config centralizado."""
        from app.core.config import settings
        return (
            settings.NFSE_SEFIN_URL_PRODUCAO if ambiente == "producao"
            else settings.NFSE_SEFIN_URL_HOMOLOGACAO
        )

    # ============================================
    # BUILDER DO DPS
    # ============================================

    def montar_dps(
        self,
        dados_emissao: Dict[str, Any],
        empresa: Dict[str, Any],
        ambiente: str = "homologacao"
    ) -> str:
        """
        Monta DPS (Documento Padrão de Serviço) em XML.

        Args:
            dados_emissao: Dados da nota fiscal a ser emitida
                - tomador: dict com dados do cliente
                - servico: dict com descrição, valor, códigos
                - tributos: dict com IBS, CBS, ISS (opcional se zerados)
            empresa: Dados do prestador
                - cnpj, inscricao_municipal, razao_social, endereco
            ambiente: "producao" ou "homologacao"

        Returns:
            XML do DPS como string

        Raises:
            ValueError: Se campos obrigatórios estiverem faltando
        """
        # Validar campos obrigatórios
        self._validar_dados_emissao(dados_emissao, empresa)

        # Ambiente: 1=Produção, 2=Homologação
        tp_amb = "1" if ambiente == "producao" else "2"

        # Data/hora de emissão
        dh_emi = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")

        # Extrair dados
        tomador = dados_emissao.get("tomador", {})
        servico = dados_emissao.get("servico", {})
        tributos = dados_emissao.get("tributos", {})
        valores = dados_emissao.get("valores", {})

        # Gerar ID do DPS (pode ser usado para rastreamento)
        dps_id = f"DPS{empresa['cnpj']}{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Construir XML
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<DPS xmlns="{self.NS_ABRASF}">
  <InfDPS Id="{dps_id}">
    <tpAmb>{tp_amb}</tpAmb>
    <dhEmi>{dh_emi}</dhEmi>

    <!-- Prestador -->
    <prest>
      <CNPJ>{self._limpar_cnpj(empresa['cnpj'])}</CNPJ>
      <IM>{empresa.get('inscricao_municipal', '')}</IM>
      <xNome>{self._xml_escape(empresa.get('razao_social', ''))}</xNome>
    </prest>

    <!-- Tomador -->
    <toma>
      {self._xml_documento_tomador(tomador)}
      <xNome>{self._xml_escape(tomador.get('nome', tomador.get('razao_social', '')))}</xNome>
      {self._xml_endereco_tomador(tomador)}
    </toma>

    <!-- Serviço -->
    <serv>
      <cServ>
        <cTribNac>{servico.get('codigo_tributacao_nacional', '01.01')}</cTribNac>
      </cServ>
      <xServ>{self._xml_escape(servico.get('discriminacao', ''))}</xServ>
      <vServ>{self._formatar_valor(servico.get('valor_servicos', 0))}</vServ>
      <vDesc>{self._formatar_valor(servico.get('valor_desconto', 0))}</vDesc>
      <vBC>{self._formatar_valor(servico.get('valor_base_calculo', servico.get('valor_servicos', 0)))}</vBC>

      <!-- Tributos -->
      <trib>
        {self._xml_tributos(tributos, servico)}
      </trib>
    </serv>

    <!-- Valores Totais -->
    <valores>
      <vServPrest>{self._formatar_valor(valores.get('valor_servicos', servico.get('valor_servicos', 0)))}</vServPrest>
      <vDesc>{self._formatar_valor(valores.get('valor_desconto', servico.get('valor_desconto', 0)))}</vDesc>
      <vLiq>{self._formatar_valor(valores.get('valor_liquido', servico.get('valor_servicos', 0)))}</vLiq>
    </valores>
  </InfDPS>
</DPS>'''

        # Validar XML gerado
        try:
            etree.fromstring(xml.encode('utf-8'))
            logger.debug("DPS montado e validado com sucesso")
        except etree.XMLSyntaxError as e:
            logger.error(f"XML DPS mal formado: {e}")
            raise ValueError(f"Erro ao montar DPS: XML inválido - {e}")

        return xml

    def _xml_documento_tomador(self, tomador: Dict) -> str:
        """Gera tag CPF ou CNPJ do tomador."""
        cpf = tomador.get('cpf')
        cnpj = tomador.get('cnpj')

        if cnpj:
            return f"<CNPJ>{self._limpar_cnpj(cnpj)}</CNPJ>"
        elif cpf:
            return f"<CPF>{self._limpar_cpf(cpf)}</CPF>"
        else:
            # Tomador pode ser omitido em alguns casos, mas preferível ter CPF/CNPJ
            logger.warning("Tomador sem CPF/CNPJ informado")
            return ""

    def _xml_endereco_tomador(self, tomador: Dict) -> str:
        """Gera bloco de endereço do tomador."""
        endereco = tomador.get('endereco', {})

        if not endereco:
            return ""

        return f'''<end>
        <xLgr>{self._xml_escape(endereco.get('logradouro', ''))}</xLgr>
        <nro>{endereco.get('numero', 'SN')}</nro>
        <xBairro>{self._xml_escape(endereco.get('bairro', ''))}</xBairro>
        <cMun>{endereco.get('codigo_municipio', '')}</cMun>
        <xMun>{self._xml_escape(endereco.get('municipio', ''))}</xMun>
        <UF>{endereco.get('uf', '')}</UF>
        <CEP>{self._limpar_cep(endereco.get('cep', ''))}</CEP>
      </end>'''

    def _xml_tributos(self, tributos: Dict, servico: Dict) -> str:
        """
        Gera bloco de tributos (IBS, CBS, ISS).

        IBS e CBS são obrigatórios desde 2026 (mesmo que zerados).
        """
        ibs = tributos.get('ibs', {})
        cbs = tributos.get('cbs', {})
        iss = tributos.get('iss', {})

        # Base de cálculo padrão
        valor_base = servico.get('valor_base_calculo', servico.get('valor_servicos', 0))

        # IBS - Imposto sobre Bens e Serviços
        vbc_ibs = ibs.get('valor_base_calculo', valor_base)
        p_ibs = ibs.get('aliquota', 0)
        v_ibs = ibs.get('valor', vbc_ibs * p_ibs / 100 if p_ibs > 0 else 0)

        # CBS - Contribuição sobre Bens e Serviços
        vbc_cbs = cbs.get('valor_base_calculo', valor_base)
        p_cbs = cbs.get('aliquota', 0)
        v_cbs = cbs.get('valor', vbc_cbs * p_cbs / 100 if p_cbs > 0 else 0)

        # ISS - Imposto Sobre Serviços (mantido para compatibilidade)
        vbc_iss = iss.get('valor_base_calculo', valor_base)
        p_iss = iss.get('aliquota', 0)
        v_iss = iss.get('valor', vbc_iss * p_iss / 100 if p_iss > 0 else 0)
        c_mun_incid = iss.get('codigo_municipio_incidencia', servico.get('codigo_municipio', ''))

        xml_tributos = f'''<IBS>
          <vBCIBS>{self._formatar_valor(vbc_ibs)}</vBCIBS>
          <pIBS>{self._formatar_valor(p_ibs)}</pIBS>
          <vIBS>{self._formatar_valor(v_ibs)}</vIBS>
        </IBS>
        <CBS>
          <vBCCBS>{self._formatar_valor(vbc_cbs)}</vBCCBS>
          <pCBS>{self._formatar_valor(p_cbs)}</pCBS>
          <vCBS>{self._formatar_valor(v_cbs)}</vCBS>
        </CBS>'''

        # ISS opcional (incluir se houver alíquota ou município)
        if p_iss > 0 or c_mun_incid:
            xml_tributos += f'''
        <ISS>
          <vBC>{self._formatar_valor(vbc_iss)}</vBC>
          <pISSQN>{self._formatar_valor(p_iss)}</pISSQN>
          <vISSQN>{self._formatar_valor(v_iss)}</vISSQN>
          <cMunIncid>{c_mun_incid}</cMunIncid>
        </ISS>'''

        return xml_tributos

    # ============================================
    # EMISSÃO
    # ============================================

    async def emitir_nfse(
        self,
        dps_xml: str,
        cert_path: str,
        cert_password: str,
        ambiente: str = "homologacao",
        empresa_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Emite NFS-e Nacional via SEFIN (síncrono).

        Args:
            dps_xml: XML do DPS montado
            cert_path: Caminho do certificado A1 (.pfx)
            cert_password: Senha do certificado
            ambiente: "producao" ou "homologacao"
            empresa_id: ID da empresa (para auditoria)

        Returns:
            {
                "sucesso": bool,
                "chave_acesso": str,
                "numero_nfse": str,
                "protocolo": str,
                "xml_nfse": str,
                "mensagem": str
            }

        Raises:
            httpx.HTTPError: Erro na comunicação
            ValueError: Resposta inválida
        """
        # Proteção contra emissão acidental
        from app.utils.emission_guard import verificar_permissao_emissao
        verificar_permissao_emissao(
            empresa_id=empresa_id or "nfse-nacional",
            tipo_documento="NFSe"
        )

        base_url = self._obter_url_base(ambiente)
        url_emissao = f"{base_url}/nfse"

        logger.info(f"Emitindo NFS-e Nacional via {base_url}")

        try:
            # CORREÇÃO SSL: Converter PFX para PEM para mTLS
            # httpx.AsyncClient exige certificado em formato PEM, não PFX
            from app.services.certificado_service import certificado_service
            import tempfile
            import os as os_module

            # Ler arquivo PFX
            with open(cert_path, 'rb') as f:
                pfx_bytes = f.read()

            # Converter PFX → PEM
            cert_pem, key_pem = certificado_service.pfx_para_pem(pfx_bytes, cert_password)

            # Criar arquivos temporários PEM
            cert_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            key_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')

            try:
                # Escrever PEM em arquivos temporários
                cert_pem_file.write(cert_pem)
                cert_pem_file.flush()
                cert_pem_path = cert_pem_file.name

                key_pem_file.write(key_pem)
                key_pem_file.flush()
                key_pem_path = key_pem_file.name

                cert_pem_file.close()
                key_pem_file.close()

                # Cliente HTTP com mTLS usando certificado PEM
                async with httpx.AsyncClient(
                    cert=(cert_pem_path, key_pem_path),
                    verify=True,
                    timeout=30.0
                ) as client:
                    # Log da requisição para debug
                    logger.info(f"POST {url_emissao}")
                    logger.debug(f"XML DPS (primeiros 500 chars): {dps_xml[:500]}")

                    # TENTATIVA 1: Enviar como JSON com XML em base64 (SEM gzip)
                    # SEFIN retorna E1226 "Estrutura descompactada mal formada" com gzip
                    import json

                    xml_bytes = dps_xml.encode('utf-8')

                    # Base64 do XML (sem compressão gzip)
                    xml_base64 = base64.b64encode(xml_bytes).decode('utf-8')

                    payload_json = {
                        "dps": xml_base64,
                        "tpAmb": "2" if ambiente == "homologacao" else "1"
                    }

                    logger.debug(f"Payload JSON size: {len(json.dumps(payload_json))} bytes")
                    logger.debug(f"DPS base64 length: {len(xml_base64)} chars")

                    response = await client.post(
                        url_emissao,
                        json=payload_json,  # httpx auto-seta Content-Type: application/json
                        headers={
                            "Accept": "application/json"
                        }
                    )

                    # Processar resposta
                    return self._processar_resposta_emissao(response)

            finally:
                # SEMPRE limpar arquivos temporários (contêm chave privada!)
                try:
                    os_module.unlink(cert_pem_path)
                except:
                    pass
                try:
                    os_module.unlink(key_pem_path)
                except:
                    pass

        except httpx.TimeoutException as e:
            logger.error(f"Timeout ao emitir NFS-e: {e}")
            return {
                "sucesso": False,
                "mensagem": "Timeout ao conectar com SEFIN Nacional. Tente novamente.",
                "erro": str(e)
            }

        except httpx.HTTPError as e:
            logger.error(f"Erro HTTP ao emitir NFS-e: {e}")
            return {
                "sucesso": False,
                "mensagem": f"Erro de rede ao emitir NFS-e: {e}",
                "erro": str(e)
            }

        except Exception as e:
            logger.error(f"Erro inesperado ao emitir NFS-e: {e}", exc_info=True)
            return {
                "sucesso": False,
                "mensagem": f"Erro inesperado: {e}",
                "erro": str(e)
            }

    def _processar_resposta_emissao(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Processa resposta HTTP da emissão.

        Status HTTP possíveis:
        - 200: Sucesso
        - 400: Erro no DPS
        - 401: Falha autenticação
        - 422: Validação de negócio falhou
        - 500: Erro interno
        """
        status = response.status_code

        # Log completo da resposta para debug
        logger.info(f"Response status: {status}")
        logger.info(f"Response body: {response.text[:1000]}")

        if status == 200:
            # Sucesso - parsear JSON ou XML da NFS-e
            return self._parsear_nfse_retornada(response.content)

        elif status == 400:
            return {
                "sucesso": False,
                "mensagem": "Erro na estrutura do DPS (XML inválido)",
                "detalhes": response.text,  # Mensagem completa do SEFIN
                "codigo_http": 400
            }

        elif status == 401:
            return {
                "sucesso": False,
                "mensagem": "Falha na autenticação mTLS (certificado inválido ou expirado)",
                "detalhes": response.text,
                "codigo_http": 401
            }

        elif status == 422:
            # Validação de negócio (ex: duplicidade, dados inconsistentes)
            return {
                "sucesso": False,
                "mensagem": "Validação de negócio falhou",
                "detalhes": response.text,
                "codigo_http": 422
            }

        elif status >= 500:
            return {
                "sucesso": False,
                "mensagem": f"Erro interno do SEFIN Nacional (HTTP {status})",
                "detalhes": response.text,
                "codigo_http": status
            }

        else:
            return {
                "sucesso": False,
                "mensagem": f"Resposta inesperada do SEFIN (HTTP {status})",
                "detalhes": response.text,
                "codigo_http": status
            }

    def _parsear_nfse_retornada(self, xml_bytes: bytes) -> Dict[str, Any]:
        """
        Parseia XML da NFS-e retornada.

        Pode vir em formato:
        - XML puro
        - GZIP + Base64 (precisa decodificar)
        """
        try:
            # Tentar decodificar se for Base64+GZIP
            xml_string = self._decodificar_xml_resposta(xml_bytes)

            # Parsear XML
            root = etree.fromstring(xml_string.encode('utf-8'))

            # Extrair dados (estrutura pode variar)
            chave_acesso = self._extrair_campo_xml(root, ".//chNFSe")
            numero_nfse = self._extrair_campo_xml(root, ".//nNFSe")
            protocolo = self._extrair_campo_xml(root, ".//nProt")

            logger.info(f"NFS-e emitida com sucesso: {numero_nfse} (chave: {chave_acesso})")

            return {
                "sucesso": True,
                "chave_acesso": chave_acesso,
                "numero_nfse": numero_nfse,
                "protocolo": protocolo,
                "xml_nfse": xml_string,
                "mensagem": "NFS-e emitida com sucesso"
            }

        except Exception as e:
            logger.error(f"Erro ao parsear resposta da emissão: {e}")
            return {
                "sucesso": False,
                "mensagem": f"Erro ao processar resposta da SEFIN: {e}",
                "xml_raw": xml_bytes.decode('utf-8', errors='ignore')
            }

    # ============================================
    # CONSULTA
    # ============================================

    async def consultar_nfse_por_chave(
        self,
        chave_acesso: str,
        cert_path: str,
        cert_password: str,
        ambiente: str = "homologacao"
    ) -> Dict[str, Any]:
        """
        Consulta NFS-e por chave de acesso (44 dígitos).

        Args:
            chave_acesso: Chave de 44 dígitos
            cert_path: Caminho do certificado A1
            cert_password: Senha do certificado
            ambiente: "producao" ou "homologacao"

        Returns:
            {
                "encontrada": bool,
                "xml_nfse": str,
                "mensagem": str
            }
        """
        base_url = self._obter_url_base(ambiente)
        url_consulta = f"{base_url}/nfse/{chave_acesso}"

        logger.info(f"Consultando NFS-e chave {chave_acesso}")

        try:
            # CORREÇÃO SSL: Converter PFX para PEM
            from app.services.certificado_service import certificado_service
            import tempfile
            import os as os_module

            with open(cert_path, 'rb') as f:
                pfx_bytes = f.read()

            cert_pem, key_pem = certificado_service.pfx_para_pem(pfx_bytes, cert_password)

            cert_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            key_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')

            try:
                cert_pem_file.write(cert_pem)
                cert_pem_file.flush()
                cert_pem_path = cert_pem_file.name

                key_pem_file.write(key_pem)
                key_pem_file.flush()
                key_pem_path = key_pem_file.name

                cert_pem_file.close()
                key_pem_file.close()

                async with httpx.AsyncClient(
                    cert=(cert_pem_path, key_pem_path),
                    verify=True,
                    timeout=30.0
                ) as client:
                    response = await client.get(
                        url_consulta,
                        headers={"Accept": "application/xml"}
                    )

                    if response.status_code == 200:
                        xml_string = self._decodificar_xml_resposta(response.content)
                        return {
                            "encontrada": True,
                            "xml_nfse": xml_string,
                            "mensagem": "NFS-e encontrada"
                        }

                    elif response.status_code == 404:
                        return {
                            "encontrada": False,
                            "mensagem": "NFS-e não encontrada"
                        }

                    else:
                        return {
                            "encontrada": False,
                            "mensagem": f"Erro ao consultar: HTTP {response.status_code}",
                            "detalhes": response.text
                        }

            finally:
                # Limpar arquivos temporários
                try:
                    os_module.unlink(cert_pem_path)
                except:
                    pass
                try:
                    os_module.unlink(key_pem_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Erro ao consultar NFS-e: {e}")
            return {
                "encontrada": False,
                "mensagem": f"Erro na consulta: {e}",
                "erro": str(e)
            }

    # ============================================
    # CANCELAMENTO
    # ============================================

    async def cancelar_nfse(
        self,
        chave_acesso: str,
        motivo: str,
        cert_path: str,
        cert_password: str,
        ambiente: str = "homologacao"
    ) -> Dict[str, Any]:
        """
        Cancela NFS-e Nacional.

        STATUS: NÃO IMPLEMENTADO NO ENDPOINT PRINCIPAL
        ================================================

        Esta implementação de serviço tenta fazer cancelamento via API,
        mas o endpoint REST do projeto (POST /nacional/{chave}/cancelar)
        está desabilitado com HTTP 501 pois:

        1. Endpoint de cancelamento SEFIN não confirmado na documentação acessível
        2. Requer confirmação de que a API SEFIN aceita cancelamentos via mTLS
        3. Comportamento esperado: Cancelamento via portal gov.br

        QUANDO IMPLEMENTAR (próximas versões):
        - Confirmar endpoint de cancelamento com Receita Federal
        - Validar estrutura XML de evento de cancelamento
        - Testar em ambiente de homologação do SEFIN
        - Re-habilitar endpoint REST com flag de feature

        Referência:
        https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica

        Args:
            chave_acesso: Chave de 44 dígitos
            motivo: Justificativa do cancelamento (mínimo 15 caracteres)
            cert_path: Caminho do certificado A1
            cert_password: Senha do certificado
            ambiente: "producao" ou "homologacao"

        Returns:
            {
                "cancelada": bool,
                "protocolo": str (se sucesso),
                "mensagem": str
            }
        """
        if len(motivo) < 15:
            return {
                "cancelada": False,
                "mensagem": "Motivo do cancelamento deve ter no mínimo 15 caracteres"
            }

        logger.warning(
            "⚠️ Endpoint de cancelamento não confirmado. "
            "Tentando abordagem baseada em eventos ABRASF."
        )

        base_url = self._obter_url_base(ambiente)

        # Tentativa 1: Evento de cancelamento (padrão ABRASF)
        url_evento = f"{base_url}/nfse/{chave_acesso}/evento"

        # XML de evento de cancelamento
        evento_xml = self._montar_evento_cancelamento(chave_acesso, motivo)

        try:
            # CORREÇÃO SSL: Converter PFX para PEM
            from app.services.certificado_service import certificado_service
            import tempfile
            import os as os_module

            with open(cert_path, 'rb') as f:
                pfx_bytes = f.read()

            cert_pem, key_pem = certificado_service.pfx_para_pem(pfx_bytes, cert_password)

            cert_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            key_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')

            try:
                cert_pem_file.write(cert_pem)
                cert_pem_file.flush()
                cert_pem_path = cert_pem_file.name

                key_pem_file.write(key_pem)
                key_pem_file.flush()
                key_pem_path = key_pem_file.name

                cert_pem_file.close()
                key_pem_file.close()

                async with httpx.AsyncClient(
                    cert=(cert_pem_path, key_pem_path),
                    verify=True,
                    timeout=30.0
                ) as client:
                    response = await client.post(
                        url_evento,
                        content=evento_xml.encode('utf-8'),
                        headers={"Content-Type": "application/xml"}
                    )

                    if response.status_code == 200:
                        # Sucesso
                        root = etree.fromstring(response.content)
                        protocolo = self._extrair_campo_xml(root, ".//nProt")

                        logger.info(f"NFS-e {chave_acesso} cancelada (protocolo: {protocolo})")

                        return {
                            "cancelada": True,
                            "protocolo": protocolo,
                            "mensagem": "NFS-e cancelada com sucesso"
                        }

                    elif response.status_code == 404:
                        # Endpoint não encontrado - tentar URL alternativa
                        logger.warning("Endpoint /evento não encontrado, tentando /cancelar")
                        return await self._tentar_cancelamento_alternativo(
                            chave_acesso, motivo, cert_path, cert_password, base_url
                        )

                    else:
                        return {
                            "cancelada": False,
                            "mensagem": f"Falha no cancelamento: HTTP {response.status_code}",
                            "detalhes": response.text,
                            "orientacao": "Tente cancelar via portal https://www.gov.br/nfse"
                        }

            finally:
                # Limpar arquivos temporários
                try:
                    os_module.unlink(cert_pem_path)
                except:
                    pass
                try:
                    os_module.unlink(key_pem_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Erro ao cancelar NFS-e: {e}")
            return {
                "cancelada": False,
                "mensagem": f"Erro no cancelamento: {e}",
                "orientacao": "Tente cancelar via portal https://www.gov.br/nfse"
            }

    async def _tentar_cancelamento_alternativo(
        self,
        chave_acesso: str,
        motivo: str,
        cert_path: str,
        cert_password: str,
        base_url: str
    ) -> Dict[str, Any]:
        """Tenta endpoint alternativo de cancelamento."""
        url_cancelar = f"{base_url}/nfse/{chave_acesso}/cancelar"

        payload = {
            "motivo": motivo
        }

        try:
            # CORREÇÃO SSL: Converter PFX para PEM
            from app.services.certificado_service import certificado_service
            import tempfile
            import os as os_module

            with open(cert_path, 'rb') as f:
                pfx_bytes = f.read()

            cert_pem, key_pem = certificado_service.pfx_para_pem(pfx_bytes, cert_password)

            cert_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            key_pem_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')

            try:
                cert_pem_file.write(cert_pem)
                cert_pem_file.flush()
                cert_pem_path = cert_pem_file.name

                key_pem_file.write(key_pem)
                key_pem_file.flush()
                key_pem_path = key_pem_file.name

                cert_pem_file.close()
                key_pem_file.close()

                async with httpx.AsyncClient(
                    cert=(cert_pem_path, key_pem_path),
                    verify=True,
                    timeout=30.0
                ) as client:
                    response = await client.post(
                        url_cancelar,
                        json=payload
                    )

                    if response.status_code == 200:
                        return {
                            "cancelada": True,
                            "mensagem": "NFS-e cancelada via endpoint alternativo"
                        }
                    else:
                        return {
                            "cancelada": False,
                            "mensagem": "Endpoint de cancelamento não disponível via API",
                            "orientacao": "Cancele via portal: https://www.gov.br/nfse"
                        }

            finally:
                # Limpar arquivos temporários
                try:
                    os_module.unlink(cert_pem_path)
                except:
                    pass
                try:
                    os_module.unlink(key_pem_path)
                except:
                    pass

        except Exception as e:
            return {
                "cancelada": False,
                "mensagem": f"Cancelamento via API não disponível: {e}",
                "orientacao": "Cancele via portal: https://www.gov.br/nfse"
            }

    def _montar_evento_cancelamento(self, chave_acesso: str, motivo: str) -> str:
        """Monta XML de evento de cancelamento (padrão ABRASF)."""
        dh_evento = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<evento xmlns="{self.NS_ABRASF}" versao="1.00">
  <infEvento>
    <chNFSe>{chave_acesso}</chNFSe>
    <dhEvento>{dh_evento}</dhEvento>
    <tpEvento>101</tpEvento>
    <nSeqEvento>1</nSeqEvento>
    <detEvento versao="1.00">
      <descEvento>Cancelamento</descEvento>
      <xJust>{self._xml_escape(motivo)}</xJust>
    </detEvento>
  </infEvento>
</evento>'''

    # ============================================
    # UTILITÁRIOS
    # ============================================

    def _validar_dados_emissao(self, dados_emissao: Dict, empresa: Dict):
        """Valida campos obrigatórios antes de montar DPS."""
        erros = []

        # Empresa
        if not empresa.get('cnpj'):
            erros.append("CNPJ do prestador é obrigatório")
        if not empresa.get('razao_social'):
            erros.append("Razão social do prestador é obrigatória")

        # Tomador
        tomador = dados_emissao.get('tomador', {})
        if not tomador:
            erros.append("Dados do tomador são obrigatórios")
        elif not tomador.get('cnpj') and not tomador.get('cpf'):
            erros.append("CPF ou CNPJ do tomador é obrigatório")

        # Serviço
        servico = dados_emissao.get('servico', {})
        if not servico:
            erros.append("Dados do serviço são obrigatórios")
        elif not servico.get('discriminacao'):
            erros.append("Discriminação do serviço é obrigatória")
        elif not servico.get('valor_servicos'):
            erros.append("Valor dos serviços é obrigatório")

        if erros:
            raise ValueError("Validação falhou: " + "; ".join(erros))

    def _decodificar_xml_resposta(self, xml_bytes: bytes) -> str:
        """
        Decodifica XML que pode estar em Base64+GZIP.

        Tenta:
        1. Decodificar Base64 + descomprimir GZIP
        2. Apenas descomprimir GZIP
        3. Usar XML puro
        """
        try:
            # Tentar Base64 + GZIP
            decoded = base64.b64decode(xml_bytes)
            decompressed = gzip.decompress(decoded)
            return decompressed.decode('utf-8')
        except:
            pass

        try:
            # Tentar apenas GZIP
            decompressed = gzip.decompress(xml_bytes)
            return decompressed.decode('utf-8')
        except:
            pass

        # XML puro
        return xml_bytes.decode('utf-8')

    def _extrair_campo_xml(self, root: etree.Element, xpath: str) -> str:
        """Extrai campo XML usando XPath (com namespace)."""
        try:
            namespaces = {'nfse': self.NS_ABRASF}
            element = root.find(xpath, namespaces)
            if element is not None:
                return element.text or ""
            # Tentar sem namespace
            element = root.find(xpath)
            return element.text if element is not None else ""
        except:
            return ""

    def _formatar_valor(self, valor: float) -> str:
        """Formata valor monetário com 2 casas decimais."""
        return f"{float(valor):.2f}"

    def _limpar_cnpj(self, cnpj: str) -> str:
        """Remove formatação do CNPJ."""
        return ''.join(filter(str.isdigit, cnpj))

    def _limpar_cpf(self, cpf: str) -> str:
        """Remove formatação do CPF."""
        return ''.join(filter(str.isdigit, cpf))

    def _limpar_cep(self, cep: str) -> str:
        """Remove formatação do CEP."""
        return ''.join(filter(str.isdigit, cep))

    def _xml_escape(self, texto: str) -> str:
        """Escapa caracteres especiais para XML."""
        if not texto:
            return ""
        return (texto
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))


# Singleton
nfse_nacional_service = NFSeNacionalService()
