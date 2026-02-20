"""
Adapter para o Sistema Nacional de NFS-e (ABRASF/ISSNet).

Portal: https://www.gov.br/nfse
Ambiente de producao: https://sefin.nfse.gov.br
Ambiente de homologacao: https://sefin.producaorestrita.nfse.gov.br
"""

import logging
import os
import tempfile
from datetime import date
from typing import Any, Dict, List

import httpx

from app.services.nfse.base_adapter import (
    BaseNFSeAdapter,
    NFSeAuthException,
    NFSeSearchException,
)

logger = logging.getLogger(__name__)


class SistemaNacionalAdapter(BaseNFSeAdapter):
    """Adapter para o Sistema Nacional de NFS-e."""

    SISTEMA_NOME = "Sistema Nacional"

    URL_PRODUCAO = "https://sefin.nfse.gov.br"
    URL_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.homologacao = homologacao

    def _usar_autenticacao_por_certificado(self) -> bool:
        return bool(
            self.credentials.get("certificado_a1")
            and self.credentials.get("certificado_senha_encrypted")
        )

    def _endpoints_consulta(self) -> List[str]:
        base = self.base_url.rstrip("/")
        return [
            f"{base}/SefinNacional/nfse/consultar",
            f"{base}/sefinnacional/nfse/consultar",
            f"{base}/SefinNacional/nfse",
            f"{base}/sefinnacional/nfse",
        ]

    def _parametros_consulta(
        self,
        cnpj_limpo: str,
        data_inicio: date,
        data_fim: date,
        limite: int,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "cnpjPrestador": cnpj_limpo,
                "dataInicial": data_inicio.strftime("%Y-%m-%d"),
                "dataFinal": data_fim.strftime("%Y-%m-%d"),
                "pagina": 1,
                "itensPorPagina": limite,
            },
            {
                "cnpjPrestador": cnpj_limpo,
                "dataInicio": data_inicio.strftime("%Y-%m-%d"),
                "dataFim": data_fim.strftime("%Y-%m-%d"),
                "pagina": 1,
                "tamanhoPagina": limite,
            },
            {
                "cnpj": cnpj_limpo,
                "dataInicio": data_inicio.strftime("%Y-%m-%d"),
                "dataFim": data_fim.strftime("%Y-%m-%d"),
                "pagina": 1,
                "limite": limite,
            },
        ]

    async def autenticar(self) -> str:
        """Autenticacao no Sistema Nacional de NFS-e."""
        if self._usar_autenticacao_por_certificado():
            self.token = "CERTIFICADO_A1_MTLS"
            self.log_info("Autenticacao por certificado A1 habilitada (mTLS)")
            return self.token

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                payload = {
                    "login": self.credentials.get("usuario"),
                    "senha": self.credentials.get("senha"),
                }

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
                        "Credenciais invalidas para o Sistema Nacional de NFS-e",
                        detalhes=response.text,
                    )

                if response.status_code != 200:
                    raise NFSeAuthException(
                        f"Falha na autenticacao Sistema Nacional: HTTP {response.status_code}",
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
                        "Resposta de autenticacao nao contem token valido",
                        detalhes=str(data),
                    )

                self.log_info("Autenticacao bem-sucedida")
                return self.token

        except NFSeAuthException:
            raise
        except httpx.TimeoutException as e:
            self.log_error(f"Timeout na autenticacao: {e}")
            raise NFSeAuthException(
                "Timeout ao conectar com Sistema Nacional de NFS-e. Tente novamente."
            )
        except httpx.HTTPError as e:
            self.log_error(f"Erro HTTP na autenticacao: {e}")
            raise NFSeAuthException(f"Erro de rede ao autenticar: {e}")
        except Exception as e:
            self.log_error(f"Erro inesperado na autenticacao: {e}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {e}")

    async def buscar_notas(
        self,
        cnpj: str,
        data_inicio: date,
        data_fim: date,
        limite: int = 100,
    ) -> List[Dict]:
        """Busca NFS-e por CNPJ e periodo."""
        cnpj_limpo = self.limpar_cnpj(cnpj)
        if not self.validar_cnpj(cnpj_limpo):
            raise NFSeSearchException(f"CNPJ invalido: {cnpj}")

        if self._usar_autenticacao_por_certificado():
            return await self._buscar_notas_com_certificado(
                cnpj_limpo=cnpj_limpo,
                data_inicio=data_inicio,
                data_fim=data_fim,
                limite=limite,
            )

        if not self.token:
            await self.autenticar()

        try:
            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                response = await client.get(
                    self._endpoints_consulta()[0],
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                    params=self._parametros_consulta(cnpj_limpo, data_inicio, data_fim, limite)[0],
                )

                if response.status_code == 401:
                    self.log_warning("Token expirado, reautenticando...")
                    self.token = None
                    await self.autenticar()
                    return await self.buscar_notas(cnpj, data_inicio, data_fim, limite)

                if response.status_code in {204, 404}:
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

    async def _buscar_notas_com_certificado(
        self,
        cnpj_limpo: str,
        data_inicio: date,
        data_fim: date,
        limite: int,
    ) -> List[Dict]:
        cert_pem_path = ""
        key_pem_path = ""
        try:
            cert_bytes, senha_cert = self._carregar_certificado_para_mtls()
            cert_pem_path, key_pem_path = self._gerar_cert_key_temp(cert_bytes, senha_cert)

            tentativas = []
            async with httpx.AsyncClient(
                timeout=60.0,
                verify=True,
                cert=(cert_pem_path, key_pem_path),
            ) as client:
                for endpoint in self._endpoints_consulta():
                    for params in self._parametros_consulta(cnpj_limpo, data_inicio, data_fim, limite):
                        response = await client.get(
                            endpoint,
                            headers={"Accept": "application/json"},
                            params=params,
                        )
                        tentativas.append(f"{endpoint} [{response.status_code}]")

                        if response.status_code in {204, 404}:
                            continue

                        if response.status_code in {401, 403}:
                            self.log_warning(
                                f"Consulta mTLS sem permissao no endpoint {endpoint} "
                                f"(HTTP {response.status_code})"
                            )
                            continue

                        if response.status_code != 200:
                            continue

                        try:
                            data = response.json()
                        except ValueError:
                            continue

                        notas_processadas = self.processar_resposta(data)
                        self.log_info(
                            f"{len(notas_processadas)} NFS-e encontradas via mTLS para CNPJ {cnpj_limpo} "
                            f"({data_inicio} a {data_fim})"
                        )
                        return notas_processadas

            self.log_info(
                f"Consulta NFS-e via mTLS sem documentos para CNPJ {cnpj_limpo}. "
                f"Tentativas: {' | '.join(tentativas)}"
            )
            return []

        except NFSeAuthException:
            raise
        except Exception as e:
            self.log_error(f"Falha na consulta NFS-e via mTLS: {e}", exc_info=True)
            raise NFSeSearchException(f"Falha na consulta NFS-e via mTLS: {e}")
        finally:
            for path in (cert_pem_path, key_pem_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def _carregar_certificado_para_mtls(self) -> tuple[bytes, str]:
        cert_base64 = self.credentials.get("certificado_a1")
        senha_encrypted = self.credentials.get("certificado_senha_encrypted")
        if not cert_base64 or not senha_encrypted:
            raise NFSeAuthException("Certificado A1 nao configurado para autenticacao mTLS")

        try:
            from app.services.certificado_service import certificado_service

            cert_bytes, _ = certificado_service.carregar_certificado(
                cert_base64,
                senha_encrypted,
            )
            senha_cert = certificado_service.descriptografar_senha(senha_encrypted)
            return cert_bytes, senha_cert
        except Exception as exc:  # noqa: BLE001
            raise NFSeAuthException("Falha ao carregar certificado A1", detalhes=str(exc)) from exc

    def _gerar_cert_key_temp(self, cert_bytes: bytes, senha_cert: str) -> tuple[str, str]:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            pkcs12,
        )

        senha_bytes = senha_cert.encode("utf-8") if senha_cert else None
        private_key, certificate, additional = pkcs12.load_key_and_certificates(cert_bytes, senha_bytes)
        if private_key is None or certificate is None:
            raise NFSeAuthException("PFX invalido sem certificado/chave privada")

        cert_chain = certificate.public_bytes(Encoding.PEM)
        if additional:
            for cert_extra in additional:
                cert_chain += cert_extra.public_bytes(Encoding.PEM)

        key_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption(),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_tmp:
            cert_tmp.write(cert_chain)
            cert_path = cert_tmp.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_tmp:
            key_tmp.write(key_pem)
            key_path = key_tmp.name

        return cert_path, key_path

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """Processa resposta do Sistema Nacional para formato padrao Hi-Control."""
        notas = []

        lista_notas = (
            resposta.get("nfse")
            or resposta.get("notas")
            or resposta.get("listaNfse")
            or resposta.get("compNfse")
            or []
        )

        for nota_raw in lista_notas:
            try:
                prestador = nota_raw.get("prestador") or {}
                if isinstance(prestador, str):
                    prestador = {}

                tomador = nota_raw.get("tomador") or {}
                if isinstance(tomador, str):
                    tomador = {}

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
