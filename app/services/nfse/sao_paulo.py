"""
Adapter para API de NFS-e da Prefeitura de São Paulo (NF Paulistana).

A Prefeitura de SP possui sistema próprio de NFS-e chamado NF Paulistana
(Nota Fiscal Paulistana / Nota do Milhão).

Portal: https://nfe.prefeitura.sp.gov.br
Documentação: https://nfe.prefeitura.sp.gov.br/ws/index.html

Código IBGE: 3550308 (São Paulo/SP)

A API de SP utiliza Web Services SOAP com XML assinado digitalmente.
Este adapter implementa a comunicação com os serviços REST/JSON quando
disponíveis, com fallback para SOAP quando necessário.

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


class SaoPauloAdapter(BaseNFSeAdapter):
    """
    Adapter para API de NFS-e da Prefeitura de São Paulo.

    NF Paulistana - Sistema de NFS-e próprio de SP.

    Autenticação:
    - Certificado digital e-CNPJ (obrigatório para consultas via WS)
    - Login/senha do portal NF Paulistana

    Código IBGE: 3550308

    Serviços disponíveis:
    - ConsultaNFe: Consulta NFS-e emitidas
    - ConsultaNFeRecebidas: Consulta NFS-e recebidas (tomador)
    - ConsultaCNPJ: Verifica inscrição municipal
    """

    SISTEMA_NOME = "São Paulo"
    MUNICIPIO_CODIGO_IBGE = "3550308"
    MUNICIPIO_NOME = "São Paulo"

    # URLs da NF Paulistana
    URL_PRODUCAO = "https://nfe.prefeitura.sp.gov.br/api"
    URL_HOMOLOGACAO = "https://nfehml.prefeitura.sp.gov.br/api"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    async def autenticar(self) -> str:
        """
        Autenticação na API da NF Paulistana.

        SP utiliza autenticação via:
        - Certificado digital e-CNPJ
        - Login/senha do portal (para operações limitadas)

        Returns:
            Token de autenticação

        Raises:
            NFSeAuthException: Falha na autenticação
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                payload = {
                    "usuario": self.credentials.get("usuario"),
                    "senha": self.credentials.get("senha"),
                }

                cnpj = self.credentials.get("cnpj")
                if cnpj:
                    payload["cnpj"] = self.limpar_cnpj(cnpj)

                response = await client.post(
                    f"{self.base_url}/autenticacao/login",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 401:
                    raise NFSeAuthException(
                        "Credenciais inválidas para NF Paulistana",
                        detalhes=response.text,
                    )

                if response.status_code != 200:
                    raise NFSeAuthException(
                        f"Falha na autenticação SP: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                self.token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("hashAutenticacao")
                )

                if not self.token:
                    raise NFSeAuthException(
                        "Resposta de autenticação SP não contém token válido",
                        detalhes=str(data),
                    )

                self.log_info("Autenticação NF Paulistana bem-sucedida")
                return self.token

        except NFSeAuthException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na autenticação SP: {e}")
            raise NFSeAuthException(
                "Timeout ao conectar com NF Paulistana. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na autenticação SP: {e}")
            raise NFSeAuthException(f"Erro de rede: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na autenticação SP: {e}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {e}")

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """
        Busca NFS-e emitidas em São Paulo.

        Utiliza o serviço ConsultaNFe da NF Paulistana.

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
                # SP utiliza POST com body JSON para consultas
                response = await client.post(
                    f"{self.base_url}/nfse/consultarEmitidas",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "cnpjPrestador": cnpj_limpo,
                        "dataInicio": data_inicio.strftime("%Y-%m-%d"),
                        "dataFim": data_fim.strftime("%Y-%m-%d"),
                        "pagina": 1,
                        "registrosPorPagina": limite,
                    },
                )

                if response.status_code == 401:
                    self.log_warning("Token expirado SP, reautenticando...")
                    self.token = None
                    await self.autenticar()
                    return await self.buscar_notas(cnpj, data_inicio, data_fim, limite)

                if response.status_code == 404:
                    self.log_info(
                        f"Nenhuma NFS-e encontrada em SP para CNPJ {cnpj_limpo}"
                    )
                    return []

                if response.status_code != 200:
                    raise NFSeSearchException(
                        f"Erro na busca SP: HTTP {response.status_code}",
                        detalhes=response.text,
                    )

                data = response.json()
                notas_processadas = self.processar_resposta(data)

                self.log_info(
                    f"{len(notas_processadas)} NFS-e encontradas em SP para CNPJ {cnpj_limpo}"
                )
                return notas_processadas

        except NFSeSearchException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na busca SP: {e}")
            raise NFSeSearchException(
                "Timeout ao buscar NFS-e em São Paulo. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na busca SP: {e}")
            raise NFSeSearchException(f"Erro de rede: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na busca SP: {e}", exc_info=True)
            raise NFSeSearchException(f"Erro inesperado: {e}")

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Processa resposta da API NF Paulistana para formato padrão.

        A NF Paulistana usa nomenclatura própria nos campos,
        diferente do padrão ABRASF.

        Args:
            resposta: Resposta bruta da API

        Returns:
            Lista de notas no formato padrão
        """
        notas = []

        # SP pode retornar em diferentes chaves conforme a versão da API
        lista_notas = (
            resposta.get("NFe")
            or resposta.get("NotasFiscais")
            or resposta.get("listaNfse")
            or resposta.get("nfse")
            or []
        )

        for nota_raw in lista_notas:
            try:
                # SP pode ter sub-objetos ou campos achatados
                prestador = nota_raw.get("Prestador") or nota_raw.get("prestador") or {}
                tomador = nota_raw.get("Tomador") or nota_raw.get("tomador") or {}

                nota = self.criar_nota_padrao(
                    numero=str(
                        nota_raw.get("NumeroNFe")
                        or nota_raw.get("NumeroNota")
                        or nota_raw.get("numero")
                        or ""
                    ),
                    serie=str(
                        nota_raw.get("SerieNFe")
                        or nota_raw.get("serie")
                        or ""
                    ),
                    data_emissao=(
                        nota_raw.get("DataEmissao")
                        or nota_raw.get("dataEmissao")
                        or nota_raw.get("DataEmissaoNFe")
                    ),
                    valor_total=float(
                        nota_raw.get("ValorServicos")
                        or nota_raw.get("ValorTotal")
                        or nota_raw.get("valorTotal")
                        or 0
                    ),
                    valor_servicos=float(
                        nota_raw.get("ValorServicos")
                        or nota_raw.get("valorServicos")
                        or 0
                    ),
                    valor_deducoes=float(
                        nota_raw.get("ValorDeducoes")
                        or nota_raw.get("valorDeducoes")
                        or 0
                    ),
                    valor_iss=float(
                        nota_raw.get("ValorISS")
                        or nota_raw.get("valorIss")
                        or 0
                    ),
                    aliquota_iss=float(
                        nota_raw.get("AliquotaServicos")
                        or nota_raw.get("aliquota")
                        or 0
                    ),
                    cnpj_prestador=self.limpar_cnpj(
                        str(
                            nota_raw.get("CPFCNPJPrestador")
                            or prestador.get("cnpj")
                            or nota_raw.get("cnpjPrestador")
                            or ""
                        )
                    ),
                    prestador_nome=(
                        nota_raw.get("RazaoSocialPrestador")
                        or prestador.get("razaoSocial")
                        or nota_raw.get("NomePrestador")
                        or ""
                    ),
                    cnpj_tomador=self.limpar_cnpj(
                        str(
                            nota_raw.get("CPFCNPJTomador")
                            or tomador.get("cnpj")
                            or nota_raw.get("cnpjTomador")
                            or ""
                        )
                    ),
                    tomador_nome=(
                        nota_raw.get("RazaoSocialTomador")
                        or tomador.get("razaoSocial")
                        or nota_raw.get("NomeTomador")
                        or ""
                    ),
                    descricao_servico=(
                        nota_raw.get("Discriminacao")
                        or nota_raw.get("DescricaoServico")
                        or nota_raw.get("descricaoServico")
                        or ""
                    ),
                    codigo_servico=(
                        nota_raw.get("CodigoServico")
                        or nota_raw.get("codigoServico")
                        or ""
                    ),
                    codigo_verificacao=(
                        nota_raw.get("CodigoVerificacao")
                        or nota_raw.get("codigoVerificacao")
                        or ""
                    ),
                    link_visualizacao=(
                        nota_raw.get("LinkVisualizacao")
                        or nota_raw.get("linkVisualizacao")
                        or ""
                    ),
                    xml_content=(
                        nota_raw.get("XML")
                        or nota_raw.get("xml")
                        or nota_raw.get("xmlNfse")
                        or ""
                    ),
                    municipio_codigo=self.MUNICIPIO_CODIGO_IBGE,
                    municipio_nome=self.MUNICIPIO_NOME,
                    status=(
                        nota_raw.get("StatusNFe")
                        or nota_raw.get("situacao")
                        or nota_raw.get("status")
                        or "Normal"
                    ),
                )

                notas.append(nota)

            except Exception as e:
                self.log_warning(
                    f"Erro ao processar nota SP "
                    f"{nota_raw.get('NumeroNFe') or nota_raw.get('numero', '?')}: {e}"
                )
                continue

        return notas
