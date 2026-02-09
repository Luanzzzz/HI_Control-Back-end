"""
Adapter para o Sistema Nacional de NFS-e (ABRASF/ISSNet).

O Sistema Nacional de NFS-e é uma iniciativa do governo federal que unifica
a emissão de NFS-e em todo o Brasil. Utiliza o padrão ABRASF e é gerenciado
em parceria com municípios.

Portal: https://www.gov.br/nfse
Ambiente de Produção: https://sefin.nfse.gov.br
Ambiente de Homologação: https://sefin.producaorestrita.nfse.gov.br

Documentação técnica:
- https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica
- Padrão ABRASF 2.04

Cobre aproximadamente 3.000+ municípios brasileiros que aderiram ao sistema.
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


class SistemaNacionalAdapter(BaseNFSeAdapter):
    """
    Adapter para o Sistema Nacional de NFS-e (padrão ABRASF).

    Endpoints oficiais:
    - Produção: https://sefin.nfse.gov.br/sefinnacional
    - Homologação: https://sefin.producaorestrita.nfse.gov.br/sefinnacional

    Autenticação:
    - Certificado digital e-CNPJ (A1 ou A3) OU
    - Login/senha gerado no portal gov.br

    Nota: As URLs e formatos de resposta podem variar conforme atualizações
    do sistema. Consulte a documentação oficial antes de usar em produção.
    """

    SISTEMA_NOME = "Sistema Nacional"

    # URLs oficiais do Sistema Nacional de NFS-e
    URL_PRODUCAO = "https://sefin.nfse.gov.br/sefinnacional"
    URL_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    async def autenticar(self) -> str:
        """
        Autenticação no Sistema Nacional de NFS-e.

        O Sistema Nacional utiliza autenticação via:
        - Certificado digital e-CNPJ (preferencial)
        - Credenciais gov.br (login federado)

        Returns:
            Token/sessão de autenticação

        Raises:
            NFSeAuthException: Falha na autenticação
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                # Tentativa de autenticação via credenciais
                payload = {
                    "login": self.credentials.get("usuario"),
                    "senha": self.credentials.get("senha"),
                }

                # Se houver CNPJ, incluir para contexto
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
                        "Credenciais inválidas para o Sistema Nacional de NFS-e",
                        detalhes=response.text,
                    )

                if response.status_code != 200:
                    raise NFSeAuthException(
                        f"Falha na autenticação Sistema Nacional: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                self.token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("chaveAutenticacao")
                )

                if not self.token:
                    raise NFSeAuthException(
                        "Resposta de autenticação não contém token válido",
                        detalhes=str(data),
                    )

                self.log_info("Autenticação bem-sucedida")
                return self.token

        except NFSeAuthException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na autenticação: {e}")
            raise NFSeAuthException(
                "Timeout ao conectar com Sistema Nacional de NFS-e. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na autenticação: {e}")
            raise NFSeAuthException(f"Erro de rede ao autenticar: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na autenticação: {e}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {e}")

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """
        Busca NFS-e no Sistema Nacional por CNPJ e período.

        Utiliza o serviço de consulta do padrão ABRASF para buscar
        notas fiscais de serviço emitidas pelo prestador.

        Args:
            cnpj: CNPJ do prestador (com ou sem formatação)
            data_inicio: Data inicial do período
            data_fim: Data final do período
            limite: Quantidade máxima de notas

        Returns:
            Lista de notas no formato padrão Hi-Control

        Raises:
            NFSeSearchException: Erro na consulta
        """
        if not self.token:
            await self.autenticar()

        cnpj_limpo = self.limpar_cnpj(cnpj)
        if not self.validar_cnpj(cnpj_limpo):
            raise NFSeSearchException(f"CNPJ inválido: {cnpj}")

        try:
            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                # Consulta de NFS-e emitidas (padrão ABRASF)
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

                # Token expirado - reautenticar (máx 1 retry)
                if response.status_code == 401:
                    self.log_warning("Token expirado, reautenticando...")
                    self.token = None
                    await self.autenticar()
                    return await self.buscar_notas(cnpj, data_inicio, data_fim, limite)

                if response.status_code == 404:
                    self.log_info(f"Nenhuma NFS-e encontrada para CNPJ {cnpj_limpo}")
                    return []

                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                notas_processadas = self.processar_resposta(data)

                self.log_info(
                    f"{len(notas_processadas)} NFS-e encontradas para CNPJ {cnpj_limpo} "
                    f"({data_inicio} a {data_fim})"
                )
                return notas_processadas

        except NFSeSearchException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na busca: {e}")
            raise NFSeSearchException(
                "Timeout ao buscar NFS-e no Sistema Nacional. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na busca: {e}")
            raise NFSeSearchException(f"Erro de rede: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na busca: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro inesperado: {e}")

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Processa resposta do Sistema Nacional para formato padrão Hi-Control.

        O Sistema Nacional ABRASF retorna dados em formato JSON com
        campos padronizados. Este método normaliza para o formato interno.

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
                # Extrair dados do prestador (pode ser objeto aninhado)
                prestador = nota_raw.get("prestador") or {}
                if isinstance(prestador, str):
                    prestador = {}

                # Extrair dados do tomador (pode ser objeto aninhado)
                tomador = nota_raw.get("tomador") or {}
                if isinstance(tomador, str):
                    tomador = {}

                # Extrair valores (podem estar em sub-objetos)
                valores = nota_raw.get("valores") or nota_raw.get("servico") or {}
                if isinstance(valores, str):
                    valores = {}

                nota = self.criar_nota_padrao(
                    numero=str(nota_raw.get("numero") or nota_raw.get("numeroNfse") or ""),
                    serie=str(nota_raw.get("serie") or ""),
                    data_emissao=(
                        nota_raw.get("dataEmissao")
                        or nota_raw.get("data_emissao")
                        or nota_raw.get("dhEmissao")
                    ),
                    valor_total=float(
                        nota_raw.get("valorTotal")
                        or nota_raw.get("valor_total")
                        or valores.get("valorServicos")
                        or valores.get("valorTotal")
                        or 0
                    ),
                    valor_servicos=float(
                        valores.get("valorServicos")
                        or nota_raw.get("valorServicos")
                        or 0
                    ),
                    valor_iss=float(
                        valores.get("valorIss")
                        or nota_raw.get("valorIss")
                        or 0
                    ),
                    aliquota_iss=float(
                        valores.get("aliquota")
                        or nota_raw.get("aliquotaIss")
                        or 0
                    ),
                    cnpj_prestador=self.limpar_cnpj(
                        str(
                            prestador.get("cnpj")
                            or nota_raw.get("cnpjPrestador")
                            or nota_raw.get("cnpj_prestador")
                            or ""
                        )
                    ),
                    prestador_nome=(
                        prestador.get("razaoSocial")
                        or prestador.get("nome")
                        or nota_raw.get("prestador_nome")
                        or nota_raw.get("razaoSocialPrestador")
                        or ""
                    ),
                    cnpj_tomador=self.limpar_cnpj(
                        str(
                            tomador.get("cnpj")
                            or nota_raw.get("cnpjTomador")
                            or nota_raw.get("cnpj_tomador")
                            or ""
                        )
                    ),
                    tomador_nome=(
                        tomador.get("razaoSocial")
                        or tomador.get("nome")
                        or nota_raw.get("tomador_nome")
                        or nota_raw.get("razaoSocialTomador")
                        or ""
                    ),
                    descricao_servico=(
                        nota_raw.get("discriminacao")
                        or nota_raw.get("descricaoServico")
                        or nota_raw.get("descricao_servico")
                        or valores.get("discriminacao")
                        or ""
                    ),
                    codigo_servico=(
                        nota_raw.get("codigoServico")
                        or nota_raw.get("itemListaServico")
                        or valores.get("itemListaServico")
                        or ""
                    ),
                    codigo_verificacao=(
                        nota_raw.get("codigoVerificacao")
                        or nota_raw.get("codigo_verificacao")
                        or ""
                    ),
                    link_visualizacao=nota_raw.get("linkVisualizacao", ""),
                    xml_content=nota_raw.get("xml") or nota_raw.get("xmlNfse") or "",
                    municipio_codigo=str(
                        nota_raw.get("codigoMunicipio")
                        or nota_raw.get("municipio_codigo")
                        or prestador.get("codigoMunicipio")
                        or ""
                    ),
                    municipio_nome=(
                        nota_raw.get("municipioNome")
                        or nota_raw.get("municipio_nome")
                        or prestador.get("municipio")
                        or ""
                    ),
                    status=(
                        nota_raw.get("situacao")
                        or nota_raw.get("status")
                        or "Autorizada"
                    ),
                )

                notas.append(nota)

            except Exception as e:
                self.log_warning(
                    f"Erro ao processar nota {nota_raw.get('numero', '?')}: {e}"
                )
                continue

        return notas
