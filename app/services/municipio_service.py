"""
Serviço para resolver código IBGE de município a partir de cidade + UF.

Fonte de dados: IBGE API
https://servicodados.ibge.gov.br/api/v1/localidades/estados/{UF}/municipios
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Dict, Optional, Tuple, List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_municipios_cache: Dict[str, List[Dict]] = {}


def _normalizar_nome(nome: str) -> str:
    """Normaliza nome para comparação (sem acentos, lower, sem pontuação)."""
    if not nome:
        return ""
    nome = unicodedata.normalize("NFD", nome)
    nome = "".join(ch for ch in nome if unicodedata.category(ch) != "Mn")
    nome = nome.lower()
    for ch in [".", ",", "-", "'", "\"", "(", ")", "/"]:
        nome = nome.replace(ch, " ")
    nome = " ".join(nome.split())
    return nome


async def _carregar_municipios_uf(uf: str) -> List[Dict]:
    """Carrega e cacheia a lista de municípios do IBGE para a UF."""
    uf = (uf or "").upper()
    if not uf:
        return []

    if uf in _municipios_cache:
        return _municipios_cache[uf]

    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    timeout = float(settings.NFSE_TIMEOUT) if hasattr(settings, "NFSE_TIMEOUT") else 60.0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            _municipios_cache[uf] = data or []
            return _municipios_cache[uf]
    except Exception as e:
        logger.warning(f"[IBGE] Falha ao carregar municípios para UF {uf}: {e}")
        return []


async def resolver_municipio_por_cidade_uf(
    cidade: str,
    uf: str,
) -> Optional[Tuple[str, str]]:
    """
    Resolve código IBGE e nome do município a partir de cidade + UF.

    Returns:
        Tuple (codigo_ibge, nome_municipio) ou None se não encontrado.
    """
    if not cidade or not uf:
        return None

    municipios = await _carregar_municipios_uf(uf)
    if not municipios:
        return None

    alvo = _normalizar_nome(cidade)
    if not alvo:
        return None

    for municipio in municipios:
        nome = municipio.get("nome", "")
        if _normalizar_nome(nome) == alvo:
            codigo = str(municipio.get("id", ""))
            if codigo:
                return codigo, nome

    # Fallback: tentativa de contains (casos com bairros ou sufixos)
    for municipio in municipios:
        nome = municipio.get("nome", "")
        if alvo in _normalizar_nome(nome) or _normalizar_nome(nome) in alvo:
            codigo = str(municipio.get("id", ""))
            if codigo:
                return codigo, nome

    return None


async def resolver_municipio_por_codigo(
    codigo_ibge: str,
) -> Optional[Tuple[str, str]]:
    """
    Resolve nome do município a partir do código IBGE.

    Returns:
        Tuple (codigo_ibge, nome_municipio) ou None se não encontrado.
    """
    if not codigo_ibge:
        return None

    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo_ibge}"
    timeout = float(settings.NFSE_TIMEOUT) if hasattr(settings, "NFSE_TIMEOUT") else 60.0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                nome = data.get("nome")
                codigo = str(data.get("id", codigo_ibge))
                if nome:
                    return codigo, nome
    except Exception as e:
        logger.warning(f"[IBGE] Falha ao resolver município {codigo_ibge}: {e}")

    return None
