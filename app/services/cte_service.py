"""
Serviço para emissão de CT-e (Conhecimento de Transporte Eletrônico - Modelo 57).

Funcionalidades:
- Geração do XML CT-e (layout 4.00)
- Assinatura digital
- Autorização junto à SEFAZ
- Consulta de CT-e
- Cancelamento
- Geração de DACTE (via danfe_service)

O CT-e documenta prestações de serviço de transporte de cargas
(rodoviário, aéreo, aquaviário, ferroviário, dutoviário).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CTeService:
    """Serviço para operações com CT-e."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============================================
    # GERAÇÃO DE XML CT-e
    # ============================================

    def gerar_xml_cte(
        self,
        cte_data: dict,
        empresa: dict,
    ) -> str:
        """
        Gera XML do CT-e conforme layout 4.00.

        Args:
            cte_data: Dados do CT-e
            empresa: Dados da empresa emitente

        Returns:
            XML string do CT-e
        """
        from app.core.sefaz_config import UF_CODES

        # Dados básicos
        uf_code = UF_CODES.get(empresa.get("uf", "SP"), "35")
        cnpj = empresa.get("cnpj", "")
        modelo = "57"
        serie = cte_data.get("serie", "1")
        numero = cte_data.get("numero_ct", "1")
        data_emissao = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")
        ambiente = cte_data.get("ambiente", "2")

        # Gerar chave de acesso
        chave = self._gerar_chave_acesso(
            uf=uf_code,
            data=datetime.now(),
            cnpj=cnpj,
            modelo=modelo,
            serie=serie,
            numero=numero,
        )

        # Modal
        modal = cte_data.get("modal", "01")  # 01=Rodoviário
        tipo_cte = cte_data.get("tipo_cte", "0")  # 0=Normal
        tipo_servico = cte_data.get("tipo_servico", "0")  # 0=Normal

        # Remetente
        rem = cte_data.get("remetente", {})
        # Destinatário
        dest = cte_data.get("destinatario", {})
        # Valores
        valor_total = cte_data.get("valor_total_servico", "0.00")
        valor_receber = cte_data.get("valor_receber", valor_total)
        # Carga
        carga = cte_data.get("carga", {})
        # NF-e vinculadas
        nfe_vinculadas = cte_data.get("nfe_vinculadas", [])

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CTe xmlns="http://www.portalfiscal.inf.br/cte">
    <infCte versao="4.00" Id="CTe{chave}">
        <ide>
            <cUF>{uf_code}</cUF>
            <cCT>{chave[35:43]}</cCT>
            <CFOP>{cte_data.get('cfop', '5353')}</CFOP>
            <natOp>{cte_data.get('natureza_operacao', 'PRESTACAO DE SERVICO DE TRANSPORTE')}</natOp>
            <mod>{modelo}</mod>
            <serie>{serie}</serie>
            <nCT>{numero}</nCT>
            <dhEmi>{data_emissao}</dhEmi>
            <tpImp>1</tpImp>
            <tpEmis>1</tpEmis>
            <cDV>{chave[-1]}</cDV>
            <tpAmb>{ambiente}</tpAmb>
            <tpCTe>{tipo_cte}</tpCTe>
            <procEmi>0</procEmi>
            <verProc>HI-CONTROL1.0</verProc>
            <modal>{modal}</modal>
            <tpServ>{tipo_servico}</tpServ>
            <UFIni>{rem.get('uf', '')}</UFIni>
            <xMunIni>{rem.get('municipio', '')}</xMunIni>
            <cMunIni>{rem.get('codigo_municipio', '0000000')}</cMunIni>
            <UFFim>{dest.get('uf', '')}</UFFim>
            <xMunFim>{dest.get('municipio', '')}</xMunFim>
            <cMunFim>{dest.get('codigo_municipio', '0000000')}</cMunFim>
        </ide>
        <emit>
            <CNPJ>{cnpj}</CNPJ>
            <IE>{empresa.get('inscricao_estadual', '')}</IE>
            <xNome>{empresa.get('razao_social', '')}</xNome>
            <enderEmit>
                <xLgr>{empresa.get('logradouro', '')}</xLgr>
                <nro>{empresa.get('numero', 'SN')}</nro>
                <xBairro>{empresa.get('bairro', '')}</xBairro>
                <cMun>{empresa.get('codigo_municipio', '0000000')}</cMun>
                <xMun>{empresa.get('municipio', '')}</xMun>
                <CEP>{empresa.get('cep', '')}</CEP>
                <UF>{empresa.get('uf', '')}</UF>
            </enderEmit>
        </emit>
        <rem>
            <CNPJ>{rem.get('cnpj', '')}</CNPJ>
            <IE>{rem.get('ie', '')}</IE>
            <xNome>{rem.get('nome', '')}</xNome>
            <xFant>{rem.get('fantasia', '')}</xFant>
            <enderReme>
                <xLgr>{rem.get('logradouro', '')}</xLgr>
                <nro>{rem.get('numero', 'SN')}</nro>
                <xBairro>{rem.get('bairro', '')}</xBairro>
                <cMun>{rem.get('codigo_municipio', '0000000')}</cMun>
                <xMun>{rem.get('municipio', '')}</xMun>
                <CEP>{rem.get('cep', '')}</CEP>
                <UF>{rem.get('uf', '')}</UF>
            </enderReme>
        </rem>
        <dest>
            <CNPJ>{dest.get('cnpj', '')}</CNPJ>
            <IE>{dest.get('ie', '')}</IE>
            <xNome>{dest.get('nome', '')}</xNome>
            <enderDest>
                <xLgr>{dest.get('logradouro', '')}</xLgr>
                <nro>{dest.get('numero', 'SN')}</nro>
                <xBairro>{dest.get('bairro', '')}</xBairro>
                <cMun>{dest.get('codigo_municipio', '0000000')}</cMun>
                <xMun>{dest.get('municipio', '')}</xMun>
                <CEP>{dest.get('cep', '')}</CEP>
                <UF>{dest.get('uf', '')}</UF>
            </enderDest>
        </dest>
        <vPrest>
            <vTPrest>{valor_total}</vTPrest>
            <vRec>{valor_receber}</vRec>
        </vPrest>
        <imp>
            <ICMS>
                <ICMS00>
                    <CST>00</CST>
                    <vBC>{valor_total}</vBC>
                    <pICMS>{cte_data.get('aliquota_icms', '12.00')}</pICMS>
                    <vICMS>{cte_data.get('valor_icms', '0.00')}</vICMS>
                </ICMS00>
            </ICMS>
        </imp>
        <infCTeNorm>
            <infCarga>
                <vCarga>{carga.get('valor', '0.00')}</vCarga>
                <proPred>{carga.get('produto_predominante', 'MERCADORIAS EM GERAL')}</proPred>
                <infQ>
                    <cUnid>01</cUnid>
                    <tpMed>PESO BRUTO</tpMed>
                    <qCarga>{carga.get('quantidade', '0.0000')}</qCarga>
                </infQ>
            </infCarga>"""

        # NF-e vinculadas
        if nfe_vinculadas:
            xml += "\n            <infDoc>"
            for nfe in nfe_vinculadas:
                xml += f"""
                <infNFe>
                    <chave>{nfe.get('chave_acesso', '')}</chave>
                </infNFe>"""
            xml += "\n            </infDoc>"

        # Modal rodoviário
        if modal == "01":
            rodo = cte_data.get("rodoviario", {})
            xml += f"""
            <infModal versao="4.00">
                <rodo>
                    <RNTRC>{rodo.get('rntrc', empresa.get('rntrc', ''))}</RNTRC>
                </rodo>
            </infModal>"""

        xml += """
        </infCTeNorm>
    </infCte>
</CTe>"""

        return xml

    # ============================================
    # AUTORIZAÇÃO
    # ============================================

    async def autorizar_cte(
        self,
        cte_data: dict,
        empresa: dict,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> Dict[str, Any]:
        """
        Autoriza CT-e junto à SEFAZ.

        Args:
            cte_data: Dados do CT-e
            empresa: Dados da empresa emitente
            cert_bytes: Certificado A1 em bytes
            senha_cert: Senha do certificado

        Returns:
            Resultado da autorização
        """
        import httpx
        from app.core.cte_sefaz_config import obter_endpoints_cte

        uf = empresa.get("uf", "SP")
        endpoints = obter_endpoints_cte(uf)
        url = endpoints.get("autorizacao", "")

        try:
            # 1. Gerar XML
            xml_cte = self.gerar_xml_cte(cte_data, empresa)

            # 2. Assinar XML
            # TODO: usar adapter de assinatura (mesmo do NF-e)
            xml_assinado = xml_cte  # Placeholder - usar PyNFeAdapter

            logger.info(
                f"Autorizando CT-e {cte_data.get('numero_ct')} "
                f"série {cte_data.get('serie')} para {empresa.get('cnpj')}"
            )

            # 3. Enviar para SEFAZ
            headers = {
                "Content-Type": "application/soap+xml; charset=utf-8",
                "SOAPAction": '"autorizacao"',
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=xml_assinado.encode("utf-8"),
                    headers=headers,
                )

                if response.status_code == 200:
                    # Parsear resposta
                    result = self._parsear_resposta_cte(response.text)
                    return result

                return {
                    "autorizado": False,
                    "erro": f"HTTP {response.status_code}: {response.text[:200]}",
                }

        except Exception as e:
            logger.error(f"Erro ao autorizar CT-e: {e}", exc_info=True)
            return {
                "autorizado": False,
                "erro": str(e),
            }

    # ============================================
    # CONSULTA
    # ============================================

    async def consultar_cte(
        self,
        chave_acesso: str,
        uf: str,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> Dict[str, Any]:
        """Consulta CT-e por chave de acesso."""
        import httpx
        from app.core.cte_sefaz_config import obter_endpoints_cte

        endpoints = obter_endpoints_cte(uf)
        url = endpoints.get("consulta", "")

        xml_consulta = f"""<?xml version="1.0" encoding="UTF-8"?>
<consSitCTe versao="4.00" xmlns="http://www.portalfiscal.inf.br/cte">
    <tpAmb>2</tpAmb>
    <xServ>CONSULTAR</xServ>
    <chCTe>{chave_acesso}</chCTe>
</consSitCTe>"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=xml_consulta.encode("utf-8"),
                    headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                )

                if response.status_code == 200:
                    return self._parsear_resposta_cte(response.text)

                return {
                    "autorizado": False,
                    "erro": f"HTTP {response.status_code}",
                }

        except Exception as e:
            logger.error(f"Erro ao consultar CT-e: {e}")
            return {"autorizado": False, "erro": str(e)}

    # ============================================
    # CANCELAMENTO
    # ============================================

    async def cancelar_cte(
        self,
        chave_acesso: str,
        protocolo: str,
        motivo: str,
        cnpj: str,
        uf: str,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> Dict[str, Any]:
        """Cancela CT-e autorizado."""
        import httpx
        from app.core.cte_sefaz_config import obter_endpoints_cte

        endpoints = obter_endpoints_cte(uf)
        url = endpoints.get("evento", "")

        data_evento = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")

        xml_cancel = f"""<?xml version="1.0" encoding="UTF-8"?>
<eventoCTe xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">
    <infEvento Id="ID1101110{chave_acesso}01">
        <cOrgao>91</cOrgao>
        <tpAmb>2</tpAmb>
        <CNPJ>{cnpj}</CNPJ>
        <chCTe>{chave_acesso}</chCTe>
        <dhEvento>{data_evento}</dhEvento>
        <tpEvento>110111</tpEvento>
        <nSeqEvento>1</nSeqEvento>
        <detEvento versaoEvento="4.00">
            <evCancCTe>
                <descEvento>Cancelamento</descEvento>
                <nProt>{protocolo}</nProt>
                <xJust>{motivo}</xJust>
            </evCancCTe>
        </detEvento>
    </infEvento>
</eventoCTe>"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=xml_cancel.encode("utf-8"),
                    headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                )

                if response.status_code == 200:
                    return {
                        "cancelado": True,
                        "mensagem": "CT-e cancelado com sucesso",
                    }

                return {
                    "cancelado": False,
                    "erro": f"HTTP {response.status_code}",
                }

        except Exception as e:
            logger.error(f"Erro ao cancelar CT-e: {e}")
            return {"cancelado": False, "erro": str(e)}

    # ============================================
    # UTILITÁRIOS
    # ============================================

    def _gerar_chave_acesso(
        self,
        uf: str,
        data: datetime,
        cnpj: str,
        modelo: str,
        serie: str,
        numero: str,
    ) -> str:
        """Gera chave de acesso de 44 dígitos para CT-e."""
        import random

        aamm = data.strftime("%y%m")
        cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
        codigo = str(random.randint(10000000, 99999999))

        chave_sem_dv = (
            f"{uf.zfill(2)}"
            f"{aamm}"
            f"{cnpj_limpo.zfill(14)}"
            f"{modelo.zfill(2)}"
            f"{serie.zfill(3)}"
            f"{numero.zfill(9)}"
            f"1"  # tpEmis normal
            f"{codigo}"
        )

        # Calcular dígito verificador (módulo 11)
        dv = self._calcular_dv_mod11(chave_sem_dv)
        return f"{chave_sem_dv}{dv}"

    def _calcular_dv_mod11(self, chave: str) -> str:
        """Calcula dígito verificador módulo 11."""
        pesos = [2, 3, 4, 5, 6, 7, 8, 9]
        soma = 0
        for i, digito in enumerate(reversed(chave)):
            soma += int(digito) * pesos[i % len(pesos)]
        resto = soma % 11
        dv = 11 - resto
        if dv >= 10:
            dv = 0
        return str(dv)

    def _parsear_resposta_cte(self, xml_response: str) -> Dict[str, Any]:
        """Parseia resposta XML da SEFAZ CT-e."""
        try:
            from lxml import etree
            ns = "http://www.portalfiscal.inf.br/cte"

            root = etree.fromstring(xml_response.encode("utf-8"))

            # Tentar extrair status
            cstat = root.find(f".//{{{ns}}}cStat")
            xmotivo = root.find(f".//{{{ns}}}xMotivo")
            nprot = root.find(f".//{{{ns}}}nProt")
            chave = root.find(f".//{{{ns}}}chCTe")

            status = cstat.text if cstat is not None else "999"
            motivo = xmotivo.text if xmotivo is not None else "Resposta não parseada"
            protocolo = nprot.text if nprot is not None else ""
            chave_acesso = chave.text if chave is not None else ""

            autorizado = status == "100"

            return {
                "autorizado": autorizado,
                "status_codigo": status,
                "status_descricao": motivo,
                "protocolo": protocolo,
                "chave_acesso": chave_acesso,
            }

        except Exception as e:
            logger.error(f"Erro ao parsear resposta CT-e: {e}")
            return {
                "autorizado": False,
                "status_codigo": "999",
                "status_descricao": f"Erro ao processar resposta: {str(e)}",
            }


# Singleton
cte_service = CTeService()
