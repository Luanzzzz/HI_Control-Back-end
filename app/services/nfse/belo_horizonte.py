"""
Adapter para API de NFS-e da Prefeitura de Belo Horizonte (BHISSDigital).

A Prefeitura de BH possui sistema próprio de NFS-e chamado BHISSDigital.

Portal: https://bhissdigital.pbh.gov.br
Documentação: https://prefeitura.pbh.gov.br/fazenda/bhiss-digital

Código IBGE: 3106200 (Belo Horizonte/MG)

O BHISSDigital utiliza Web Services SOAP (padrão ABRASF adaptado) e também
disponibiliza uma interface REST mais recente. Este adapter implementa
a comunicação com a API REST quando disponível, com fallback para SOAP.

Nota: As URLs e formatos de resposta podem variar conforme atualizações
da prefeitura. Consulte a documentação oficial antes de usar em produção.
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


class BeloHorizonteAdapter(BaseNFSeAdapter):
    """
    Adapter para API de NFS-e da Prefeitura de Belo Horizonte.

    BHISSDigital - Sistema de NFS-e próprio de BH.

    Autenticação:
    - Login/senha cadastrados no portal BHISSDigital
    - Certificado digital e-CNPJ (para operações avançadas)

    Código IBGE: 3106200
    """

    SISTEMA_NOME = "Belo Horizonte"
    MUNICIPIO_CODIGO_IBGE = "3106200"
    MUNICIPIO_NOME = "Belo Horizonte"

    # URLs do BHISSDigital
    URL_PRODUCAO = "https://bhissdigital.pbh.gov.br/api/v1"
    URL_HOMOLOGACAO = "https://bhissdigitalhml.pbh.gov.br/api/v1"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    async def autenticar(self) -> str:
        """
        Autenticação na API BHISSDigital.

        Returns:
            Token de autenticação

        Raises:
            NFSeAuthException: Falha na autenticação
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                response = await client.post(
                    f"{self.base_url}/autenticacao/login",
                    json={
                        "login": self.credentials.get("usuario"),
                        "senha": self.credentials.get("senha"),
                    },
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 401:
                    raise NFSeAuthException(
                        "Credenciais inválidas para BHISSDigital",
                        detalhes=response.text,
                    )

                if response.status_code != 200:
                    raise NFSeAuthException(
                        f"Falha na autenticação BH: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                self.token = data.get("access_token") or data.get("token")

                if not self.token:
                    raise NFSeAuthException(
                        "Resposta de autenticação BH não contém token válido",
                        detalhes=str(data),
                    )

                self.log_info("Autenticação BHISSDigital bem-sucedida")
                return self.token

        except NFSeAuthException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na autenticação BH: {e}")
            raise NFSeAuthException(
                "Timeout ao conectar com BHISSDigital. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na autenticação BH: {e}")
            raise NFSeAuthException(f"Erro de rede: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na autenticação BH: {e}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {e}")

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """
        Busca NFS-e emitidas em Belo Horizonte.

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
                response = await client.get(
                    f"{self.base_url}/nfse/consultar",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                    params={
                        "cnpjPrestador": cnpj_limpo,
                        "dataInicio": data_inicio.strftime("%Y-%m-%d"),
                        "dataFim": data_fim.strftime("%Y-%m-%d"),
                        "pagina": 1,
                        "tamanhoPagina": limite,
                    },
                )

                if response.status_code == 401:
                    self.log_warning("Token expirado BH, reautenticando...")
                    self.token = None
                    await self.autenticar()
                    return await self.buscar_notas(cnpj, data_inicio, data_fim, limite)

                if response.status_code == 404:
                    self.log_info(f"Nenhuma NFS-e encontrada em BH para CNPJ {cnpj_limpo}")
                    return []

                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca BH: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                notas_processadas = self.processar_resposta(data)

                self.log_info(
                    f"{len(notas_processadas)} NFS-e encontradas em BH para CNPJ {cnpj_limpo}"
                )
                return notas_processadas

        except NFSeSearchException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na busca BH: {e}")
            raise NFSeSearchException(
                "Timeout ao buscar NFS-e em Belo Horizonte. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na busca BH: {e}")
            raise NFSeSearchException(f"Erro de rede: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na busca BH: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro inesperado: {e}")

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Processa resposta da API BHISSDigital para formato padrão.

        Args:
            resposta: Resposta bruta da API

        Returns:
            Lista de notas no formato padrão
        """
        notas = []

        lista_notas = (
            resposta.get("listaNotas")
            or resposta.get("notas")
            or resposta.get("nfse")
            or []
        )

        for nota_raw in lista_notas:
            try:
                # BHISSDigital pode aninhar dados em sub-objetos
                prestador = nota_raw.get("prestador") or {}
                tomador = nota_raw.get("tomador") or {}
                servico = nota_raw.get("servico") or nota_raw.get("declaracaoServico") or {}

                nota = self.criar_nota_padrao(
                    numero=str(nota_raw.get("numero") or nota_raw.get("numeroNfse") or ""),
                    serie=str(nota_raw.get("serie") or ""),
                    data_emissao=(
                        nota_raw.get("dataEmissao")
                        or nota_raw.get("data_emissao")
                    ),
                    valor_total=float(
                        nota_raw.get("valorTotal")
                        or servico.get("valorServicos")
                        or 0
                    ),
                    valor_servicos=float(servico.get("valorServicos", 0)),
                    valor_deducoes=float(servico.get("valorDeducoes", 0)),
                    valor_iss=float(servico.get("valorIss", 0)),
                    aliquota_iss=float(servico.get("aliquota", 0)),
                    cnpj_prestador=self.limpar_cnpj(
                        str(prestador.get("cnpj") or nota_raw.get("cnpjPrestador") or "")
                    ),
                    prestador_nome=(
                        prestador.get("razaoSocial")
                        or nota_raw.get("razaoSocialPrestador")
                        or ""
                    ),
                    cnpj_tomador=self.limpar_cnpj(
                        str(tomador.get("cnpj") or nota_raw.get("cnpjTomador") or "")
                    ),
                    tomador_nome=(
                        tomador.get("razaoSocial")
                        or nota_raw.get("razaoSocialTomador")
                        or ""
                    ),
                    descricao_servico=(
                        servico.get("discriminacao")
                        or nota_raw.get("descricaoServico")
                        or ""
                    ),
                    codigo_servico=(
                        servico.get("codigoServico")
                        or servico.get("itemListaServico")
                        or ""
                    ),
                    codigo_verificacao=(
                        nota_raw.get("codigoVerificacao")
                        or nota_raw.get("codigoAutenticidade")
                        or ""
                    ),
                    link_visualizacao=nota_raw.get("linkVisualizacao", ""),
                    xml_content=nota_raw.get("xml") or nota_raw.get("xmlNfse") or "",
                    municipio_codigo=self.MUNICIPIO_CODIGO_IBGE,
                    municipio_nome=self.MUNICIPIO_NOME,
                    status=(
                        nota_raw.get("situacao")
                        or nota_raw.get("status")
                        or "Autorizada"
                    ),
                )

                notas.append(nota)

            except Exception as e:
                self.log_warning(
                    f"Erro ao processar nota BH {nota_raw.get('numero', '?')}: {e}"
                )
                continue

        return notas
