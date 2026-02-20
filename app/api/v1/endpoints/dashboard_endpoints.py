"""
Endpoint agregado de dashboard por empresa.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.dependencies import get_admin_db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/empresas", tags=["Dashboard"])

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


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


def _normalizar_tipo_nf_saida(value: Optional[str]) -> Optional[str]:
    tipo = str(value or "")
    if tipo == "NFSE":
        return "NFSe"
    return value


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
        buckets[chave] = {"prestados": 0.0, "tomados": 0.0}
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
        else:
            buckets[chave]["tomados"] += valor

    historico = []
    for chave, valores in buckets.items():
        ano_i, mes_i = chave.split("-")
        periodo = f"{MESES[int(mes_i)-1]}. {str(ano_i)[2:]}"
        historico.append(
            {
                "periodo": periodo,
                "prestados": round(valores["prestados"], 2),
                "tomados": round(valores["tomados"], 2),
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
            "situacao, municipio_nome, fonte"
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
    }


@router.get("/{empresa_id}/notas")
async def listar_notas_empresa(
    empresa_id: str,
    tipo: Optional[str] = Query(default="Todos"),
    status_filtro: Optional[str] = Query(default="Todos", alias="status"),
    retencao: Optional[str] = Query(default="Todas"),
    busca: Optional[str] = Query(default=""),
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

    colunas = (
        "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, data_emissao, "
        "valor_total, cnpj_emitente, nome_emitente, cnpj_destinatario, nome_destinatario, "
        "situacao, municipio_nome, fonte, valor_iss, valor_pis, valor_cofins"
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
