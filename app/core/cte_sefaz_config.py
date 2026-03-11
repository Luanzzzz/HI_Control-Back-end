"""
Configuração de endpoints SEFAZ para CT-e (Conhecimento de Transporte Eletrônico).

O CT-e utiliza webservices distintos da NF-e.
Versão: 4.00
Referência: Manual de Integração CT-e v4.0

Cada UF é atendida por um autorizador:
- SVRS: maioria dos estados
- SVSP: SP e MS
- MG: próprio
- MT: próprio
- PR: próprio
"""
import os
from typing import Dict

# Ambiente CT-e (herda da config NF-e)
CTE_AMBIENTE = os.getenv("SEFAZ_AMBIENTE", "producao")

# ============================================
# AUTORIZADORES CT-e POR UF
# ============================================

# Mapeamento UF -> Autorizador
CTE_AUTORIZADOR = {
    "AC": "SVRS", "AL": "SVRS", "AM": "SVRS", "AP": "SVRS",
    "BA": "SVRS", "CE": "SVRS", "DF": "SVRS", "ES": "SVRS",
    "GO": "SVRS", "MA": "SVRS", "MG": "MG", "MS": "SVSP",
    "MT": "MT", "PA": "SVRS", "PB": "SVRS", "PE": "SVRS",
    "PI": "SVRS", "PR": "PR", "RJ": "SVRS", "RN": "SVRS",
    "RO": "SVRS", "RR": "SVRS", "RS": "SVRS", "SC": "SVRS",
    "SE": "SVRS", "SP": "SVSP", "TO": "SVRS",
}

# ============================================
# ENDPOINTS HOMOLOGAÇÃO CT-e 4.00
# ============================================

CTE_ENDPOINTS_HOMOLOGACAO: Dict[str, Dict[str, str]] = {
    "SVRS": {
        "autorizacao": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoSinc/CTeRecepcaoSinc.asmx",
        "retorno": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRetRecepcao/CTeRetRecepcao.asmx",
        "consulta": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeConsultaV4/CTeConsultaV4.asmx",
        "status_servico": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx",
        "evento": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoEventoV4/CTeRecepcaoEventoV4.asmx",
        "inutilizacao": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeInutilizacaoV4/CTeInutilizacaoV4.asmx",
    },
    "SVSP": {
        "autorizacao": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoSinc.asmx",
        "retorno": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRetRecepcao.asmx",
        "consulta": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeConsultaV4.asmx",
        "status_servico": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeStatusServicoV4.asmx",
        "evento": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoEventoV4.asmx",
        "inutilizacao": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeInutilizacaoV4.asmx",
    },
    "MG": {
        "autorizacao": "https://hcte.fazenda.mg.gov.br/cte/services/CTeRecepcaoSinc",
        "retorno": "https://hcte.fazenda.mg.gov.br/cte/services/CTeRetRecepcao",
        "consulta": "https://hcte.fazenda.mg.gov.br/cte/services/CTeConsultaV4",
        "status_servico": "https://hcte.fazenda.mg.gov.br/cte/services/CTeStatusServicoV4",
        "evento": "https://hcte.fazenda.mg.gov.br/cte/services/CTeRecepcaoEventoV4",
        "inutilizacao": "https://hcte.fazenda.mg.gov.br/cte/services/CTeInutilizacaoV4",
    },
    "MT": {
        "autorizacao": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeRecepcaoSinc",
        "retorno": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeRetRecepcao",
        "consulta": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeConsultaV4",
        "status_servico": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeStatusServicoV4",
        "evento": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeRecepcaoEventoV4",
        "inutilizacao": "https://homologacao.sefaz.mt.gov.br/ctews2/services/CTeInutilizacaoV4",
    },
    "PR": {
        "autorizacao": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeRecepcaoSinc",
        "retorno": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeRetRecepcao",
        "consulta": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeConsultaV4",
        "status_servico": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeStatusServicoV4",
        "evento": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeRecepcaoEventoV4",
        "inutilizacao": "https://homologacao.cte.fazenda.pr.gov.br/cte4/CTeInutilizacaoV4",
    },
}

# ============================================
# ENDPOINTS PRODUÇÃO CT-e 4.00
# ============================================

CTE_ENDPOINTS_PRODUCAO: Dict[str, Dict[str, str]] = {
    "SVRS": {
        "autorizacao": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoSinc/CTeRecepcaoSinc.asmx",
        "retorno": "https://cte.svrs.rs.gov.br/ws/CTeRetRecepcao/CTeRetRecepcao.asmx",
        "consulta": "https://cte.svrs.rs.gov.br/ws/CTeConsultaV4/CTeConsultaV4.asmx",
        "status_servico": "https://cte.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx",
        "evento": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoEventoV4/CTeRecepcaoEventoV4.asmx",
        "inutilizacao": "https://cte.svrs.rs.gov.br/ws/CTeInutilizacaoV4/CTeInutilizacaoV4.asmx",
    },
    "SVSP": {
        "autorizacao": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoSinc.asmx",
        "retorno": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRetRecepcao.asmx",
        "consulta": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeConsultaV4.asmx",
        "status_servico": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeStatusServicoV4.asmx",
        "evento": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoEventoV4.asmx",
        "inutilizacao": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeInutilizacaoV4.asmx",
    },
    "MG": {
        "autorizacao": "https://cte.fazenda.mg.gov.br/cte/services/CTeRecepcaoSinc",
        "retorno": "https://cte.fazenda.mg.gov.br/cte/services/CTeRetRecepcao",
        "consulta": "https://cte.fazenda.mg.gov.br/cte/services/CTeConsultaV4",
        "status_servico": "https://cte.fazenda.mg.gov.br/cte/services/CTeStatusServicoV4",
        "evento": "https://cte.fazenda.mg.gov.br/cte/services/CTeRecepcaoEventoV4",
        "inutilizacao": "https://cte.fazenda.mg.gov.br/cte/services/CTeInutilizacaoV4",
    },
    "MT": {
        "autorizacao": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeRecepcaoSinc",
        "retorno": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeRetRecepcao",
        "consulta": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeConsultaV4",
        "status_servico": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeStatusServicoV4",
        "evento": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeRecepcaoEventoV4",
        "inutilizacao": "https://cte.sefaz.mt.gov.br/ctews2/services/CTeInutilizacaoV4",
    },
    "PR": {
        "autorizacao": "https://cte.fazenda.pr.gov.br/cte4/CTeRecepcaoSinc",
        "retorno": "https://cte.fazenda.pr.gov.br/cte4/CTeRetRecepcao",
        "consulta": "https://cte.fazenda.pr.gov.br/cte4/CTeConsultaV4",
        "status_servico": "https://cte.fazenda.pr.gov.br/cte4/CTeStatusServicoV4",
        "evento": "https://cte.fazenda.pr.gov.br/cte4/CTeRecepcaoEventoV4",
        "inutilizacao": "https://cte.fazenda.pr.gov.br/cte4/CTeInutilizacaoV4",
    },
}


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def obter_autorizador_cte(uf: str) -> str:
    """Retorna o autorizador CT-e para a UF."""
    return CTE_AUTORIZADOR.get(uf.upper(), "SVRS")


def obter_endpoints_cte(uf: str, ambiente: str = None) -> Dict[str, str]:
    """
    Retorna endpoints do CT-e para a UF e ambiente.

    Args:
        uf: Sigla da UF
        ambiente: 'producao' ou 'homologacao'

    Returns:
        Dict com URLs dos webservices
    """
    if ambiente is None:
        ambiente = CTE_AMBIENTE

    autorizador = obter_autorizador_cte(uf)

    if ambiente == "producao":
        endpoints = CTE_ENDPOINTS_PRODUCAO.get(autorizador)
    else:
        endpoints = CTE_ENDPOINTS_HOMOLOGACAO.get(autorizador)

    if not endpoints:
        # Fallback para SVRS
        if ambiente == "producao":
            return CTE_ENDPOINTS_PRODUCAO["SVRS"]
        return CTE_ENDPOINTS_HOMOLOGACAO["SVRS"]

    return endpoints
