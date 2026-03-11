"""
Adapter para API de NFS-e da Prefeitura de Porto Alegre (ISSQN POA).

Portal: https://nfe.portoalegre.rs.gov.br
Código IBGE: 4314902 (Porto Alegre/RS)

Porto Alegre utiliza sistema próprio de NFS-e com Web Services SOAP
baseados no padrão ABRASF.
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


class PortoAlegreAdapter(BaseNFSeAdapter):
    """
    Adapter para API de NFS-e de Porto Alegre (ISSQN POA).

    Código IBGE: 4314902
    """

    SISTEMA_NOME = "Porto Alegre"
    MUNICIPIO_CODIGO_IBGE = "4314902"
    MUNICIPIO_NOME = "Porto Alegre"

    URL_PRODUCAO = "https://nfe.portoalegre.rs.gov.br/bhiss-ws/nfse"
    URL_HOMOLOGACAO = "https://nfehomologacao.portoalegre.rs.gov.br/bhiss-ws/nfse"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    async def autenticar(self) -> str:
        """POA usa autenticação por CNPJ + IM embutida no request."""
        self.token = self.credentials.get("senha", "")
        self.log_info("Credenciais ISSQN POA configuradas")
        return self.token

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """Busca NFS-e emitidas em Porto Alegre."""
        if not self.token:
            await self.autenticar()

        cnpj_limpo = self.limpar_cnpj(cnpj)
        if not self.validar_cnpj(cnpj_limpo):
            raise NFSeSearchException(f"CNPJ inválido: {cnpj}")

        try:
            soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                              xmlns:ws="http://ws.bhiss.pbh.gov.br">
                <soapenv:Body>
                    <ws:ConsultarNfseServicoPrestadoRequest>
                        <nfseCabecMsg><![CDATA[
                            <cabecalho xmlns="http://www.abrasf.org.br/nfse.xsd" versao="2.04">
                                <versaoDados>2.04</versaoDados>
                            </cabecalho>
                        ]]></nfseCabecMsg>
                        <nfseDadosMsg><![CDATA[
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
                        ]]></nfseDadosMsg>
                    </ws:ConsultarNfseServicoPrestadoRequest>
                </soapenv:Body>
            </soapenv:Envelope>"""

            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                response = await client.post(
                    self.base_url,
                    content=soap_body,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": "ConsultarNfseServicoPrestadoRequest",
                    },
                )

                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca POA: HTTP {response.status_code}",
                        detalhes=response.text[:500],
                    )

                notas = self.processar_resposta({"xml_response": response.text})
                self.log_info(f"{len(notas)} NFS-e encontradas em POA para CNPJ {cnpj_limpo}")
                return notas

        except NFSeSearchException:
            raise
        except httpx.TimeoutException:
            raise NFSeSearchException("Timeout ao buscar NFS-e em Porto Alegre.")
        except Exception as e:
            self.log_error(f"Erro na busca POA: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro ao buscar NFS-e em POA: {e}")

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """Processa resposta SOAP do ISSQN POA."""
        from lxml import etree

        notas = []
        xml_text = resposta.get("xml_response", "")
        if not xml_text:
            return notas

        try:
            root = etree.fromstring(xml_text.encode("utf-8"))

            for elem in root.iter():
                local = etree.QName(elem).localname if isinstance(elem.tag, str) else ""
                if local == "CompNfse":
                    nota = self._extrair_nota(elem)
                    if nota:
                        notas.append(nota)

        except Exception as e:
            self.log_error(f"Erro ao processar resposta POA: {e}")

        return notas

    def _extrair_nota(self, comp_elem) -> Dict:
        from lxml import etree

        def get_text(parent, tag):
            for elem in parent.iter():
                local = etree.QName(elem).localname if isinstance(elem.tag, str) else ""
                if local == tag and elem.text:
                    return elem.text.strip()
            return ""

        return self.criar_nota_padrao(
            numero=get_text(comp_elem, "Numero"),
            data_emissao=get_text(comp_elem, "DataEmissao"),
            valor_total=float(get_text(comp_elem, "ValorServicos") or 0),
            valor_servicos=float(get_text(comp_elem, "ValorServicos") or 0),
            valor_iss=float(get_text(comp_elem, "ValorIss") or 0),
            aliquota_iss=float(get_text(comp_elem, "Aliquota") or 0),
            cnpj_prestador=get_text(comp_elem, "Cnpj"),
            prestador_nome=get_text(comp_elem, "RazaoSocial"),
            descricao_servico=get_text(comp_elem, "Discriminacao"),
            codigo_servico=get_text(comp_elem, "ItemListaServico"),
            codigo_verificacao=get_text(comp_elem, "CodigoVerificacao"),
            municipio_codigo=self.MUNICIPIO_CODIGO_IBGE,
            municipio_nome=self.MUNICIPIO_NOME,
            status="Autorizada",
        )
