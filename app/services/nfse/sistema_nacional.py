"""
Adapter para o Sistema Nacional de NFS-e.

Fluxos suportados:
1) Emissao/consulta por chave (Sefin Nacional).
2) Distribuicao por NSU para contribuintes (ADN), com mTLS via certificado A1.
"""

from __future__ import annotations

import base64
import gzip
import logging
import os
import re
import tempfile
import zlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

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

    # API Sefin Nacional (emissao/consulta por chave)
    URL_PRODUCAO = "https://sefin.nfse.gov.br"
    URL_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br"

    # API ADN Contribuintes (distribuicao por NSU)
    ADN_URL_PRODUCAO = "https://adn.nfse.gov.br/contribuintes"
    ADN_URL_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

    def __init__(self, credentials: Dict[str, str], homologacao: bool = False):
        super().__init__(credentials)
        self.base_url = self.URL_HOMOLOGACAO if homologacao else self.URL_PRODUCAO
        self.adn_base_url = self.ADN_URL_HOMOLOGACAO if homologacao else self.ADN_URL_PRODUCAO
        self.homologacao = homologacao

        self.nsu_inicial = self._coerce_int(credentials.get("nsu_inicial"), 0)
        self.nsu_final = self.nsu_inicial
        self.nsu_max_visto = self.nsu_inicial
        token_raw = str(credentials.get("token") or "")
        token_upper = token_raw.upper()
        self.bootstrap_recente_concluido = "HOTDONE:1" in token_upper
        self.persistir_cursor_nsu = True
        self.cursor_sugerido_token: Optional[str] = None

    def _usar_autenticacao_por_certificado(self) -> bool:
        return bool(
            self.credentials.get("certificado_a1")
            and self.credentials.get("certificado_senha_encrypted")
        )

    def _endpoints_consulta_por_chave(self) -> List[str]:
        base = self.base_url.rstrip("/")
        return [
            f"{base}/SefinNacional/nfse",
            f"{base}/sefinnacional/nfse",
        ]

    def _priorizar_recente_habilitado(self) -> bool:
        valor = os.getenv("NFSE_ADN_PRIORIZAR_RECENTES", "true").strip().lower()
        return valor not in {"0", "false", "no", "off"}

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
        except httpx.TimeoutException as exc:
            self.log_error(f"Timeout na autenticacao: {exc}")
            raise NFSeAuthException(
                "Timeout ao conectar com Sistema Nacional de NFS-e. Tente novamente."
            )
        except httpx.HTTPError as exc:
            self.log_error(f"Erro HTTP na autenticacao: {exc}")
            raise NFSeAuthException(f"Erro de rede ao autenticar: {exc}")
        except Exception as exc:  # noqa: BLE001
            self.log_error(f"Erro inesperado na autenticacao: {exc}", exc_info=True)
            raise NFSeAuthException(f"Erro inesperado: {exc}")

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

        # Fluxo legado sem certificado: consulta por chave de acesso.
        # Nao suporta varredura por periodo, portanto retorna vazio por padrao.
        self.log_warning(
            "Consulta por periodo sem certificado nao suportada no Sistema Nacional. "
            "Configure certificado A1 para distribuicao por NSU."
        )
        return []

    async def _buscar_notas_com_certificado(
        self,
        cnpj_limpo: str,
        data_inicio: date,
        data_fim: date,
        limite: int,
    ) -> List[Dict]:
        cert_pem_path = ""
        key_pem_path = ""

        # O endpoint /DFe/{NSU} retorna lotes de 50 por chamada.
        tamanho_lote = 50
        max_paginas = max(1, int(os.getenv("NFSE_ADN_MAX_PAGINAS", "8")))
        esperar_429_seg = max(1, int(os.getenv("NFSE_ADN_RETRY_429_SECONDS", "2")))
        max_retries_429 = max(1, int(os.getenv("NFSE_ADN_RETRY_429_MAX", "4")))
        pausa_paginas_ms = max(0, int(os.getenv("NFSE_ADN_PAGE_DELAY_MS", "300")))

        notas: List[Dict] = []
        chaves_vistas: Set[str] = set()
        nsu_atual = max(0, self.nsu_inicial)

        try:
            cert_bytes, senha_cert = self._carregar_certificado_para_mtls()
            cert_pem_path, key_pem_path = self._gerar_cert_key_temp(cert_bytes, senha_cert)

            async with httpx.AsyncClient(
                timeout=60.0,
                verify=True,
                cert=(cert_pem_path, key_pem_path),
            ) as client:
                if (
                    self._priorizar_recente_habilitado()
                    and self.nsu_inicial <= 0
                    and not self.bootstrap_recente_concluido
                ):
                    try:
                        nsu_atual = await self._resolver_nsu_bootstrap_recente(
                            client=client,
                            cnpj_limpo=cnpj_limpo,
                            max_retries_429=max_retries_429,
                            esperar_429_seg=esperar_429_seg,
                        )
                        if nsu_atual > 0:
                            self.persistir_cursor_nsu = False
                            self.log_info(
                                "Bootstrap prioritario de recentes habilitado: iniciando NSU em %s",
                                nsu_atual,
                            )
                    except Exception as exc:  # noqa: BLE001
                        self.log_warning(
                            "Falha ao localizar NSU recente (fallback para NSU inicial padrao): %s",
                            exc,
                        )
                        nsu_atual = max(0, self.nsu_inicial)

                for pagina in range(1, max_paginas + 1):
                    try:
                        response = await self._consultar_lote_adn(
                            client=client,
                            cnpj_limpo=cnpj_limpo,
                            nsu=nsu_atual,
                            max_retries_429=max_retries_429,
                            esperar_429_seg=esperar_429_seg,
                            contexto=f"pagina={pagina},nsu={nsu_atual}",
                        )
                    except NFSeSearchException:
                        if notas:
                            break
                        raise

                    if response is None:
                        break

                    if response.status_code in {401, 403}:
                        raise NFSeAuthException(
                            f"Falha na autenticacao ADN Contribuintes: HTTP {response.status_code}",
                            detalhes=response.text,
                        )

                    if response.status_code not in {200, 404}:
                        raise NFSeSearchException(
                            f"Erro na consulta ADN Contribuintes: HTTP {response.status_code}",
                            detalhes=response.text,
                        )

                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise NFSeSearchException(
                            "Resposta invalida da API ADN Contribuintes",
                            detalhes=str(exc),
                        ) from exc

                    status_proc = str(data.get("StatusProcessamento") or "").upper()
                    lote_dfe = data.get("LoteDFe") or []

                    self.log_info(
                        f"ADN DFe pagina={pagina} nsu={nsu_atual} "
                        f"status={status_proc} lote={len(lote_dfe)}"
                    )

                    if status_proc == "NENHUM_DOCUMENTO_LOCALIZADO" and not lote_dfe:
                        break

                    if not lote_dfe:
                        # Sem lote retornado: encerra para evitar loop sem progresso.
                        break

                    nsu_lote_max = nsu_atual
                    for item in lote_dfe:
                        nsu_item = self._coerce_int(item.get("NSU"), 0)
                        nsu_lote_max = max(nsu_lote_max, nsu_item)
                        self.nsu_max_visto = max(self.nsu_max_visto, nsu_item)

                        if str(item.get("TipoDocumento") or "").upper() != "NFSE":
                            continue

                        xml_doc = self._decodificar_arquivo_xml(item.get("ArquivoXml"))
                        if not xml_doc:
                            continue

                        nota = self._extrair_nota_do_xml(xml_doc, cnpj_limpo, item)
                        if not nota:
                            continue

                        if not self._nota_no_periodo(nota.get("data_emissao"), data_inicio, data_fim):
                            continue

                        chave_unica = (
                            nota.get("chave_acesso")
                            or f"{nota.get('numero')}|{nota.get('codigo_verificacao')}|{nsu_item}"
                        )
                        if chave_unica in chaves_vistas:
                            continue

                        chaves_vistas.add(chave_unica)
                        notas.append(nota)

                    self.nsu_final = max(self.nsu_final, nsu_lote_max)
                    if nsu_lote_max <= nsu_atual:
                        break

                    nsu_atual = nsu_lote_max + 1

                    # Lote menor que 50 geralmente indica fim da janela atual.
                    if len(lote_dfe) < tamanho_lote:
                        break

                    if pausa_paginas_ms > 0:
                        await self._sleep_async(pausa_paginas_ms / 1000.0)

                if (
                    not self.persistir_cursor_nsu
                    and self.nsu_final > 0
                    and not self.bootstrap_recente_concluido
                ):
                    self.cursor_sugerido_token = f"AUTO_CERT_A1|NSU:0|HOTDONE:1|HOTNSU:{self.nsu_final}"
                    self.bootstrap_recente_concluido = True

            self.log_info(
                f"Consulta ADN concluida: cnpj={cnpj_limpo} notas={len(notas)} "
                f"nsu_inicial={self.nsu_inicial} nsu_final={self.nsu_final}"
            )
            return notas

        except NFSeAuthException:
            raise
        except NFSeSearchException:
            raise
        except Exception as exc:  # noqa: BLE001
            self.log_error(f"Falha na consulta NFS-e via ADN/mTLS: {exc}", exc_info=True)
            raise NFSeSearchException(f"Falha na consulta NFS-e via ADN/mTLS: {exc}")
        finally:
            for path in (cert_pem_path, key_pem_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    async def _sleep_async(self, segundos: float) -> None:
        import asyncio

        await asyncio.sleep(max(0.1, float(segundos)))

    async def _consultar_lote_adn(
        self,
        client: httpx.AsyncClient,
        cnpj_limpo: str,
        nsu: int,
        max_retries_429: int,
        esperar_429_seg: int,
        contexto: str,
    ) -> Optional[httpx.Response]:
        endpoint = f"{self.adn_base_url}/DFe/{max(0, int(nsu))}"
        tentativas_429 = 0

        while True:
            response = await client.get(
                endpoint,
                headers={"Accept": "application/json"},
                params={"cnpjConsulta": cnpj_limpo, "lote": "true"},
            )
            if response.status_code != 429:
                return response

            tentativas_429 += 1
            self.log_warning(
                "ADN retornou 429 (limite temporario). contexto=%s tentativa=%s/%s",
                contexto,
                tentativas_429,
                max_retries_429,
            )
            if tentativas_429 >= max_retries_429:
                raise NFSeSearchException(
                    "ADN bloqueou temporariamente a consulta por excesso de requisicoes (HTTP 429).",
                    detalhes=contexto,
                )
            await self._sleep_async(esperar_429_seg * tentativas_429)

    async def _resolver_nsu_bootstrap_recente(
        self,
        client: httpx.AsyncClient,
        cnpj_limpo: str,
        max_retries_429: int,
        esperar_429_seg: int,
    ) -> int:
        max_probe = max(0, self._coerce_int(os.getenv("NFSE_ADN_PRIORIDADE_NSU_MAX", "999999999999999")))
        janela_nsu = max(200, self._coerce_int(os.getenv("NFSE_ADN_PRIORIDADE_JANELA_NSU", "5000")))
        max_iter = max(6, self._coerce_int(os.getenv("NFSE_ADN_PRIORIDADE_MAX_ITER", "18")))

        low = 0
        high = max_probe
        melhor_nsu_com_documento = -1

        for idx in range(1, max_iter + 1):
            if low > high:
                break
            mid = (low + high) // 2
            response = await self._consultar_lote_adn(
                client=client,
                cnpj_limpo=cnpj_limpo,
                nsu=mid,
                max_retries_429=max_retries_429,
                esperar_429_seg=esperar_429_seg,
                contexto=f"bootstrap-iter={idx},nsu={mid}",
            )
            if response is None:
                break

            if response.status_code in {401, 403}:
                raise NFSeAuthException(
                    f"Falha na autenticacao ADN Contribuintes: HTTP {response.status_code}",
                    detalhes=response.text,
                )
            if response.status_code not in {200, 404}:
                raise NFSeSearchException(
                    f"Erro na consulta ADN Contribuintes: HTTP {response.status_code}",
                    detalhes=response.text,
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise NFSeSearchException(
                    "Resposta invalida da API ADN Contribuintes durante bootstrap de NSU",
                    detalhes=str(exc),
                ) from exc

            lote = payload.get("LoteDFe") or []
            if lote:
                melhor_nsu_com_documento = max(melhor_nsu_com_documento, mid)
                nsu_lote_max = mid
                for item in lote:
                    nsu_item = self._coerce_int(item.get("NSU"), mid)
                    nsu_lote_max = max(nsu_lote_max, nsu_item)
                low = max(low, nsu_lote_max + 1)
            else:
                high = mid - 1

        if melhor_nsu_com_documento < 0:
            return max(0, self.nsu_inicial)

        return max(0, melhor_nsu_com_documento - janela_nsu)

    def _carregar_certificado_para_mtls(self) -> Tuple[bytes, str]:
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

    def _gerar_cert_key_temp(self, cert_bytes: bytes, senha_cert: str) -> Tuple[str, str]:
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

    def _decodificar_arquivo_xml(self, arquivo_xml: Any) -> Optional[str]:
        if arquivo_xml is None:
            return None

        valor = str(arquivo_xml).strip()
        if not valor:
            return None

        if valor.startswith("<"):
            return valor

        binarios: List[bytes] = []

        # Tentativa base64 padrao
        try:
            binarios.append(base64.b64decode(valor, validate=True))
        except Exception:  # noqa: BLE001
            try:
                binarios.append(base64.b64decode(valor + "==="))
            except Exception:  # noqa: BLE001
                pass

        # Tentativa direta em bytes (casos sem base64)
        if not binarios:
            binarios.append(valor.encode("utf-8", errors="ignore"))

        decompressors = (
            lambda b: gzip.decompress(b),
            lambda b: zlib.decompress(b),
            lambda b: zlib.decompress(b, -zlib.MAX_WBITS),
        )

        for bruto in binarios:
            if not bruto:
                continue

            # Se ja for XML em bytes
            if bruto.lstrip().startswith(b"<"):
                try:
                    return bruto.decode("utf-8", errors="ignore")
                except Exception:  # noqa: BLE001
                    continue

            for fn in decompressors:
                try:
                    descompactado = fn(bruto)
                except Exception:  # noqa: BLE001
                    continue

                if descompactado and descompactado.lstrip().startswith(b"<"):
                    return descompactado.decode("utf-8", errors="ignore")

        return None

    def _extrair_nota_do_xml(
        self,
        xml_doc: str,
        cnpj_consulta: str,
        item_dfe: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_doc)
        except ET.ParseError:
            return None

        inf_nfse = self._find_node(root, "infNFSe") or root

        emit = self._find_node(inf_nfse, "emit") or self._find_node(inf_nfse, "prest")
        toma = self._find_node(inf_nfse, "toma")

        cnpj_emitente = self.limpar_cnpj(self._find_text(emit, "CNPJ") or cnpj_consulta)
        nome_emitente = self._find_text(emit, "xNome") or self._find_text(emit, "xFant") or ""

        cnpj_destinatario = self.limpar_cnpj(
            self._find_text(toma, "CNPJ") or self._find_text(toma, "CPF") or ""
        )
        nome_destinatario = self._find_text(toma, "xNome") or ""

        data_emissao = (
            self._find_text(inf_nfse, "dhEmi")
            or self._find_text(inf_nfse, "dCompet")
            or self._find_text(inf_nfse, "dhProc")
        )

        valor_total = self._to_float(
            self._find_text(inf_nfse, "vLiq")
            or self._find_text(inf_nfse, "vServ")
            or self._find_text(inf_nfse, "vNFSe")
            or "0"
        )
        valor_iss = self._to_float(
            self._find_text(inf_nfse, "vISSQN")
            or self._find_text(inf_nfse, "vIss")
            or "0"
        )
        aliquota_iss = self._to_float(
            self._find_text(inf_nfse, "pAliqAplic")
            or self._find_text(inf_nfse, "pAliq")
            or "0"
        )

        chave_acesso = self._extrair_chave_acesso_nfse(inf_nfse, item_dfe)
        numero_nf = self._find_text(inf_nfse, "nNFSe") or self._find_text(inf_nfse, "nDPS") or ""
        serie = self._find_text(inf_nfse, "serie") or ""

        codigo_municipio = self._find_text(inf_nfse, "cLocIncid") or self._find_text(inf_nfse, "cLocPrestacao") or ""
        nome_municipio = self._find_text(inf_nfse, "xLocIncid") or self._find_text(inf_nfse, "xLocPrestacao") or ""

        descricao_servico = (
            self._find_text(inf_nfse, "xDescServ")
            or self._find_text(inf_nfse, "xTribMun")
            or self._find_text(inf_nfse, "xTribNac")
            or ""
        )
        codigo_servico = self._find_text(inf_nfse, "cTribNac") or self._find_text(inf_nfse, "cTribMun") or ""

        codigo_verificacao = (
            self._find_text(inf_nfse, "cVerif")
            or self._find_text(inf_nfse, "codigoVerificacao")
            or ""
        )

        cstat = self._find_text(inf_nfse, "cStat") or ""
        status = self._mapear_status(cstat)

        return self.criar_nota_padrao(
            chave_acesso=chave_acesso,
            numero=str(numero_nf),
            serie=str(serie),
            data_emissao=data_emissao,
            valor_total=valor_total,
            valor_servicos=valor_total,
            valor_iss=valor_iss,
            aliquota_iss=aliquota_iss,
            cnpj_prestador=cnpj_emitente,
            prestador_nome=nome_emitente,
            cnpj_tomador=cnpj_destinatario,
            tomador_nome=nome_destinatario,
            descricao_servico=descricao_servico,
            codigo_servico=codigo_servico,
            codigo_verificacao=codigo_verificacao,
            link_visualizacao="",
            xml_content=xml_doc,
            municipio_codigo=str(codigo_municipio),
            municipio_nome=nome_municipio,
            status=status,
            nsu=self._coerce_int(item_dfe.get("NSU"), 0),
        )

    def _mapear_status(self, cstat: str) -> str:
        codigo = str(cstat or "").strip()
        if codigo in {"100", "101", "102", "103", "104", "105", "106"}:
            return "Autorizada"
        if codigo in {"200", "201", "202"}:
            return "Cancelada"
        return "Autorizada"

    def _extrair_chave_acesso_nfse(self, inf_nfse: ET.Element, item_dfe: Dict[str, Any]) -> str:
        chave = str(item_dfe.get("ChaveAcesso") or "").strip()
        if chave and len(re.sub(r"\D", "", chave)) >= 44:
            return chave

        ident = str((inf_nfse.attrib or {}).get("Id") or "").strip()
        if ident:
            match = re.search(r"(\d{50})", ident)
            if match:
                return match.group(1)
            if ident.startswith("NFS"):
                return ident[3:]
            return ident

        return ""

    def _find_node(self, root: Optional[ET.Element], local_name: str) -> Optional[ET.Element]:
        if root is None:
            return None
        alvo = local_name.strip()
        for el in root.iter():
            if self._tag_local(el.tag) == alvo:
                return el
        return None

    def _find_text(self, root: Optional[ET.Element], local_name: str) -> Optional[str]:
        node = self._find_node(root, local_name)
        if node is None:
            return None
        texto = (node.text or "").strip()
        return texto or None

    def _tag_local(self, tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _coerce_int(self, valor: Any, default: int = 0) -> int:
        try:
            return int(str(valor).strip())
        except Exception:  # noqa: BLE001
            return int(default)

    def _to_float(self, valor: Any) -> float:
        if valor is None:
            return 0.0
        txt = str(valor).strip()
        if not txt:
            return 0.0

        # Formato pt-BR com milhar e decimal: 1.234,56
        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        # Formato decimal com virgula: 123,45
        elif "," in txt:
            txt = txt.replace(",", ".")

        try:
            return float(txt)
        except Exception:  # noqa: BLE001
            return 0.0

    def _nota_no_periodo(self, data_emissao: Optional[str], data_inicio: date, data_fim: date) -> bool:
        if not data_emissao:
            return False

        texto = str(data_emissao).strip()
        data_nota: Optional[date] = None

        try:
            data_nota = datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
        except Exception:  # noqa: BLE001
            pass

        if data_nota is None:
            try:
                data_nota = date.fromisoformat(texto[:10])
            except Exception:  # noqa: BLE001
                return False

        return data_inicio <= data_nota <= data_fim

    def processar_resposta(self, resposta: Dict) -> List[Dict]:
        """
        Mantido para compatibilidade com fluxo legado.
        No fluxo atual por certificado (ADN), o parse eh feito por XML no metodo
        _extrair_nota_do_xml.
        """
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

            except Exception as exc:  # noqa: BLE001
                self.log_warning(
                    f"Erro ao processar nota {nota_raw.get('numero', '?')}: {exc}"
                )
                continue

        return notas
