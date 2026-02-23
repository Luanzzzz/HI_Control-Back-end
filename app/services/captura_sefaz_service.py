"""
Captura de NF-e no DistribuicaoDFe (SEFAZ Nacional).
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import logging
import os
import re
import tempfile
import threading
import zlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None

from app.core.sefaz_config import AMBIENTE_PADRAO, DISTRIBUICAO_DFE_ENDPOINTS, UF_CODES

try:
    from app.services.certificado_service import CertificadoError
except Exception:  # pragma: no cover
    class CertificadoError(Exception):
        pass

logger = logging.getLogger(__name__)
SOAP_DISTRIBUICAO_ACTION = (
    "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
)
MOCK_CHAVES_ACESSO = {
    "35260112345678000190550010000001231123456789",
    "35260112345678000190550010000001241123456790",
    "35260112345678000190550010000001251123456791",
}


class SefazNetworkError(Exception):
    pass


class SefazTimeoutError(SefazNetworkError):
    pass


class CapturaService:
    def _coerce_int_env(self, key: str, default: int, min_value: int, max_value: int) -> int:
        try:
            value = int(str(os.getenv(key, str(default))).strip())
        except (TypeError, ValueError):
            value = default
        return max(min_value, min(max_value, value))

    def _ambiente_norm(self) -> str:
        ambiente = str(AMBIENTE_PADRAO or "producao").strip().lower()
        return ambiente if ambiente in {"producao", "homologacao"} else "producao"

    def _usar_pynfe_distribuicao(self) -> bool:
        return os.getenv("USE_PYNFE_DISTRIBUICAO", "false").strip().lower() == "true"

    def sincronizar_empresa(
        self,
        empresa_id: str,
        db,
        reparar_incompletas: bool = False,
        reset_cursor_recente: bool = False,
    ) -> Dict[str, Any]:
        inicio = datetime.now(timezone.utc)
        logger.info("Captura SEFAZ iniciada para empresa_id=%s", empresa_id)

        notas_novas = 0
        notas_atualizadas = 0
        nsu_inicio = 0
        nsu_fim = 0
        max_nsu = 0
        status = "erro"
        erro_mensagem: Optional[str] = None

        sync_state = self._obter_ou_criar_sync(db, empresa_id)
        if sync_state:
            nsu_inicio = int(sync_state.get("ultimo_nsu") or 0)
            nsu_fim = nsu_inicio
            max_nsu = int(sync_state.get("max_nsu") or 0)

        if reset_cursor_recente:
            self._resetar_cursor_nfse_token_bootstrap(db, empresa_id)

        progresso_inicio = datetime.now(timezone.utc)
        try:
            db.table("sync_empresas").update({"inicio_sync_at": progresso_inicio.isoformat()}).eq("empresa_id", empresa_id).execute()
        except Exception:  # noqa: BLE001
            logger.debug("Coluna inicio_sync_at indisponivel para empresa_id=%s", empresa_id)
        self._atualizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            percentual=2.0,
            etapa="iniciando",
            mensagem="Iniciando captura de notas...",
            processadas=0,
            estimadas=None,
            eta_segundos=None,
        )

        try:
            empresa = self._obter_empresa(db, empresa_id)
            if not empresa:
                erro_mensagem = "Empresa nao encontrada"
                status = self._atualizar_sync_erro_generico(db, empresa_id, erro_mensagem, sync_state)
                return self._resultado(status, 0, 0, nsu_fim, max_nsu, erro_mensagem)

            cnpj_empresa = self._normalizar_cnpj(empresa.get("cnpj"))
            if not cnpj_empresa:
                erro_mensagem = "CNPJ da empresa invalido"
                status = self._atualizar_sync_erro_generico(db, empresa_id, erro_mensagem, sync_state)
                return self._resultado(status, 0, 0, nsu_fim, max_nsu, erro_mensagem)

            use_mock = self._is_mock_enabled()
            if not use_mock:
                self._atualizar_sync_progresso(
                    db=db,
                    empresa_id=empresa_id,
                    percentual=8.0,
                    etapa="validando_certificado",
                    mensagem="Validando certificado digital...",
                    processadas=0,
                    estimadas=None,
                    eta_segundos=self._calcular_eta_segundos(progresso_inicio, 8.0),
                )
                self._limpar_notas_mock_antigas(db, empresa_id)
                if self._certificado_expirado_por_data(empresa.get("certificado_validade")):
                    erro_mensagem = "Certificado expirado"
                    self._marcar_sem_certificado(db, empresa_id, erro_mensagem)
                    return self._resultado("sem_certificado", 0, 0, nsu_fim, max_nsu, erro_mensagem)

                if not empresa.get("certificado_a1") or not empresa.get("certificado_senha_encrypted"):
                    erro_mensagem = "Certificado A1 nao configurado"
                    self._marcar_sem_certificado(db, empresa_id, erro_mensagem)
                    return self._resultado("sem_certificado", 0, 0, nsu_fim, max_nsu, erro_mensagem)

                cert_service = self._get_certificado_service()
                cert_bytes, _ = cert_service.carregar_certificado(
                    empresa["certificado_a1"],
                    empresa["certificado_senha_encrypted"],
                )
                senha_cert = cert_service.descriptografar_senha(empresa["certificado_senha_encrypted"])

                uf_codigo, uf_sigla = self._resolver_uf_codigo_empresa(empresa, cert_bytes, senha_cert)
                if uf_sigla and not str(empresa.get("estado") or "").strip():
                    self._persistir_estado_empresa(db, empresa_id, uf_sigla)

                if self._certificado_expirado_por_pfx(cert_bytes, senha_cert):
                    erro_mensagem = "Certificado expirado"
                    self._marcar_sem_certificado(db, empresa_id, erro_mensagem)
                    return self._resultado("sem_certificado", 0, 0, nsu_fim, max_nsu, erro_mensagem)

            self._atualizar_sync_progresso(
                db=db,
                empresa_id=empresa_id,
                percentual=12.0,
                etapa="consultando_sefaz",
                mensagem="Consultando documentos no SEFAZ...",
                processadas=0,
                estimadas=None,
                eta_segundos=self._calcular_eta_segundos(progresso_inicio, 12.0),
            )

            def _on_lote_distribuicao(
                pagina: int,
                cstat_cb: str,
                ult_nsu_cb: int,
                max_nsu_cb: int,
                docs_total_cb: int,
            ) -> None:
                percentual = self._estimar_percentual_consulta(
                    pagina=pagina,
                    nsu_inicio=nsu_inicio,
                    ult_nsu=ult_nsu_cb,
                    max_nsu=max_nsu_cb,
                )
                estimadas: Optional[int] = None
                processadas = int(max(0, docs_total_cb))
                if int(max_nsu_cb or 0) > int(nsu_inicio or 0):
                    estimadas = int(max(0, int(max_nsu_cb) - int(nsu_inicio or 0)))
                    processadas = int(max(processadas, max(0, int(ult_nsu_cb or 0) - int(nsu_inicio or 0))))
                    if estimadas and processadas > estimadas:
                        estimadas = processadas
                self._atualizar_sync_progresso(
                    db=db,
                    empresa_id=empresa_id,
                    percentual=percentual,
                    etapa="consultando_sefaz",
                    mensagem=f"Capturando lotes SEFAZ (pagina {pagina}, cStat {cstat_cb})",
                    processadas=processadas,
                    estimadas=estimadas,
                    eta_segundos=self._calcular_eta_segundos(progresso_inicio, percentual),
                )

            retorno = self._coletar_documentos_distribuicao(
                empresa_id=empresa_id,
                cnpj_empresa=cnpj_empresa,
                nsu_inicio=nsu_inicio,
                use_mock=use_mock,
                cert_bytes=cert_bytes if not use_mock else None,
                senha_cert=senha_cert if not use_mock else None,
                uf_codigo=uf_codigo if not use_mock else "35",
                on_lote_callback=_on_lote_distribuicao,
            )
            cstat = retorno.get("cstat")
            motivo = retorno.get("xmotivo", "")
            nsu_fim = int(retorno.get("ult_nsu") or nsu_inicio)
            max_nsu_retorno = int(retorno.get("max_nsu") or 0)
            max_nsu = max(int(max_nsu or 0), max_nsu_retorno, nsu_fim)

            documentos = retorno.get("documentos", [])
            if cstat not in {"137", "138", "656"}:
                erro_mensagem = f"SEFAZ cStat={cstat}: {motivo}"
                status = self._atualizar_sync_erro_sefaz(
                    db=db,
                    empresa_id=empresa_id,
                    mensagem=erro_mensagem,
                    sync_state=sync_state,
                    ultimo_nsu=nsu_fim,
                    max_nsu=max_nsu,
                )
                return self._resultado(status, 0, 0, nsu_fim, max_nsu, erro_mensagem)

            payload = []
            schemas: Dict[str, int] = {}
            for doc in documentos:
                schema = str(doc.get("schema") or "desconhecido")
                schemas[schema] = schemas.get(schema, 0) + 1
                nota = self._montar_payload_nota(doc, cnpj_empresa, empresa_id)
                if nota:
                    payload.append(nota)

            logger.info(
                "Documentos distribuidos empresa_id=%s total_docs=%s notas_validas=%s schemas=%s",
                empresa_id,
                len(documentos),
                len(payload),
                schemas,
            )

            self._atualizar_sync_progresso(
                db=db,
                empresa_id=empresa_id,
                percentual=72.0,
                etapa="processando_documentos",
                mensagem=f"Processando {len(payload)} documentos capturados...",
                processadas=len(payload),
                estimadas=len(payload) if payload else None,
                eta_segundos=self._calcular_eta_segundos(progresso_inicio, 72.0),
            )

            notas_novas, notas_atualizadas = self._upsert_notas(db, payload)
            notas_processadas = len(payload)

            aviso_sync: Optional[str] = None
            fallback_bloqueante = False
            if not use_mock and self._deve_executar_fallback_nfse(cstat, len(payload)):
                self._atualizar_sync_progresso(
                    db=db,
                    empresa_id=empresa_id,
                    percentual=82.0,
                    etapa="fallback_nfse",
                    mensagem="Consultando fallback NFS-e (Sistema Nacional)...",
                    processadas=notas_processadas,
                    estimadas=None,
                    eta_segundos=self._calcular_eta_segundos(progresso_inicio, 82.0),
                )
                fallback_nfse = self._executar_fallback_nfse(db, empresa)
                notas_novas += fallback_nfse["notas_novas"]
                notas_atualizadas += fallback_nfse["notas_atualizadas"]
                notas_processadas += fallback_nfse["notas_processadas"]

                logger.info(
                    "Fallback NFS-e empresa_id=%s executado=%s sucesso=%s processadas=%s novas=%s atualizadas=%s mensagem=%s",
                    empresa_id,
                    fallback_nfse["executado"],
                    fallback_nfse["sucesso"],
                    fallback_nfse["notas_processadas"],
                    fallback_nfse["notas_novas"],
                    fallback_nfse["notas_atualizadas"],
                    fallback_nfse["mensagem"],
                )

                if fallback_nfse["executado"] and not fallback_nfse["sucesso"] and not notas_processadas:
                    aviso_sync = fallback_nfse["mensagem"]
                    fallback_bloqueante = self._fallback_nfse_bloqueia_sync(
                        str(fallback_nfse.get("erro_tipo") or "")
                    )

            if fallback_bloqueante and aviso_sync:
                self._atualizar_sync_alerta_config(
                    db=db,
                    empresa_id=empresa_id,
                    ultimo_nsu=nsu_fim,
                    max_nsu=max_nsu,
                    mensagem=aviso_sync,
                    notas_processadas=notas_processadas,
                    notas_novas=notas_novas,
                )
                erro_mensagem = aviso_sync
                status = "erro"
                return self._resultado(status, notas_novas, notas_atualizadas, nsu_fim, max_nsu, aviso_sync)

            if cstat == "656":
                self._atualizar_sync_cooldown(
                    db,
                    empresa_id,
                    nsu_fim,
                    max_nsu,
                    horas=1,
                    sync_state=sync_state,
                    notas_processadas=notas_processadas,
                    notas_novas=notas_novas,
                    mensagem=aviso_sync,
                )
            else:
                self._atualizar_sync_ok(
                    db,
                    empresa_id,
                    sync_state,
                    nsu_fim,
                    max_nsu,
                    notas_processadas,
                    notas_novas,
                    mensagem=aviso_sync,
                )

            self._atualizar_sync_progresso(
                db=db,
                empresa_id=empresa_id,
                percentual=95.0,
                etapa="finalizando",
                mensagem="Finalizando sincronizacao...",
                processadas=notas_processadas,
                estimadas=notas_processadas if notas_processadas > 0 else None,
                eta_segundos=self._calcular_eta_segundos(progresso_inicio, 95.0),
            )
            if aviso_sync and not erro_mensagem:
                erro_mensagem = aviso_sync

            if reparar_incompletas:
                limite_reparo = self._coerce_int_env("CAPTURA_REPARO_INCOMPLETAS_LIMITE", 1200, 50, 10000)
                reparadas = self.reprocessar_notas_incompletas(
                    db=db,
                    empresa_id=empresa_id,
                    limite=limite_reparo,
                )
                if reparadas > 0:
                    notas_atualizadas += reparadas
                    logger.info(
                        "Reparo de notas incompletas aplicado empresa_id=%s reparadas=%s",
                        empresa_id,
                        reparadas,
                    )

            status = "ok"
            return self._resultado(status, notas_novas, notas_atualizadas, nsu_fim, max_nsu, aviso_sync)

        except SefazTimeoutError as exc:
            erro_mensagem = f"Timeout de rede: {exc}"
            status = self._atualizar_sync_erro_rede(db, empresa_id, erro_mensagem, sync_state)
            return self._resultado(status, notas_novas, notas_atualizadas, nsu_fim, max_nsu, erro_mensagem)
        except SefazNetworkError as exc:
            erro_mensagem = f"Erro de rede: {exc}"
            status = self._atualizar_sync_erro_rede(db, empresa_id, erro_mensagem, sync_state)
            return self._resultado(status, notas_novas, notas_atualizadas, nsu_fim, max_nsu, erro_mensagem)
        except CertificadoError as exc:
            erro_mensagem = f"Erro de certificado: {exc}"
            self._marcar_sem_certificado(db, empresa_id, erro_mensagem)
            return self._resultado("sem_certificado", notas_novas, notas_atualizadas, nsu_fim, max_nsu, erro_mensagem)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro inesperado na captura SEFAZ")
            erro_mensagem = f"Erro inesperado: {exc}"
            status = self._atualizar_sync_erro_generico(db, empresa_id, erro_mensagem, sync_state)
            return self._resultado(status, notas_novas, notas_atualizadas, nsu_fim, max_nsu, erro_mensagem)
        finally:
            fim = datetime.now(timezone.utc)
            self._registrar_sync_log(
                db=db,
                empresa_id=empresa_id,
                iniciado_em=inicio,
                finalizado_em=fim,
                status=status if status in {"ok", "erro", "parcial"} else ("erro" if status != "ok" else "ok"),
                notas_novas=notas_novas,
                notas_atualizadas=notas_atualizadas,
                nsu_inicio=nsu_inicio,
                nsu_fim=nsu_fim,
                erro_detalhes=erro_mensagem,
                duracao_ms=int((fim - inicio).total_seconds() * 1000),
            )

    def _coletar_documentos_distribuicao(
        self,
        empresa_id: str,
        cnpj_empresa: str,
        nsu_inicio: int,
        use_mock: bool,
        cert_bytes: Optional[bytes],
        senha_cert: Optional[str],
        uf_codigo: str,
        on_lote_callback: Optional[Callable[[int, str, int, int, int], None]] = None,
    ) -> Dict[str, Any]:
        max_paginas = 1 if use_mock else self._coerce_int_env("SEFAZ_DFE_MAX_PAGINAS", 6, 1, 20)
        documentos: List[Dict[str, Any]] = []
        ult_nsu = int(nsu_inicio or 0)
        max_nsu = int(nsu_inicio or 0)
        cstat_final = ""
        xmotivo_final = ""

        for pagina in range(1, max_paginas + 1):
            if use_mock:
                logger.info("USE_MOCK_SEFAZ=true | usando mock de distribuicao DFe")
                resposta_xml = self._consultar_distribuicao_mock(cnpj_empresa, ult_nsu)
            else:
                resposta_xml = self._consultar_distribuicao_dfe(
                    cnpj=cnpj_empresa,
                    ultimo_nsu=ult_nsu,
                    cert_bytes=cert_bytes or b"",
                    senha_cert=senha_cert or "",
                    uf_codigo=uf_codigo,
                )

            retorno = self._parse_retorno_distribuicao(resposta_xml)
            cstat = str(retorno.get("cstat") or "")
            xmotivo = str(retorno.get("xmotivo") or "")
            novo_ult_nsu = int(retorno.get("ult_nsu") or ult_nsu)
            novo_max_nsu = int(retorno.get("max_nsu") or 0)
            docs_lote = retorno.get("documentos", []) or []

            max_nsu = max(max_nsu, novo_max_nsu, novo_ult_nsu)
            cstat_final = cstat
            xmotivo_final = xmotivo

            logger.info(
                "retDistDFeInt empresa_id=%s pagina=%s cStat=%s ultNSU=%s maxNSU=%s docs=%s",
                empresa_id,
                pagina,
                cstat,
                novo_ult_nsu,
                max_nsu,
                len(docs_lote),
            )

            if on_lote_callback:
                try:
                    on_lote_callback(
                        pagina,
                        cstat,
                        int(novo_ult_nsu or 0),
                        int(max_nsu or 0),
                        int(len(documentos) + len(docs_lote)),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("Falha ao atualizar callback de progresso da distribuicao", exc_info=True)

            if cstat == "138":
                documentos.extend(docs_lote)
                if novo_ult_nsu <= ult_nsu:
                    logger.warning(
                        "Distribuicao sem avancar NSU (empresa_id=%s, ult_nsu=%s, novo_ult_nsu=%s)",
                        empresa_id,
                        ult_nsu,
                        novo_ult_nsu,
                    )
                    ult_nsu = novo_ult_nsu
                    break
                ult_nsu = novo_ult_nsu
                if max_nsu > 0 and ult_nsu >= max_nsu:
                    break
                continue

            ult_nsu = novo_ult_nsu
            break

        return {
            "cstat": cstat_final,
            "xmotivo": xmotivo_final,
            "ult_nsu": ult_nsu,
            "max_nsu": max_nsu,
            "documentos": documentos,
        }

    def _deve_executar_fallback_nfse(self, cstat: str, dfe_notas_processadas: int) -> bool:
        if os.getenv("CAPTURA_NFSE_FALLBACK_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return False
        if dfe_notas_processadas > 0:
            return False
        # 137: sem documentos; 138: documentos nao convertidos para nota; 656: consumo indevido.
        return str(cstat or "") in {"137", "138", "656"}

    def _fallback_nfse_bloqueia_sync(self, erro_tipo: str) -> bool:
        strict_mode = os.getenv("CAPTURA_NFSE_FALLBACK_STRICT_MODE", "false").strip().lower()
        if strict_mode in {"0", "false", "no", "off"}:
            return False

        erro = (erro_tipo or "").strip().lower()
        return erro in {
            "credenciais_ausentes",
            "nfse_config_error",
            "nfse_auth_error",
            "nfse_search_error",
        }

    def _executar_fallback_nfse(self, db, empresa: Dict[str, Any]) -> Dict[str, Any]:
        empresa_id = str(empresa.get("id") or "")
        if not empresa_id:
            return {
                "executado": False,
                "sucesso": False,
                "notas_processadas": 0,
                "notas_novas": 0,
                "notas_atualizadas": 0,
                "mensagem": "empresa_id invalido para fallback NFS-e",
                "erro_tipo": "empresa_invalida",
            }

        usuario_id = str(empresa.get("usuario_id") or "") or None

        notas_antes = self._contar_notas_empresa(db, empresa_id)
        dias_recente = self._coerce_int_env("CAPTURA_NFSE_FALLBACK_DIAS", 365, 1, 730)
        dias_backfill = max(
            dias_recente,
            self._coerce_int_env("CAPTURA_NFSE_FALLBACK_DIAS_BACKFILL", 3650, dias_recente, 7300),
        )
        usar_janela_longa = os.getenv("CAPTURA_NFSE_FALLBACK_LONG_WINDOW", "true").strip().lower()
        if usar_janela_longa in {"0", "false", "no", "off"}:
            dias = dias_backfill if notas_antes == 0 else dias_recente
        else:
            dias = dias_backfill

        data_fim = date.today()
        data_inicio = data_fim - timedelta(days=dias)

        try:
            from app.services.nfse.nfse_service import nfse_service

            resultado = self._run_async_coro(
                nfse_service.buscar_notas_empresa(
                    empresa_id=empresa_id,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    usuario_id=usuario_id,
                )
            )
            resultado = resultado if isinstance(resultado, dict) else {}
            sucesso = bool(resultado.get("success", False))
            notas_processadas = int(resultado.get("quantidade") or 0)
            mensagem = str(resultado.get("mensagem") or "").strip() or None
            erro_tipo = str(resultado.get("erro_tipo") or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha no fallback NFS-e para empresa_id=%s", empresa_id)
            sucesso = False
            notas_processadas = 0
            mensagem = f"Falha no fallback NFS-e: {exc}"
            erro_tipo = str(getattr(exc, "codigo", "") or exc.__class__.__name__).strip()

        notas_depois = self._contar_notas_empresa(db, empresa_id)
        notas_novas = max(0, notas_depois - notas_antes)
        notas_atualizadas = max(0, notas_processadas - notas_novas)

        return {
            "executado": True,
            "sucesso": sucesso,
            "notas_processadas": int(notas_processadas),
            "notas_novas": int(notas_novas),
            "notas_atualizadas": int(notas_atualizadas),
            "mensagem": mensagem,
            "erro_tipo": erro_tipo,
        }

    def _run_async_coro(self, coro):
        try:
            asyncio.get_running_loop()
            running_loop = True
        except RuntimeError:
            running_loop = False

        if not running_loop:
            return asyncio.run(coro)

        result_box: Dict[str, Any] = {}
        error_box: Dict[str, Exception] = {}

        def _runner():
            try:
                result_box["value"] = asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                error_box["error"] = exc

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        timeout_seg = self._coerce_int_env("CAPTURA_FALLBACK_ASYNC_TIMEOUT_SECONDS", 180, 30, 1200)
        t.join(timeout=timeout_seg)
        if t.is_alive():
            raise TimeoutError(
                f"Timeout aguardando resposta do fallback NFS-e apos {timeout_seg}s"
            )

        if "error" in error_box:
            raise error_box["error"]
        return result_box.get("value")

    def _consultar_distribuicao_dfe(
        self,
        cnpj: str,
        ultimo_nsu: int,
        cert_bytes: bytes,
        senha_cert: str,
        uf_codigo: str,
    ) -> str:
        ambiente = self._ambiente_norm()
        endpoint = DISTRIBUICAO_DFE_ENDPOINTS.get(ambiente, DISTRIBUICAO_DFE_ENDPOINTS["producao"])
        logger.info("Consultando endpoint distribuicao: %s | ambiente=%s", endpoint, ambiente)

        if not self._usar_pynfe_distribuicao():
            logger.info("USE_PYNFE_DISTRIBUICAO=false | usando SOAP direto")
            return self._consultar_via_soap(cnpj, ultimo_nsu, cert_bytes, senha_cert, endpoint, uf_codigo)

        try:
            return self._consultar_via_pynfe(cnpj, ultimo_nsu, cert_bytes, senha_cert)
        except Exception as exc:  # noqa: BLE001
            logger.info("PyNFE indisponivel/falhou (%s). Usando SOAP direto.", exc)
            return self._consultar_via_soap(cnpj, ultimo_nsu, cert_bytes, senha_cert, endpoint, uf_codigo)

    def _consultar_distribuicao_mock(self, cnpj: str, ultimo_nsu: int) -> str:
        from app.adapters.mock_sefaz_client import get_distribuicao_client

        client = get_distribuicao_client()
        if client is None:
            raise RuntimeError("USE_MOCK_SEFAZ habilitado, mas mock client indisponivel")
        return client.consultar(cnpj=cnpj, nsu_inicial=ultimo_nsu)

    def _consultar_via_pynfe(
        self,
        cnpj: str,
        ultimo_nsu: int,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> str:
        from pynfe.processamento.comunicacao import ComunicacaoSefaz

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pfx") as cert_tmp:
            cert_tmp.write(cert_bytes)
            cert_path = cert_tmp.name

        try:
            homologacao = self._ambiente_norm() != "producao"
            comunicacao = ComunicacaoSefaz(uf="AN", certificado=cert_path, senha=senha_cert, homologacao=homologacao)
            nsu = str(max(0, int(ultimo_nsu))).zfill(15)

            if hasattr(comunicacao, "consulta_distribuicao_nfe"):
                resposta = comunicacao.consulta_distribuicao_nfe(cnpj=cnpj, ultimo_nsu=nsu)
            elif hasattr(comunicacao, "consultar_distribuicao_nfe"):
                resposta = comunicacao.consultar_distribuicao_nfe(cnpj=cnpj, ultimo_nsu=nsu)
            else:
                raise RuntimeError("Metodo de distribuicao nao encontrado no PyNFE")

            return self._normalizar_resposta_xml(resposta)
        finally:
            try:
                os.remove(cert_path)
            except OSError:
                pass

    def _consultar_via_soap(
        self,
        cnpj: str,
        ultimo_nsu: int,
        cert_bytes: bytes,
        senha_cert: str,
        endpoint: str,
        uf_codigo: str,
    ) -> str:
        import requests

        cert_pem_path, key_pem_path = self._gerar_cert_key_temp(cert_bytes, senha_cert)
        nsu = str(max(0, int(ultimo_nsu))).zfill(15)
        payload = self._montar_envelope_distribuicao(cnpj, nsu, uf_codigo)
        headers = {
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_DISTRIBUICAO_ACTION}"',
            "SOAPAction": f'"{SOAP_DISTRIBUICAO_ACTION}"',
        }
        logger.info("SOAP distribuicao: endpoint=%s cnpj=%s ult_nsu=%s cUFAutor(body)=%s", endpoint, cnpj, nsu, uf_codigo)

        try:
            response = requests.post(
                endpoint,
                data=payload.encode("utf-8"),
                headers=headers,
                cert=(cert_pem_path, key_pem_path),
                timeout=60,
            )
            response.raise_for_status()
            return response.text
        except requests.Timeout as exc:
            raise SefazTimeoutError(str(exc)) from exc
        except requests.RequestException as exc:
            raise SefazNetworkError(str(exc)) from exc
        finally:
            for path in (cert_pem_path, key_pem_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

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
            raise CertificadoError("PFX invalido sem certificado/chave privada")

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

    def _montar_envelope_distribuicao(self, cnpj: str, ult_nsu: str, uf_codigo: str) -> str:
        tp_amb = "1" if self._ambiente_norm() == "producao" else "2"
        uf_codigo = str(uf_codigo or "").zfill(2)
        if not (len(uf_codigo) == 2 and uf_codigo.isdigit()):
            uf_codigo = "35"
        if uf_codigo == "91":
            uf_codigo = "35"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"
                 xmlns:nfed="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
  <soap12:Header>
    <nfed:nfeCabecMsg>
      <cUFAutor>{uf_codigo}</cUFAutor>
      <versaoDados>1.01</versaoDados>
    </nfed:nfeCabecMsg>
  </soap12:Header>
  <soap12:Body>
    <nfed:nfeDistDFeInteresse>
      <nfed:nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{tp_amb}</tpAmb>
          <cUFAutor>{uf_codigo}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <distNSU>
            <ultNSU>{ult_nsu}</ultNSU>
          </distNSU>
        </distDFeInt>
      </nfed:nfeDadosMsg>
    </nfed:nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

    def _parse_retorno_distribuicao(self, xml_retorno: str) -> Dict[str, Any]:
        if etree is None:
            raise RuntimeError("lxml nao disponivel")

        root = etree.fromstring(xml_retorno.encode("utf-8"))
        ret_nodes = root.xpath("//*[local-name()='retDistDFeInt']")
        ret = ret_nodes[0] if ret_nodes else root

        cstat = self._find_text(ret, "cStat") or ""
        xmotivo = self._find_text(ret, "xMotivo") or ""
        ult_nsu = self._parse_int(self._find_text(ret, "ultNSU")) or 0
        max_nsu = self._parse_int(self._find_text(ret, "maxNSU")) or 0

        documentos: List[Dict[str, Any]] = []
        for doc_zip in ret.xpath(".//*[local-name()='docZip']"):
            xml_doc = self._extrair_xml_doczip(doc_zip)
            if not xml_doc:
                continue
            nsu = self._parse_int(doc_zip.get("NSU"))
            if nsu is None:
                nsu = self._parse_int(self._extrair_texto_do_xml(xml_doc, "NSU")) or 0
            documentos.append(
                {
                    "nsu": int(nsu),
                    "schema": doc_zip.get("schema") or "",
                    "xml": xml_doc,
                }
            )

        return {
            "cstat": cstat,
            "xmotivo": xmotivo,
            "ult_nsu": ult_nsu,
            "max_nsu": max_nsu,
            "documentos": documentos,
        }

    def _extrair_xml_doczip(self, doc_zip) -> Optional[str]:
        # Fluxo oficial SEFAZ: docZip em base64 (com gzip no payload).
        conteudo = (doc_zip.text or "").strip()
        if conteudo:
            xml_doc = self._descompactar_doc_zip(conteudo)
            if xml_doc:
                return xml_doc

        # Fallback para mocks/fixtures com XML inline dentro do docZip.
        if etree is None or len(doc_zip) == 0:
            return None

        candidatos = []
        for child in doc_zip:
            nome = child.tag.split("}")[-1] if isinstance(child.tag, str) else ""
            if nome in {"resNFe", "procNFe", "NFe", "resCTe", "resNFCe"}:
                candidatos.append(child)

        target = candidatos[0] if candidatos else doc_zip[-1]
        try:
            return etree.tostring(target, encoding="unicode")
        except Exception:  # noqa: BLE001
            return None

    def _descompactar_doc_zip(self, conteudo_base64: str) -> Optional[str]:
        try:
            bruto = base64.b64decode(conteudo_base64)
        except Exception:  # noqa: BLE001
            return None

        candidatos: List[bytes] = [bruto]
        for fn in (
            lambda b: gzip.decompress(b),
            lambda b: zlib.decompress(b),
            lambda b: zlib.decompress(b, -zlib.MAX_WBITS),
        ):
            try:
                valor = fn(bruto)
                if valor:
                    candidatos.append(valor)
            except Exception:  # noqa: BLE001
                continue

        for payload in candidatos:
            texto = self._bytes_para_texto(payload)
            if not texto:
                continue
            if self._parece_xml_valido(texto):
                return texto

        return None

    def _bytes_para_texto(self, payload: bytes) -> Optional[str]:
        for encoding in ("utf-8", "utf-16", "utf-16le", "utf-16be", "latin-1", "cp1252"):
            try:
                texto = payload.decode(encoding, errors="ignore").strip()
                if texto:
                    return texto
            except Exception:  # noqa: BLE001
                continue
        return None

    def _parece_xml_valido(self, conteudo: str) -> bool:
        texto = (conteudo or "").lstrip("\ufeff \t\r\n")
        if not texto.startswith("<"):
            return False
        if etree is None:
            return True
        try:
            etree.fromstring(texto.encode("utf-8", errors="ignore"))
            return True
        except Exception:  # noqa: BLE001
            return False

    def _montar_payload_nota(self, doc: Dict[str, Any], cnpj_empresa: str, empresa_id: str) -> Optional[Dict[str, Any]]:
        xml_doc = doc.get("xml")
        if not xml_doc:
            return None

        schema = str(doc.get("schema") or "").strip().lower()
        if "evento" in schema and "procnfe" not in schema and "resnfe" not in schema:
            # Eventos (cancelamento/ciencia/etc) nao devem sobrescrever dados da nota.
            return None

        chave = self._extrair_chave_acesso(xml_doc)
        if not chave:
            return None

        modelo = self._extrair_primeiro_texto_do_xml(xml_doc, ["mod", "modelo"]) or chave[20:22]
        numero_nf = self._extrair_primeiro_texto_do_xml(xml_doc, ["nNF", "nNFe", "nDoc"]) or chave[25:34].lstrip("0") or chave[25:34]
        serie = self._extrair_primeiro_texto_do_xml(xml_doc, ["serie", "nSerie"]) or chave[22:25].lstrip("0") or chave[22:25]
        data_emissao = self._normalizar_data(
            self._extrair_primeiro_texto_do_xml(
                xml_doc,
                ["dhEmi", "dEmi", "dhSaiEnt", "dhRegEvento", "dhEvento", "dhRecbto", "dhProc"],
            )
        )
        valor_total = self._normalizar_decimal(
            self._extrair_primeiro_texto_do_xml(
                xml_doc,
                ["vNF", "vLiq", "vProd", "vPrest", "vTPrest"],
            )
        )

        cnpj_emitente = self._normalizar_cnpj(
            self._extrair_primeiro_texto_do_xml(xml_doc, ["CNPJEmit", "CNPJ", "emit_CNPJ"])
        ) or self._normalizar_cnpj(chave[6:20])
        cnpj_destinatario = self._normalizar_cnpj(
            self._extrair_primeiro_texto_do_xml(xml_doc, ["CNPJDest", "dest_CNPJ", "CPFDest"])
        )

        nome_emitente = (
            self._extrair_primeiro_texto_do_xml(xml_doc, ["xNomeEmit", "xFant", "xNome"])
            or ""
        )
        nome_destinatario = self._extrair_primeiro_texto_do_xml(xml_doc, ["xNomeDest", "xNome"])

        tipo_operacao = "entrada"
        if cnpj_emitente == cnpj_empresa:
            tipo_operacao = "saida"
        elif cnpj_destinatario == cnpj_empresa:
            tipo_operacao = "entrada"
        else:
            tp_nf = self._extrair_texto_do_xml(xml_doc, "tpNF")
            if tp_nf == "1":
                tipo_operacao = "saida"

        tp_evento = self._extrair_texto_do_xml(xml_doc, "tpEvento")
        if tp_evento and valor_total <= 0 and not self._extrair_texto_do_xml(xml_doc, "nNF"):
            # XML de evento sem corpo da nota: nao deve sobrescrever dados da nota fiscal.
            return None
        situacao = self._mapear_situacao(
            self._extrair_primeiro_texto_do_xml(xml_doc, ["cSitNFe", "cStat", "cSit", "cStatProc"]) or tp_evento
        )
        if tp_evento in {"110111", "110112", "110110"}:
            situacao = "cancelada"
        elif situacao == "processando" and (valor_total > 0 or numero_nf):
            situacao = "autorizada"

        protocolo = self._extrair_texto_do_xml(xml_doc, "nProt")
        xml_resumo = xml_doc if ("resNFe" in (doc.get("schema") or "") or "<resNFe" in xml_doc) else None

        if not numero_nf and valor_total <= 0 and not nome_emitente:
            # Payload muito incompleto tende a vir de eventos/artefatos que nao devem gerar nota.
            return None

        return {
            "empresa_id": empresa_id,
            "chave_acesso": chave,
            "numero_nf": numero_nf,
            "serie": serie,
            "tipo_nf": self._mapear_tipo_nf(modelo),
            "modelo": modelo,
            "data_emissao": data_emissao,
            "valor_total": valor_total,
            "cnpj_emitente": self._formatar_cnpj(cnpj_emitente) if cnpj_emitente else "00.000.000/0000-00",
            "nome_emitente": nome_emitente[:255],
            "cnpj_destinatario": self._formatar_cnpj(cnpj_destinatario) if cnpj_destinatario else None,
            "nome_destinatario": nome_destinatario[:255] if nome_destinatario else None,
            "situacao": situacao,
            "protocolo": protocolo,
            "nsu": int(doc.get("nsu") or 0),
            "tipo_operacao": tipo_operacao,
            "fonte": "sefaz_nacional",
            "xml_completo": xml_doc,
            "xml_resumo": xml_resumo,
            "ambiente": self._ambiente_norm(),
        }

    def _upsert_notas(self, db, payload: List[Dict[str, Any]]) -> Tuple[int, int]:
        if not payload:
            return 0, 0

        dedup: Dict[str, Dict[str, Any]] = {}
        for item in payload:
            chave = item["chave_acesso"]
            atual = dedup.get(chave)
            if atual is None or self._deve_substituir_payload_nota(atual, item):
                dedup[chave] = item

        lista = list(dedup.values())
        chaves = list(dedup.keys())

        existentes_resp = db.table("notas_fiscais").select("chave_acesso").in_("chave_acesso", chaves).execute()
        existentes = {x["chave_acesso"] for x in (existentes_resp.data or []) if x.get("chave_acesso")}

        db.table("notas_fiscais").upsert(lista, on_conflict="chave_acesso").execute()

        novas = len([k for k in chaves if k not in existentes])
        atualizadas = len(chaves) - novas
        return novas, atualizadas

    def _deve_substituir_payload_nota(self, atual: Dict[str, Any], novo: Dict[str, Any]) -> bool:
        score_atual = self._qualidade_payload_nota(atual)
        score_novo = self._qualidade_payload_nota(novo)
        if score_novo != score_atual:
            return score_novo > score_atual

        return int(novo.get("nsu") or 0) >= int(atual.get("nsu") or 0)

    def _qualidade_payload_nota(self, payload: Dict[str, Any]) -> int:
        score = 0
        if float(payload.get("valor_total") or 0) > 0:
            score += 20
        if str(payload.get("situacao") or "").strip().lower() != "processando":
            score += 12
        if str(payload.get("numero_nf") or "").strip():
            score += 6
        if str(payload.get("nome_emitente") or "").strip():
            score += 4
        if str(payload.get("cnpj_emitente") or "").strip():
            score += 3
        if str(payload.get("xml_completo") or "").strip():
            score += 2
        return score

    def reprocessar_notas_incompletas(self, db, empresa_id: str, limite: int = 1200) -> int:
        """
        Reprocessa notas com valor_total=0 ou situacao=processando usando o XML bruto salvo.
        """
        try:
            empresa = self._obter_empresa(db, empresa_id)
            cnpj_empresa = self._normalizar_cnpj((empresa or {}).get("cnpj")) or ""
            consulta = (
                db.table("notas_fiscais")
                .select("id, chave_acesso, tipo_nf, nsu, valor_total, situacao, xml_completo")
                .eq("empresa_id", empresa_id)
                .not_.is_("xml_completo", "null")
                .order("data_emissao", desc=True)
                .limit(max(10, int(limite)))
                .execute()
            )
            linhas = consulta.data or []
            if not linhas:
                return 0

            candidatos = []
            for row in linhas:
                tipo_nf = str(row.get("tipo_nf") or "").upper()
                if tipo_nf not in {"NFE", "NFCE", "CTE"}:
                    continue
                valor = float(row.get("valor_total") or 0)
                situacao = str(row.get("situacao") or "").strip().lower()
                if valor > 0 and situacao != "processando":
                    continue
                xml_doc = str(row.get("xml_completo") or "").strip()
                if not xml_doc:
                    continue
                candidatos.append(row)

            if not candidatos:
                return 0

            payloads: List[Dict[str, Any]] = []
            for row in candidatos:
                doc = {
                    "xml": row.get("xml_completo"),
                    "schema": "reprocess",
                    "nsu": row.get("nsu") or 0,
                }
                payload = self._montar_payload_nota(doc, cnpj_empresa, empresa_id)
                if not payload:
                    continue
                payload["chave_acesso"] = str(row.get("chave_acesso") or payload.get("chave_acesso") or "").strip()
                if not payload["chave_acesso"]:
                    continue
                valor_antigo = float(row.get("valor_total") or 0)
                if float(payload.get("valor_total") or 0) <= 0 and valor_antigo > 0:
                    payload["valor_total"] = valor_antigo
                situacao_antiga = str(row.get("situacao") or "").strip().lower()
                if payload.get("situacao") == "processando" and situacao_antiga and situacao_antiga != "processando":
                    payload["situacao"] = situacao_antiga
                payloads.append(payload)

            if not payloads:
                return 0

            _, atualizadas = self._upsert_notas(db, payloads)
            return int(atualizadas)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao reprocessar notas incompletas da empresa_id=%s", empresa_id)
            return 0

    def _obter_empresa(self, db, empresa_id: str) -> Optional[Dict[str, Any]]:
        resp = (
            db.table("empresas")
            .select(
                "id, usuario_id, cnpj, ativa, deleted_at, estado, municipio_codigo, "
                "certificado_a1, certificado_senha_encrypted, certificado_validade"
            )
            .eq("id", empresa_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def _resolver_uf_codigo_empresa(
        self,
        empresa: Dict[str, Any],
        cert_bytes: Optional[bytes] = None,
        senha_cert: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        municipio_codigo = str(empresa.get("municipio_codigo") or "").strip()
        if len(municipio_codigo) >= 2 and municipio_codigo[:2].isdigit():
            uf_codigo = municipio_codigo[:2]
            return uf_codigo, self._uf_sigla_por_codigo(uf_codigo)

        estado = str(empresa.get("estado") or "").strip().upper()
        if estado:
            uf_codigo = UF_CODES.get(estado)
            if uf_codigo:
                return uf_codigo, estado

        uf_cert = self._extrair_uf_do_certificado(cert_bytes, senha_cert or "")
        if uf_cert and uf_cert in UF_CODES:
            logger.info(
                "UF resolvida via certificado digital: %s (empresa_id=%s)",
                uf_cert,
                empresa.get("id"),
            )
            return UF_CODES[uf_cert], uf_cert

        # Fallback para manter o XML valido mesmo sem UF cadastrada na empresa.
        # Usamos uma UF autorizadora valida (35/SP) quando nao ha qualquer pista
        # de UF. Esse caso deve ser raro apos extracao via certificado.
        logger.warning(
            "Empresa sem estado/municipio_codigo. Usando cUFAutor=35 (fallback). "
            "empresa_id=%s",
            empresa.get("id"),
        )
        return "35", None

    def _persistir_estado_empresa(self, db, empresa_id: str, estado: str) -> None:
        try:
            db.table("empresas").update({"estado": estado}).eq("id", empresa_id).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao persistir estado deduzido no cadastro da empresa_id=%s", empresa_id)

    def _uf_sigla_por_codigo(self, uf_codigo: str) -> Optional[str]:
        for sigla, codigo in UF_CODES.items():
            if str(codigo).zfill(2) == str(uf_codigo).zfill(2):
                return sigla
        return None

    def _extrair_uf_do_certificado(self, cert_bytes: Optional[bytes], senha_cert: str) -> Optional[str]:
        if not cert_bytes:
            return None
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography.x509.oid import NameOID

            senha_bytes = senha_cert.encode("utf-8") if senha_cert else None
            _, cert, _ = pkcs12.load_key_and_certificates(cert_bytes, senha_bytes)
            if cert is None:
                return None

            attrs = cert.subject.get_attributes_for_oid(NameOID.STATE_OR_PROVINCE_NAME)
            if attrs:
                uf = str(attrs[0].value or "").strip().upper()
                if uf in UF_CODES:
                    return uf

            # Fallback em alguns certificados que gravam UF apenas no DN textual.
            dn = cert.subject.rfc4514_string().upper()
            match = re.search(r"(?:^|,)(?:ST|S)=([A-Z]{2})(?:,|$)", dn)
            if match:
                uf = match.group(1).strip().upper()
                if uf in UF_CODES:
                    return uf
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao extrair UF a partir do certificado digital")
        return None

    def _obter_ou_criar_sync(self, db, empresa_id: str) -> Dict[str, Any]:
        resp = db.table("sync_empresas").select("*").eq("empresa_id", empresa_id).limit(1).execute()
        if resp.data:
            return resp.data[0]
        db.table("sync_empresas").insert({"empresa_id": empresa_id}).execute()
        resp = db.table("sync_empresas").select("*").eq("empresa_id", empresa_id).limit(1).execute()
        return (resp.data or [{}])[0]

    def _contar_notas_empresa(self, db, empresa_id: str) -> int:
        try:
            resp = (
                db.table("notas_fiscais")
                .select("id", count="exact")
                .eq("empresa_id", empresa_id)
                .execute()
            )
            return int(resp.count or 0)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao contar notas da empresa_id=%s", empresa_id)
            return 0

    def _calcular_eta_segundos(self, inicio: datetime, percentual: float) -> Optional[int]:
        try:
            pct = float(percentual)
        except Exception:  # noqa: BLE001
            return None
        if pct <= 0 or pct >= 100:
            return None
        elapsed = (datetime.now(timezone.utc) - inicio).total_seconds()
        if elapsed <= 0:
            return None
        eta = int(elapsed * ((100.0 / pct) - 1.0))
        return max(1, eta)

    def _estimar_percentual_consulta(
        self,
        pagina: int,
        nsu_inicio: int,
        ult_nsu: int,
        max_nsu: int,
    ) -> float:
        base_inicio = 12.0
        base_fim = 68.0
        total_nsu = int(max_nsu or 0) - int(nsu_inicio or 0)
        proc_nsu = int(ult_nsu or 0) - int(nsu_inicio or 0)
        if total_nsu > 0:
            fator = max(0.0, min(1.0, float(proc_nsu) / float(total_nsu)))
            return round(base_inicio + (base_fim - base_inicio) * fator, 2)
        return min(base_fim, round(base_inicio + max(0, int(pagina)) * 8.0, 2))

    def _atualizar_sync_progresso(
        self,
        db,
        empresa_id: str,
        percentual: float,
        etapa: str,
        mensagem: Optional[str],
        processadas: int,
        estimadas: Optional[int],
        eta_segundos: Optional[int],
    ) -> None:
        payload: Dict[str, Any] = {
            "progresso_percentual": float(max(0.0, min(100.0, percentual))),
            "etapa_atual": str(etapa or "sincronizando")[:120],
            "mensagem_progresso": (str(mensagem)[:500] if mensagem else None),
            "notas_processadas_parcial": int(max(0, processadas or 0)),
            "notas_estimadas_total": int(max(0, estimadas or 0)) if estimadas is not None else None,
            "tempo_restante_estimado_segundos": int(max(1, eta_segundos)) if eta_segundos else None,
        }
        try:
            db.table("sync_empresas").update(payload).eq("empresa_id", empresa_id).execute()
        except Exception:  # noqa: BLE001
            # Migração pode ainda não ter sido aplicada no banco do cliente.
            logger.debug("Colunas de progresso indisponiveis em sync_empresas (empresa_id=%s)", empresa_id)

    def _finalizar_sync_progresso(
        self,
        db,
        empresa_id: str,
        status: str,
        mensagem: Optional[str],
        processadas: int = 0,
    ) -> None:
        terminal = status in {"ok", "erro", "sem_certificado"}
        etapa = "concluido" if status == "ok" else ("aguardando_retry" if status == "pendente" else "falha")
        payload = {
            "status": status,
            "progresso_percentual": 100.0 if terminal else 0.0,
            "etapa_atual": etapa,
            "mensagem_progresso": mensagem,
            "notas_processadas_parcial": int(max(0, processadas or 0)),
            "notas_estimadas_total": int(max(0, processadas or 0)),
            "tempo_restante_estimado_segundos": 0 if terminal else None,
        }
        try:
            db.table("sync_empresas").update(payload).eq("empresa_id", empresa_id).execute()
        except Exception:  # noqa: BLE001
            logger.debug("Finalizacao de progresso indisponivel (empresa_id=%s)", empresa_id)

    def _atualizar_sync_ok(
        self,
        db,
        empresa_id: str,
        sync_state: Dict[str, Any],
        ultimo_nsu: int,
        max_nsu: int,
        notas_processadas: int,
        notas_novas: int,
        mensagem: Optional[str] = None,
    ) -> None:
        total_atual = int((sync_state or {}).get("total_notas_capturadas") or 0)
        db.table("sync_empresas").update(
            {
                "ultimo_nsu": int(ultimo_nsu),
                "max_nsu": int(max_nsu),
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
                "status": "ok",
                "notas_capturadas_ultima_sync": int(notas_processadas),
                "total_notas_capturadas": total_atual + int(notas_novas),
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": 0,
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status="ok",
            mensagem=mensagem or "Captura concluida com sucesso.",
            processadas=notas_processadas,
        )

    def _atualizar_sync_cooldown(
        self,
        db,
        empresa_id: str,
        ultimo_nsu: int,
        max_nsu: int,
        horas: int = 1,
        sync_state: Optional[Dict[str, Any]] = None,
        notas_processadas: int = 0,
        notas_novas: int = 0,
        mensagem: Optional[str] = None,
    ) -> None:
        total_atual = int((sync_state or {}).get("total_notas_capturadas") or 0)
        db.table("sync_empresas").update(
            {
                "ultimo_nsu": int(ultimo_nsu),
                "max_nsu": int(max_nsu),
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=horas)).isoformat(),
                "status": "ok",
                "notas_capturadas_ultima_sync": int(notas_processadas),
                "total_notas_capturadas": total_atual + int(notas_novas),
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": 0,
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status="ok",
            mensagem=mensagem or "Captura concluida. Novo ciclo em cooldown.",
            processadas=notas_processadas,
        )

    def _atualizar_sync_alerta_config(
        self,
        db,
        empresa_id: str,
        ultimo_nsu: int,
        max_nsu: int,
        mensagem: str,
        notas_processadas: int = 0,
        notas_novas: int = 0,
        horas: int = 1,
    ) -> None:
        atual = (
            db.table("sync_empresas")
            .select("total_notas_capturadas")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        total_atual = int((atual.data or [{}])[0].get("total_notas_capturadas") or 0)
        db.table("sync_empresas").update(
            {
                "ultimo_nsu": int(ultimo_nsu or 0),
                "max_nsu": int(max_nsu or 0),
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=horas)).isoformat(),
                "status": "erro",
                "notas_capturadas_ultima_sync": int(notas_processadas),
                "total_notas_capturadas": total_atual + int(notas_novas),
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": 0,
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status="erro",
            mensagem=mensagem,
            processadas=notas_processadas,
        )

    def _marcar_sem_certificado(self, db, empresa_id: str, mensagem: str) -> None:
        db.table("sync_empresas").update(
            {
                "status": "sem_certificado",
                "erro_mensagem": mensagem,
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status="sem_certificado",
            mensagem=mensagem,
            processadas=0,
        )

    def _atualizar_sync_erro_rede(self, db, empresa_id: str, mensagem: str, sync_state: Dict[str, Any]) -> str:
        tentativas = int((sync_state or {}).get("tentativas_consecutivas_erro") or 0) + 1
        status = "erro" if tentativas >= 5 else "pendente"
        db.table("sync_empresas").update(
            {
                "status": status,
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": tentativas,
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status=status,
            mensagem=mensagem,
            processadas=0,
        )
        return status

    def _atualizar_sync_erro_generico(self, db, empresa_id: str, mensagem: str, sync_state: Dict[str, Any]) -> str:
        tentativas = int((sync_state or {}).get("tentativas_consecutivas_erro") or 0) + 1
        status = "erro" if tentativas >= 5 else "pendente"
        db.table("sync_empresas").update(
            {
                "status": status,
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": tentativas,
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status=status,
            mensagem=mensagem,
            processadas=0,
        )
        return status

    def _atualizar_sync_erro_sefaz(
        self,
        db,
        empresa_id: str,
        mensagem: str,
        sync_state: Dict[str, Any],
        ultimo_nsu: int,
        max_nsu: int,
    ) -> str:
        tentativas = int((sync_state or {}).get("tentativas_consecutivas_erro") or 0) + 1
        db.table("sync_empresas").update(
            {
                "status": "erro",
                "erro_mensagem": mensagem,
                "tentativas_consecutivas_erro": tentativas,
                "ultimo_nsu": int(ultimo_nsu or 0),
                "max_nsu": int(max_nsu or 0),
                "ultima_sync": datetime.now(timezone.utc).isoformat(),
                "proximo_sync": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
            }
        ).eq("empresa_id", empresa_id).execute()
        self._finalizar_sync_progresso(
            db=db,
            empresa_id=empresa_id,
            status="erro",
            mensagem=mensagem,
            processadas=0,
        )
        return "erro"

    def _registrar_sync_log(
        self,
        db,
        empresa_id: str,
        iniciado_em: datetime,
        finalizado_em: datetime,
        status: str,
        notas_novas: int,
        notas_atualizadas: int,
        nsu_inicio: int,
        nsu_fim: int,
        erro_detalhes: Optional[str],
        duracao_ms: int,
    ) -> None:
        try:
            db.table("sync_log").insert(
                {
                    "empresa_id": empresa_id,
                    "iniciado_em": iniciado_em.isoformat(),
                    "finalizado_em": finalizado_em.isoformat(),
                    "status": status,
                    "notas_novas": notas_novas,
                    "notas_atualizadas": notas_atualizadas,
                    "nsu_inicio": nsu_inicio,
                    "nsu_fim": nsu_fim,
                    "erro_detalhes": erro_detalhes,
                    "duracao_ms": duracao_ms,
                }
            ).execute()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao registrar sync_log para empresa_id=%s", empresa_id)

    def _get_certificado_service(self):
        from app.services.certificado_service import certificado_service
        return certificado_service

    def _is_mock_enabled(self) -> bool:
        return os.getenv("USE_MOCK_SEFAZ", "false").lower() == "true"

    def _limpar_notas_mock_antigas(self, db, empresa_id: str) -> None:
        try:
            candidatos = (
                db.table("notas_fiscais")
                .select("id, chave_acesso, cnpj_emitente, nome_emitente, fonte, nsu, xml_completo")
                .eq("empresa_id", empresa_id)
                .execute()
            ).data or []

            ids_remover: List[str] = []
            for row in candidatos:
                chave = str(row.get("chave_acesso") or "")
                cnpj_emit = str(row.get("cnpj_emitente") or "")
                nome_emit = str(row.get("nome_emitente") or "").upper()
                fonte = str(row.get("fonte") or "").lower()
                nsu = row.get("nsu")
                xml = row.get("xml_completo")

                assinatura_mock = (
                    chave in MOCK_CHAVES_ACESSO
                    or (
                        fonte == "manual"
                        and (not nsu)
                        and (not xml)
                        and cnpj_emit == "12.345.678/0001-90"
                        and "HOMOLOGACAO" in nome_emit
                    )
                )
                if assinatura_mock and row.get("id"):
                    ids_remover.append(str(row["id"]))

            if not ids_remover:
                return

            db.table("notas_fiscais").delete().in_("id", ids_remover).execute()
            logger.info(
                "Limpeza de notas mock concluida para empresa_id=%s: %s registros removidos",
                empresa_id,
                len(ids_remover),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao limpar notas mock antigas para empresa_id=%s", empresa_id)

    def _resetar_cursor_nfse_token_bootstrap(self, db, empresa_id: str) -> None:
        """
        Reseta o token tecnico AUTO_CERT_A1 para disparar bootstrap de notas recentes.
        Isso evita ciclos longos presos em backlog antigo.
        """
        try:
            credenciais = (
                db.table("credenciais_nfse")
                .select("id, token, usuario")
                .eq("empresa_id", empresa_id)
                .eq("ativo", True)
                .execute()
            ).data or []

            if not credenciais:
                return

            for cred in credenciais:
                token = str(cred.get("token") or "").strip()
                usuario = str(cred.get("usuario") or "").strip().upper()
                if not (token.upper().startswith("AUTO_CERT_A1") or usuario == "AUTO_CERT_A1"):
                    continue

                cred_id = cred.get("id")
                if not cred_id or token == "AUTO_CERT_A1|NSU:0":
                    continue

                db.table("credenciais_nfse").update({"token": "AUTO_CERT_A1|NSU:0"}).eq("id", cred_id).execute()
                logger.info(
                    "Cursor tecnico NFS-e resetado para bootstrap recente (empresa_id=%s, credencial_id=%s)",
                    empresa_id,
                    cred_id,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao resetar cursor tecnico NFS-e da empresa_id=%s", empresa_id)

    def _find_text(self, element, tag: str) -> Optional[str]:
        found = element.xpath(f".//*[local-name()='{tag}']")
        if not found:
            return None
        value = found[0].text
        return value.strip() if value else None

    def _extrair_texto_do_xml(self, xml_doc: str, tag: str) -> Optional[str]:
        if etree is None:
            return None
        try:
            root = etree.fromstring(xml_doc.encode("utf-8"))
            found = root.xpath(f".//*[local-name()='{tag}']")
            if not found:
                return None
            value = found[0].text
            return value.strip() if value else None
        except Exception:  # noqa: BLE001
            return None

    def _extrair_primeiro_texto_do_xml(self, xml_doc: str, tags: List[str]) -> Optional[str]:
        for tag in tags:
            valor = self._extrair_texto_do_xml(xml_doc, tag)
            if valor:
                return valor
        return None

    def _extrair_chave_acesso(self, xml_doc: str) -> Optional[str]:
        chave = self._extrair_texto_do_xml(xml_doc, "chNFe")
        if chave and len(chave) == 44 and chave.isdigit():
            return chave
        if etree is None:
            return self._extrair_chave_por_regex(xml_doc or "")
        try:
            root = etree.fromstring(xml_doc.encode("utf-8"))
            inf_nfe = root.xpath(".//*[local-name()='infNFe']")
            if not inf_nfe:
                id_attr = root.xpath(".//@Id")
                for ident in id_attr:
                    ident = str(ident or "")
                    if ident.startswith("NFe") and len(ident) >= 47:
                        chave = ident[3:47]
                        if len(chave) == 44 and chave.isdigit():
                            return chave
                    match_evento = re.search(r"ID\d{6}(\d{44})\d{2}", ident)
                    if match_evento:
                        return match_evento.group(1)
            else:
                ident = inf_nfe[0].attrib.get("Id", "")
                if ident.startswith("NFe"):
                    chave = ident[3:]
                    if len(chave) == 44 and chave.isdigit():
                        return chave
        except Exception:  # noqa: BLE001
            pass

        return self._extrair_chave_por_regex(xml_doc or "")

    def _extrair_chave_por_regex(self, conteudo: str) -> Optional[str]:
        if not conteudo:
            return None
        candidatos = re.findall(r"(\d{44})", conteudo)
        for candidato in candidatos:
            if len(candidato) == 44 and candidato.isdigit():
                modelo = candidato[20:22]
                if modelo in {"55", "57", "65", "67"}:
                    return candidato
        return candidatos[0] if candidatos else None

    def _normalizar_resposta_xml(self, resposta: Any) -> str:
        if isinstance(resposta, bytes):
            return resposta.decode("utf-8", errors="ignore")
        if isinstance(resposta, str):
            return resposta
        if hasattr(resposta, "text"):
            return str(resposta.text)
        if hasattr(resposta, "content"):
            content = resposta.content
            return content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)
        return str(resposta)

    def _parse_int(self, valor: Optional[str]) -> Optional[int]:
        try:
            return int(str(valor).strip()) if valor is not None else None
        except ValueError:
            return None

    def _normalizar_data(self, valor: Optional[str]) -> str:
        if not valor:
            return datetime.now(timezone.utc).isoformat()
        if "T" in valor:
            return valor
        return f"{valor}T00:00:00"

    def _normalizar_decimal(self, valor: Optional[str]) -> float:
        if not valor:
            return 0.0
        try:
            txt = str(valor).strip()
            if "," in txt and "." in txt:
                txt = txt.replace(".", "").replace(",", ".")
            else:
                txt = txt.replace(",", ".")
            return float(Decimal(txt))
        except (InvalidOperation, ValueError):
            return 0.0

    def _normalizar_cnpj(self, valor: Optional[str]) -> Optional[str]:
        if not valor:
            return None
        digits = "".join(ch for ch in str(valor) if ch.isdigit())
        return digits if len(digits) == 14 else None

    def _formatar_cnpj(self, valor: Optional[str]) -> Optional[str]:
        cnpj = self._normalizar_cnpj(valor)
        if not cnpj:
            return valor
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    def _mapear_tipo_nf(self, modelo: Optional[str]) -> str:
        mapa = {"55": "NFe", "65": "NFCe", "57": "CTe"}
        return mapa.get(str(modelo or ""), "NFe")

    def _mapear_situacao(self, codigo: Optional[str]) -> str:
        mapa = {
            "1": "autorizada",
            "2": "denegada",
            "3": "cancelada",
            "4": "autorizada",
            "100": "autorizada",
            "101": "cancelada",
            "110": "cancelada",
            "111": "cancelada",
            "128": "autorizada",
            "135": "autorizada",
            "150": "autorizada",
            "151": "cancelada",
            "302": "denegada",
            "303": "denegada",
            "110110": "cancelada",
            "110111": "cancelada",
            "110112": "cancelada",
        }
        return mapa.get((codigo or "").strip(), "processando")

    def _certificado_expirado_por_data(self, validade: Optional[str]) -> bool:
        if not validade:
            return False
        try:
            return date.fromisoformat(str(validade)[:10]) < date.today()
        except Exception:  # noqa: BLE001
            return False

    def _certificado_expirado_por_pfx(self, cert_bytes: bytes, senha: str) -> bool:
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12

            senha_bytes = senha.encode("utf-8") if senha else None
            _, cert, _ = pkcs12.load_key_and_certificates(cert_bytes, senha_bytes)
            if cert is None:
                return True
            validade = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
            if validade.tzinfo is None:
                validade = validade.replace(tzinfo=timezone.utc)
            return validade < datetime.now(timezone.utc)
        except Exception:  # noqa: BLE001
            return True

    def _resultado(
        self,
        status: str,
        notas_novas: int,
        notas_atualizadas: int,
        ultimo_nsu: int,
        max_nsu: int,
        erro_mensagem: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "notas_novas": int(notas_novas),
            "notas_atualizadas": int(notas_atualizadas),
            "ultimo_nsu": int(ultimo_nsu or 0),
            "max_nsu": int(max_nsu or 0),
            "erro_mensagem": erro_mensagem,
        }


captura_service = CapturaService()
