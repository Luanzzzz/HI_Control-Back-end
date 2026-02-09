"""
Adapter para API de NFS-e da Prefeitura do Rio de Janeiro (Nota Carioca).

Portal: https://notacarioca.rio.gov.br
Código IBGE: 3304557 (Rio de Janeiro/RJ)

O sistema Nota Carioca utiliza Web Services baseados no padrão ABRASF
com adaptações próprias da prefeitura do RJ.
"""
import httpx
from datetime import date
from typing import List, Dict
import logging

from app.services.nfse.base_adapter import (
    BaseNFSeAdapter,
    NFSeAuthException,
    NFSeSearchException,
)

logger = logging.getLogger(__name__)


class RioDeJaneiroAdapter(BaseNFSeAdapter):
    """
    Adapter para API de NFS-e do Rio de Janeiro (Nota Carioca).

    Código IBGE: 3304557
    """

    SISTEMA_NOME = "Rio de Janeiro"
    MUNICIPIO_CODIGO_IBGE = "3304557"
    MUNICIPIO_NOME = "Rio de Janeiro"

    URL_PRODUCAO = "https://notacarioca.rio.gov.br/WSNacional/nfse.asmx"
    URL_HOMOLOGACAO = "https://homologacao.notacarioca.rio.gov.br/WSNacional/nfse.asmx"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    async def autenticar(self) -> str:
        """Nota Carioca usa autenticação por CNPJ + senha no próprio request."""
        self.token = self.credentials.get("senha", "")
        self.log_info("Credenciais Nota Carioca configuradas")
        return self.token

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """Busca NFS-e emitidas no Rio de Janeiro."""
        if not self.token:
            await self.autenticar()

        cnpj_limpo = self.limpar_cnpj(cnpj)
        if not self.validar_cnpj(cnpj_limpo):
            raise NFSeSearchException(f"CNPJ inválido: {cnpj}")

        try:
            # Nota Carioca usa SOAP com envelope ABRASF
            soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                              xmlns:not="http://notacarioca.rio.gov.br/">
                <soapenv:Body>
                    <not:ConsultarNfseServicoPrestado>
                        <not:inputXML><![CDATA[
                            <ConsultarNfseServicoPrestadoEnvio xmlns="http://www.abrasf.org.br/nfse.xsd">
                                <Prestador>
                                    <CpfCnpj>
                                        <Cnpj>{cnpj_limpo}</Cnpj>
                                    </CpfCnpj>
                                    <InscricaoMunicipal>{self.credentials.get('usuario', '')}</InscricaoMunicipal>
                                </Prestador>
                                <PeriodoEmissao>
                                    <DataInicial>{data_inicio.strftime('%Y-%m-%d')}</DataInicial>
                                    <DataFinal>{data_fim.strftime('%Y-%m-%d')}</DataFinal>
                                </PeriodoEmissao>
                                <Pagina>1</Pagina>
                            </ConsultarNfseServicoPrestadoEnvio>
                        ]]></not:inputXML>
                    </not:ConsultarNfseServicoPrestado>
                </soapenv:Body>
            </soapenv:Envelope>"""

            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                response = await client.post(
                    self.base_url,
                    content=soap_body,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": "http://notacarioca.rio.gov.br/ConsultarNfseServicoPrestado",
                    },
                )

                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca RJ: HTTP {response.status_code}",
                        detalhes=response.text[:500],
                    )

                notas = self.processar_resposta({"xml_response": response.text})
                self.log_info(f"{len(notas)} NFS-e encontradas no RJ para CNPJ {cnpj_limpo}")
                return notas

        except NFSeSearchException:
            raise
        except httpx.TimeoutException:
            raise NFSeSearchException("Timeout ao buscar NFS-e no Rio de Janeiro.")
        except Exception as e:
            self.log_error(f"Erro na busca RJ: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro ao buscar NFS-e no RJ: {e}")

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """Processa resposta SOAP da Nota Carioca."""
        from lxml import etree

        notas = []
        xml_text = resposta.get("xml_response", "")
        if not xml_text:
            return notas

        try:
            root = etree.fromstring(xml_text.encode("utf-8"))
            ns = {"nfse": "http://www.abrasf.org.br/nfse.xsd"}

            for comp in root.iter():
                local = etree.QName(comp).localname if isinstance(comp.tag, str) else ""
                if local == "CompNfse":
                    nfse = comp.find(".//{http://www.abrasf.org.br/nfse.xsd}Nfse") or comp
                    inf = nfse.find(".//{http://www.abrasf.org.br/nfse.xsd}InfNfse") or nfse

                    nota = self.criar_nota_padrao(
                        numero=self._get_text(inf, "Numero", ns) or "",
                        data_emissao=self._get_text(inf, "DataEmissao", ns) or "",
                        valor_total=float(self._get_text(inf, "ValorServicos", ns) or 0),
                        valor_servicos=float(self._get_text(inf, "ValorServicos", ns) or 0),
                        valor_iss=float(self._get_text(inf, "ValorIss", ns) or 0),
                        aliquota_iss=float(self._get_text(inf, "Aliquota", ns) or 0),
                        cnpj_prestador=self._get_text(inf, "Cnpj", ns) or "",
                        prestador_nome=self._get_text(inf, "RazaoSocial", ns) or "",
                        descricao_servico=self._get_text(inf, "Discriminacao", ns) or "",
                        codigo_servico=self._get_text(inf, "ItemListaServico", ns) or "",
                        codigo_verificacao=self._get_text(inf, "CodigoVerificacao", ns) or "",
                        municipio_codigo=self.MUNICIPIO_CODIGO_IBGE,
                        municipio_nome=self.MUNICIPIO_NOME,
                        status="Autorizada",
                    )
                    notas.append(nota)

        except Exception as e:
            self.log_error(f"Erro ao processar resposta RJ: {e}")

        return notas

    def _get_text(self, parent, tag: str, ns: dict) -> str:
        if parent is None:
            return ""
        for prefix, uri in ns.items():
            elem = parent.find(f".//{{{uri}}}{tag}")
            if elem is not None and elem.text:
                return elem.text.strip()
        elem = parent.find(f".//{tag}")
        if elem is not None and elem.text:
            return elem.text.strip()
        return ""
