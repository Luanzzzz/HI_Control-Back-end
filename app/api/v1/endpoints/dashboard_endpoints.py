"""
Endpoint agregado de dashboard por empresa.
"""
from __future__ import annotations

import io
import ipaddress
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from supabase import Client

from app.dependencies import get_admin_db, get_current_user
from app.services.danfe_service import danfe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/empresas", tags=["Dashboard"])

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _prioridade_recente_habilitada() -> bool:
    valor = os.getenv("NFSE_ADN_PRIORIZAR_RECENTES", "true").strip().lower()
    return valor not in {"0", "false", "no", "off"}


def _obter_estado_prioridade_recente(db: Client, empresa_id: str) -> Dict[str, bool]:
    if not _prioridade_recente_habilitada():
        return {
            "prioridade_recente_ativa": False,
            "prioridade_recente_concluida": False,
        }

    try:
        resp = (
            db.table("credenciais_nfse")
            .select("token, usuario, ativo")
            .eq("empresa_id", empresa_id)
            .eq("ativo", True)
            .limit(20)
            .execute()
        )
        credenciais = resp.data or []
        if not credenciais:
            return {
                "prioridade_recente_ativa": False,
                "prioridade_recente_concluida": False,
            }

        auto = None
        for cred in credenciais:
            token = str(cred.get("token") or "").strip()
            usuario = str(cred.get("usuario") or "").strip().upper()
            if token.upper().startswith("AUTO_CERT_A1") or usuario == "AUTO_CERT_A1":
                auto = cred
                break

        if not auto:
            return {
                "prioridade_recente_ativa": False,
                "prioridade_recente_concluida": False,
            }

        token_upper = str(auto.get("token") or "").strip().upper()
        concluida = "HOTDONE:1" in token_upper
        ativa = not concluida
        return {
            "prioridade_recente_ativa": ativa,
            "prioridade_recente_concluida": concluida,
        }
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao obter estado da prioridade recente da empresa_id=%s", empresa_id)
        return {
            "prioridade_recente_ativa": False,
            "prioridade_recente_concluida": False,
        }


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _inicio_fim_mes(ano: int, mes: int) -> Tuple[datetime, datetime]:
    inicio = datetime(ano, mes, 1, tzinfo=timezone.utc)
    if mes == 12:
        fim = datetime(ano + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fim = datetime(ano, mes + 1, 1, tzinfo=timezone.utc)
    return inicio, fim


def _subtrair_mes(ano: int, mes: int) -> Tuple[int, int]:
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1


def _normalizar_tipo_param(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalizado = value.strip().lower().replace("-", "").replace(" ", "")
    if normalizado in {"todos", "todas", "all"}:
        return None
    if normalizado in {"nfe", "55"}:
        return "NFe"
    if normalizado in {"nfse"}:
        return "NFSe"
    if normalizado in {"nfce", "65"}:
        return "NFCe"
    if normalizado in {"cte", "57"}:
        return "CTe"
    return None


def _safe_filename_fragment(value: Any, fallback: str = "nota") -> str:
    texto = str(value or "").strip()
    if not texto:
        return fallback
    permitido = "".join(ch for ch in texto if ch.isalnum() or ch in {"-", "_", "."})
    return permitido[:120] or fallback


def _normalizar_tipo_nf_saida(value: Optional[str]) -> Optional[str]:
    tipo = str(value or "")
    if tipo == "NFSE":
        return "NFSe"
    return value


def _normalizar_tipo_nf_interno(value: Optional[str]) -> str:
    tipo = str(value or "").strip().upper()
    if tipo in {"NFSE", "NFE", "NFCE", "CTE"}:
        return tipo
    if tipo == "NFSE":
        return "NFSE"
    if str(value or "") == "NFSe":
        return "NFSE"
    if str(value or "") == "NFe":
        return "NFE"
    if str(value or "") == "NFCe":
        return "NFCE"
    if str(value or "") == "CTe":
        return "CTE"
    return tipo


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _parece_pdf(content_type: Optional[str], content: bytes) -> bool:
    ctype = str(content_type or "").lower()
    if "application/pdf" in ctype:
        return True
    return content.startswith(b"%PDF-")


def _url_aceita_para_download_oficial(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        pass

    return True


def _extrair_candidatos_pdf_do_html(html: str, base_url: str) -> List[str]:
    candidatos: List[str] = []
    padroes = [
        r'href=["\']([^"\']+)["\']',
        r'src=["\']([^"\']+)["\']',
        r'window\.open\(["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
    ]

    for padrao in padroes:
        for match in re.finditer(padrao, html, flags=re.IGNORECASE):
            valor = (match.group(1) or "").strip()
            if not valor:
                continue
            valor_low = valor.lower()
            termos_relevantes = (
                ".pdf",
                "pdf",
                "danfse",
                "imprimir",
                "consulta",
                "visualiz",
                "download",
                "nfse",
                "nota",
            )
            if not any(termo in valor_low for termo in termos_relevantes):
                # Em alguns portais o link real vem sem nome de PDF, mas com query tokenizada.
                # Mantemos caminhos com querystring para nova tentativa.
                if "?" not in valor_low:
                    continue
            candidatos.append(urljoin(base_url, valor))

    vistos = set()
    unicos: List[str] = []
    for item in candidatos:
        if item in vistos:
            continue
        vistos.add(item)
        unicos.append(item)
    return unicos


async def _download_url(url: str, timeout_sec: float = 20.0) -> Tuple[bytes, str]:
    if not _url_aceita_para_download_oficial(url):
        raise ValueError("URL de PDF oficial invalida ou bloqueada por seguranca.")

    headers = {
        "User-Agent": "Hi-Control/1.0 (+https://hi-control.vercel.app)",
        "Accept": "application/pdf, text/html, application/xhtml+xml, */*",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_sec) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content, str(resp.headers.get("content-type") or "")


async def _obter_pdf_oficial_nota(nota: Dict[str, Any]) -> Optional[bytes]:
    candidatos = [
        str(nota.get("pdf_url") or "").strip(),
        str(nota.get("link_visualizacao") or "").strip(),
    ]

    xml_content = str(nota.get("xml_completo") or nota.get("xml_resumo") or "").strip()
    if xml_content:
        for encontrado in re.findall(r'https?://[^"\'>\s]+', xml_content, flags=re.IGNORECASE):
            candidatos.append(encontrado.strip())

    template_link = str(os.getenv("NFSE_LINK_VISUALIZACAO_TEMPLATE", "") or "").strip()
    if template_link:
        try:
            url_tpl = template_link.format(
                chave=str(nota.get("chave_acesso") or ""),
                codigo_verificacao=str(nota.get("codigo_verificacao") or ""),
                numero=str(nota.get("numero_nf") or ""),
                cnpj_prestador=str(nota.get("cnpj_emitente") or ""),
            ).strip()
            if url_tpl:
                candidatos.append(url_tpl)
        except Exception:  # noqa: BLE001
            logger.debug("Template NFSE_LINK_VISUALIZACAO_TEMPLATE invalido.", exc_info=True)

    candidatos_limpos: List[str] = []
    vistos = set()
    for url in candidatos:
        if not url:
            continue
        if url in vistos:
            continue
        vistos.add(url)
        candidatos_limpos.append(url)

    for url in candidatos_limpos:
        try:
            conteudo, content_type = await _download_url(url)
            if _parece_pdf(content_type, conteudo):
                logger.info("PDF oficial obtido diretamente para nota_id=%s url=%s", nota.get("id"), url)
                return conteudo

            if "html" in content_type.lower():
                html = conteudo.decode("utf-8", errors="ignore")
                for candidato_pdf in _extrair_candidatos_pdf_do_html(html, url):
                    try:
                        conteudo_pdf, content_type_pdf = await _download_url(candidato_pdf)
                        if _parece_pdf(content_type_pdf, conteudo_pdf):
                            logger.info(
                                "PDF oficial obtido via pagina de visualizacao para nota_id=%s url=%s",
                                nota.get("id"),
                                candidato_pdf,
                            )
                            return conteudo_pdf
                    except Exception:  # noqa: BLE001
                        logger.debug(
                            "Candidato PDF invalido na pagina de visualizacao da nota_id=%s: %s",
                            nota.get("id"),
                            candidato_pdf,
                        )
                        continue
        except Exception:  # noqa: BLE001
            logger.debug("Falha ao tentar baixar PDF oficial da nota_id=%s URL=%s", nota.get("id"), url, exc_info=True)
            continue

    return None


def _gerar_pdf_resumo_nota(nota: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margem = 15 * mm
    y = height - margem

    c.setFont("Helvetica-Bold", 14)
    c.drawString(margem, y, "HI-CONTROL - Resumo da Nota Fiscal")
    y -= 8 * mm

    c.setStrokeColor(colors.lightgrey)
    c.line(margem, y, width - margem, y)
    y -= 8 * mm

    campos = [
        ("Tipo", _normalizar_tipo_nf_saida(nota.get("tipo_nf")) or "-"),
        ("Numero", str(nota.get("numero_nf") or "-")),
        ("Serie", str(nota.get("serie") or "-")),
        ("Data Emissao", str(nota.get("data_emissao") or "-")),
        ("Valor Total", str(nota.get("valor_total") or "0")),
        ("Situacao", str(nota.get("situacao") or "-")),
        ("Chave de Acesso", str(nota.get("chave_acesso") or "-")),
        ("Emitente", str(nota.get("nome_emitente") or "-")),
        ("CNPJ Emitente", str(nota.get("cnpj_emitente") or "-")),
        ("Destinatario", str(nota.get("nome_destinatario") or "-")),
        ("CNPJ Destinatario", str(nota.get("cnpj_destinatario") or "-")),
        ("Municipio", str(nota.get("municipio_nome") or "-")),
        ("Link Visualizacao", str(nota.get("link_visualizacao") or "-")),
    ]

    c.setFont("Helvetica", 10)
    for label, valor in campos:
        if y < (margem + 20 * mm):
            c.showPage()
            y = height - margem
            c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#1f2937"))
        c.drawString(margem, y, f"{label}:")
        c.setFillColor(colors.black)
        texto = str(valor)
        max_len = 95
        partes = [texto[i:i + max_len] for i in range(0, len(texto), max_len)] or ["-"]
        c.drawString(margem + 35 * mm, y, partes[0])
        y -= 6 * mm
        for parte in partes[1:]:
            c.drawString(margem + 35 * mm, y, parte)
            y -= 5 * mm

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawString(margem, margem - 2 * mm, "Documento auxiliar gerado automaticamente pelo Hi-Control.")
    c.save()
    return buffer.getvalue()


def _gerar_pdf_nota(nota: Dict[str, Any]) -> bytes:
    tipo = _normalizar_tipo_nf_interno(nota.get("tipo_nf"))
    xml_content = str(nota.get("xml_completo") or nota.get("xml_resumo") or "").strip()

    if xml_content and tipo in {"NFE", "NFCE", "CTE"}:
        try:
            if tipo == "NFE":
                return danfe_service.gerar_danfe(xml_content)
            if tipo == "NFCE":
                return danfe_service.gerar_danfce(xml_content)
            if tipo == "CTE":
                return danfe_service.gerar_dacte(xml_content)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao gerar PDF oficial da nota id=%s, usando fallback.", nota.get("id"))

    return _gerar_pdf_resumo_nota(nota)


def _normalizar_status_param(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalizado = value.strip().lower()
    if normalizado in {"todos", "todas", "all"}:
        return None
    if normalizado in {"ativa", "autorizada"}:
        return "autorizada"
    if normalizado in {"cancelada"}:
        return "cancelada"
    if normalizado in {"denegada"}:
        return "denegada"
    if normalizado in {"processando"}:
        return "processando"
    return None


def _normalizar_retencao_param(value: Optional[str]) -> str:
    if not value:
        return "todas"
    normalizado = value.strip().lower().replace("ã", "a").replace("ç", "c")
    if "com" in normalizado and "retenc" in normalizado:
        return "com"
    if "sem" in normalizado and "retenc" in normalizado:
        return "sem"
    return "todas"


def _tem_retencao(row: Dict[str, Any]) -> bool:
    valores = [row.get("valor_iss"), row.get("valor_pis"), row.get("valor_cofins")]
    for valor in valores:
        if _to_decimal(valor) > 0:
            return True
    return False


def _filtrar_por_retencao(rows: List[Dict[str, Any]], retencao: str) -> List[Dict[str, Any]]:
    if retencao == "com":
        return [row for row in rows if _tem_retencao(row)]
    if retencao == "sem":
        return [row for row in rows if not _tem_retencao(row)]
    return rows


async def _validar_empresa_usuario(db: Client, empresa_id: str, usuario_id: str) -> Dict[str, Any]:
    resp = (
        db.table("empresas")
        .select("id, razao_social, cnpj, ativa, usuario_id")
        .eq("id", empresa_id)
        .eq("usuario_id", usuario_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa nao encontrada ou sem permissao de acesso",
        )
    return resp.data[0]


@router.get("/{empresa_id}/dashboard")
async def get_dashboard_empresa(
    empresa_id: str,
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    ano: Optional[int] = Query(default=None, ge=2000, le=2100),
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    empresa = await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    hoje = date.today()
    mes = mes or hoje.month
    ano = ano or hoje.year

    inicio_mes, fim_mes = _inicio_fim_mes(ano, mes)
    prev_ano, prev_mes = _subtrair_mes(ano, mes)
    inicio_prev, fim_prev = _inicio_fim_mes(prev_ano, prev_mes)

    # Sync status
    sync_resp = db.table("sync_empresas").select("*").eq("empresa_id", empresa_id).limit(1).execute()
    sync_row = sync_resp.data[0] if sync_resp.data else {}
    estado_prioridade = _obter_estado_prioridade_recente(db, empresa_id)

    # Resumo do mes
    resumo_rows = (
        db.table("notas_fiscais")
        .select("tipo_operacao, situacao, valor_total, valor_iss, valor_pis, valor_cofins")
        .eq("empresa_id", empresa_id)
        .gte("data_emissao", inicio_mes.isoformat())
        .lt("data_emissao", fim_mes.isoformat())
        .execute()
    ).data or []

    prestados_valor = Decimal("0")
    tomados_valor = Decimal("0")
    prestados_qtd = 0
    tomados_qtd = 0
    iss_retido = Decimal("0")
    federais_retidos = Decimal("0")

    for row in resumo_rows:
        if row.get("situacao") != "autorizada":
            continue

        valor = _to_decimal(row.get("valor_total"))
        if row.get("tipo_operacao") == "saida":
            prestados_valor += valor
            prestados_qtd += 1
        else:
            tomados_valor += valor
            tomados_qtd += 1

        iss_retido += _to_decimal(row.get("valor_iss"))
        federais_retidos += _to_decimal(row.get("valor_pis")) + _to_decimal(row.get("valor_cofins"))

    # Mes anterior para variacao percentual
    prev_rows = (
        db.table("notas_fiscais")
        .select("tipo_operacao, situacao, valor_total")
        .eq("empresa_id", empresa_id)
        .gte("data_emissao", inicio_prev.isoformat())
        .lt("data_emissao", fim_prev.isoformat())
        .execute()
    ).data or []
    total_prev = sum(
        float(_to_decimal(r.get("valor_total")))
        for r in prev_rows
        if r.get("situacao") == "autorizada"
    )
    total_mes = float(prestados_valor + tomados_valor)
    variacao_percent = ((total_mes - total_prev) / total_prev * 100) if total_prev > 0 else None

    # Historico 12 meses (ate o mes solicitado)
    hist_start_ano, hist_start_mes = ano, mes
    for _ in range(11):
        hist_start_ano, hist_start_mes = _subtrair_mes(hist_start_ano, hist_start_mes)
    hist_inicio, _ = _inicio_fim_mes(hist_start_ano, hist_start_mes)
    _, hist_fim = _inicio_fim_mes(ano, mes)

    hist_rows = (
        db.table("notas_fiscais")
        .select("data_emissao, tipo_operacao, situacao, valor_total")
        .eq("empresa_id", empresa_id)
        .gte("data_emissao", hist_inicio.isoformat())
        .lt("data_emissao", hist_fim.isoformat())
        .execute()
    ).data or []

    buckets: Dict[str, Dict[str, float]] = {}
    cy, cm = hist_start_ano, hist_start_mes
    for _ in range(12):
        chave = f"{cy:04d}-{cm:02d}"
        buckets[chave] = {
            "prestados": 0.0,
            "tomados": 0.0,
            "prestados_quantidade": 0.0,
            "tomados_quantidade": 0.0,
        }
        if cm == 12:
            cy, cm = cy + 1, 1
        else:
            cm += 1

    for row in hist_rows:
        if row.get("situacao") != "autorizada":
            continue
        data_str = str(row.get("data_emissao") or "")
        if len(data_str) < 7:
            continue
        chave = data_str[:7]
        if chave not in buckets:
            continue
        valor = float(_to_decimal(row.get("valor_total")))
        if row.get("tipo_operacao") == "saida":
            buckets[chave]["prestados"] += valor
            buckets[chave]["prestados_quantidade"] += 1
        else:
            buckets[chave]["tomados"] += valor
            buckets[chave]["tomados_quantidade"] += 1

    historico = []
    for chave, valores in buckets.items():
        ano_i, mes_i = chave.split("-")
        periodo = f"{MESES[int(mes_i)-1]}. {str(ano_i)[2:]}"
        historico.append(
            {
                "periodo": periodo,
                "prestados": round(valores["prestados"], 2),
                "tomados": round(valores["tomados"], 2),
                "prestados_quantidade": int(valores["prestados_quantidade"]),
                "tomados_quantidade": int(valores["tomados_quantidade"]),
            }
        )

    # Notas do mes (paginadas)
    offset = (pagina - 1) * limite
    total_resp = (
        db.table("notas_fiscais")
        .select("id", count="exact")
        .eq("empresa_id", empresa_id)
        .gte("data_emissao", inicio_mes.isoformat())
        .lt("data_emissao", fim_mes.isoformat())
        .execute()
    )
    notas_resp = (
        db.table("notas_fiscais")
        .select(
            "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, data_emissao, "
            "valor_total, cnpj_emitente, nome_emitente, cnpj_destinatario, nome_destinatario, "
            "situacao, municipio_nome, fonte, link_visualizacao"
        )
        .eq("empresa_id", empresa_id)
        .gte("data_emissao", inicio_mes.isoformat())
        .lt("data_emissao", fim_mes.isoformat())
        .order("data_emissao", desc=True)
        .range(offset, offset + limite - 1)
        .execute()
    )
    notas_data = notas_resp.data or []
    for nota in notas_data:
        nota["tipo_nf"] = _normalizar_tipo_nf_saida(nota.get("tipo_nf"))

    estimadas = sync_row.get("notas_estimadas_total")
    processadas = sync_row.get("notas_processadas_parcial")
    try:
        estimadas_int = int(estimadas) if estimadas is not None else None
    except Exception:  # noqa: BLE001
        estimadas_int = None
    try:
        processadas_int = int(processadas) if processadas is not None else 0
    except Exception:  # noqa: BLE001
        processadas_int = 0
    restantes_int = None
    if estimadas_int is not None:
        restantes_int = max(0, estimadas_int - processadas_int)

    return {
        "empresa": {
            "id": empresa["id"],
            "razao_social": empresa.get("razao_social"),
            "cnpj": empresa.get("cnpj"),
            "ativa": empresa.get("ativa", False),
        },
        "sync": {
            "empresa_id": empresa_id,
            "status": sync_row.get("status", "pendente"),
            "ultima_sync": sync_row.get("ultima_sync"),
            "proximo_sync": sync_row.get("proximo_sync"),
            "total_notas_capturadas": sync_row.get("total_notas_capturadas", 0),
            "notas_capturadas_ultima_sync": sync_row.get("notas_capturadas_ultima_sync", 0),
            "erro_mensagem": sync_row.get("erro_mensagem"),
            "ultimo_nsu": sync_row.get("ultimo_nsu", 0),
            "inicio_sync_at": sync_row.get("inicio_sync_at"),
            "etapa_atual": sync_row.get("etapa_atual"),
            "mensagem_progresso": sync_row.get("mensagem_progresso"),
            "progresso_percentual": float(sync_row.get("progresso_percentual") or 0),
            "notas_processadas_parcial": processadas_int,
            "notas_estimadas_total": estimadas_int,
            "notas_restantes_estimadas": restantes_int,
            "tempo_restante_estimado_segundos": sync_row.get("tempo_restante_estimado_segundos"),
            "prioridade_recente_ativa": estado_prioridade["prioridade_recente_ativa"],
            "prioridade_recente_concluida": estado_prioridade["prioridade_recente_concluida"],
        },
        "resumo": {
            "prestados_valor": float(prestados_valor),
            "prestados_quantidade": prestados_qtd,
            "tomados_valor": float(tomados_valor),
            "tomados_quantidade": tomados_qtd,
            "iss_retido": float(iss_retido),
            "federais_retidos": float(federais_retidos),
            "total_retido": float(iss_retido + federais_retidos),
            "fora_competencia": 0.0,
            "diferenca": float(prestados_valor - tomados_valor),
            "variacao_mes_anterior_percent": round(variacao_percent, 2) if variacao_percent is not None else None,
        },
        "historico": historico,
        "notas": notas_data,
        "notas_total": total_resp.count or 0,
        "pagina": pagina,
        "limite": limite,
        "periodo_referencia_mes": mes,
        "periodo_referencia_ano": ano,
    }


@router.get("/{empresa_id}/notas")
async def listar_notas_empresa(
    empresa_id: str,
    tipo: Optional[str] = Query(default="Todos"),
    status_filtro: Optional[str] = Query(default="Todos", alias="status"),
    retencao: Optional[str] = Query(default="Todas"),
    busca: Optional[str] = Query(default=""),
    data_inicio: Optional[date] = Query(default=None),
    data_fim: Optional[date] = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    limite: int = Query(default=20, ge=1, le=100),
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    tipo_nf = _normalizar_tipo_param(tipo)
    situacao = _normalizar_status_param(status_filtro)
    retencao_norm = _normalizar_retencao_param(retencao)
    termo_busca = (busca or "").strip().replace(",", " ").replace("%", "").replace("*", "")

    if data_inicio and data_fim and data_fim < data_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_fim deve ser maior ou igual a data_inicio",
        )

    inicio_iso = None
    fim_iso_exclusivo = None
    if data_inicio:
        inicio_iso = datetime.combine(data_inicio, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    if data_fim:
        fim_iso_exclusivo = datetime.combine(
            data_fim + timedelta(days=1),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).isoformat()

    colunas = (
        "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, data_emissao, "
        "valor_total, cnpj_emitente, nome_emitente, cnpj_destinatario, nome_destinatario, "
        "situacao, municipio_nome, fonte, link_visualizacao, valor_iss, valor_pis, valor_cofins"
    )
    offset = (pagina - 1) * limite

    def _base_query():
        query = (
            db.table("notas_fiscais")
            .select(colunas, count="exact")
            .eq("empresa_id", empresa_id)
            .order("data_emissao", desc=True)
        )
        if tipo_nf:
            if tipo_nf == "NFSe":
                query = query.in_("tipo_nf", ["NFSe", "NFSE"])
            else:
                query = query.eq("tipo_nf", tipo_nf)
        if situacao:
            query = query.eq("situacao", situacao)
        if inicio_iso:
            query = query.gte("data_emissao", inicio_iso)
        if fim_iso_exclusivo:
            query = query.lt("data_emissao", fim_iso_exclusivo)
        if termo_busca:
            query = query.or_(
                "chave_acesso.ilike.%{0}%,"
                "numero_nf.ilike.%{0}%,"
                "cnpj_emitente.ilike.%{0}%,"
                "nome_emitente.ilike.%{0}%,"
                "cnpj_destinatario.ilike.%{0}%,"
                "nome_destinatario.ilike.%{0}%".format(termo_busca)
            )
        return query

    if retencao_norm == "todas":
        resp = _base_query().range(offset, offset + limite - 1).execute()
        notas = resp.data or []
        for nota in notas:
            nota["tipo_nf"] = _normalizar_tipo_nf_saida(nota.get("tipo_nf"))
            nota.pop("valor_iss", None)
            nota.pop("valor_pis", None)
            nota.pop("valor_cofins", None)
        return {
            "notas": notas,
            "total": resp.count or 0,
            "pagina": pagina,
            "limite": limite,
        }

    # Quando filtra por retencao, aplica filtro em memoria para evitar inconsistencias
    # entre valores nulos/zero nas colunas de retencao.
    resp = _base_query().execute()
    linhas = resp.data or []
    filtradas = _filtrar_por_retencao(linhas, retencao_norm)
    total = len(filtradas)
    notas = filtradas[offset: offset + limite]
    for nota in notas:
        nota["tipo_nf"] = _normalizar_tipo_nf_saida(nota.get("tipo_nf"))
        nota.pop("valor_iss", None)
        nota.pop("valor_pis", None)
        nota.pop("valor_cofins", None)

    return {
        "notas": notas,
        "total": total,
        "pagina": pagina,
        "limite": limite,
    }


@router.get("/{empresa_id}/notas/{nota_id}")
async def obter_nota_empresa(
    empresa_id: str,
    nota_id: str,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    resp = (
        db.table("notas_fiscais")
        .select(
            "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, data_emissao, "
            "valor_total, cnpj_emitente, nome_emitente, cnpj_destinatario, nome_destinatario, "
            "situacao, municipio_nome, fonte, link_visualizacao, protocolo"
        )
        .eq("empresa_id", empresa_id)
        .eq("id", nota_id)
        .limit(1)
        .execute()
    )
    nota = (resp.data or [None])[0]
    if not nota:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota nao encontrada para esta empresa",
        )

    nota["tipo_nf"] = _normalizar_tipo_nf_saida(nota.get("tipo_nf"))
    return {"nota": nota}


@router.get("/{empresa_id}/notas/{nota_id}/xml")
async def baixar_xml_nota_empresa(
    empresa_id: str,
    nota_id: str,
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    resp = (
        db.table("notas_fiscais")
        .select("id, chave_acesso, numero_nf, tipo_nf, xml_completo, xml_resumo")
        .eq("empresa_id", empresa_id)
        .eq("id", nota_id)
        .limit(1)
        .execute()
    )
    nota = (resp.data or [None])[0]
    if not nota:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota nao encontrada para esta empresa",
        )

    xml_content = str(nota.get("xml_completo") or nota.get("xml_resumo") or "").strip()
    if not xml_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="XML nao disponivel para esta nota",
        )

    tipo_nf = str(_normalizar_tipo_nf_saida(nota.get("tipo_nf")) or "NF")
    identificador = _safe_filename_fragment(
        nota.get("chave_acesso") or nota.get("numero_nf") or nota.get("id"),
        fallback="nota",
    )
    filename = f"{tipo_nf}_{identificador}.xml"

    return StreamingResponse(
        io.BytesIO(xml_content.encode("utf-8")),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{empresa_id}/notas/{nota_id}/pdf")
async def baixar_pdf_nota_empresa(
    empresa_id: str,
    nota_id: str,
    download: bool = Query(default=False),
    permitir_fallback: bool = Query(default=False, alias="fallback"),
    usuario: Dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    await _validar_empresa_usuario(db, empresa_id, usuario["id"])

    resp = (
        db.table("notas_fiscais")
        .select(
            "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, data_emissao, valor_total, "
            "cnpj_emitente, nome_emitente, cnpj_destinatario, nome_destinatario, situacao, municipio_nome, "
            "xml_completo, xml_resumo, link_visualizacao, pdf_url, codigo_verificacao"
        )
        .eq("empresa_id", empresa_id)
        .eq("id", nota_id)
        .limit(1)
        .execute()
    )
    nota = (resp.data or [None])[0]
    if not nota:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota nao encontrada para esta empresa",
        )

    tipo_nf_interno = _normalizar_tipo_nf_interno(nota.get("tipo_nf"))
    pdf_bytes = await _obter_pdf_oficial_nota(nota)
    source = "official"

    fallback_nfse_habilitado = _bool_from_env("NFSE_PERMITIR_PDF_FALLBACK", False)
    pode_fallback = permitir_fallback or tipo_nf_interno in {"NFE", "NFCE", "CTE"} or fallback_nfse_habilitado

    if not pdf_bytes:
        if tipo_nf_interno == "NFSE" and not pode_fallback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "PDF oficial da NFS-e indisponivel para esta nota. "
                    "Use o link oficial de visualizacao ou habilite fallback explicitamente."
                ),
            )
        pdf_bytes = _gerar_pdf_nota(nota)
        source = "generated"

    tipo_nf = str(_normalizar_tipo_nf_saida(nota.get("tipo_nf")) or "NF")
    identificador = _safe_filename_fragment(
        nota.get("chave_acesso") or nota.get("numero_nf") or nota.get("id"),
        fallback="nota",
    )
    filename = f"{tipo_nf}_{identificador}.pdf"
    disposition = "attachment" if download else "inline"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-HiControl-Pdf-Source": source,
        },
    )
