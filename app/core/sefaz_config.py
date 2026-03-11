"""
Configuração de endpoints SEFAZ para todos os 27 estados brasileiros.
Suporta ambientes de HOMOLOGAÇÃO e PRODUÇÃO.

Referências:
- Manual de Integração Contribuinte v7.0
- Portal Nacional da NF-e: https://www.nfe.fazenda.gov.br/
- NT 2014.002 - DistribuicaoDFe (Ambiente Nacional)
"""
import os
from typing import Dict, Literal

# ============================================
# CONFIGURAÇÕES GERAIS
# ============================================

# Ambiente padrão: controlado por variável de ambiente SEFAZ_AMBIENTE
# Valores válidos: "producao" ou "homologacao"
AMBIENTE_PADRAO: str = os.getenv("SEFAZ_AMBIENTE", "producao")

# Timeouts e retry
TIMEOUT_SEFAZ = 30  # segundos (validado como adequado na auditoria)
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2  # multiplicador para backoff exponencial

# Cache em memória (decisão do usuário: sem Redis)
CACHE_TTL_SECONDS = 300  # 5 minutos
_query_cache: Dict = {}  # Formato: {chave_acesso: (response, timestamp)}

# ============================================
# CÓDIGOS UF (IBGE)
# ============================================

UF_CODES = {
    "AC": "12",  # Acre
    "AL": "27",  # Alagoas
    "AM": "13",  # Amazonas
    "AP": "16",  # Amapá
    "BA": "29",  # Bahia
    "CE": "23",  # Ceará
    "DF": "53",  # Distrito Federal
    "ES": "32",  # Espírito Santo
    "GO": "52",  # Goiás
    "MA": "21",  # Maranhão
    "MG": "31",  # Minas Gerais
    "MS": "50",  # Mato Grosso do Sul
    "MT": "51",  # Mato Grosso
    "PA": "15",  # Pará
    "PB": "25",  # Paraíba
    "PE": "26",  # Pernambuco
    "PI": "22",  # Piauí
    "PR": "41",  # Paraná
    "RJ": "33",  # Rio de Janeiro
    "RN": "24",  # Rio Grande do Norte
    "RO": "11",  # Rondônia
    "RR": "14",  # Roraima
    "RS": "43",  # Rio Grande do Sul
    "SC": "42",  # Santa Catarina
    "SE": "28",  # Sergipe
    "SP": "35",  # São Paulo
    "TO": "17",  # Tocantins
}

# ============================================
# ENDPOINTS SEFAZ HOMOLOGAÇÃO - NF-e 4.0
# ============================================

# NOTA: Alguns estados utilizam SVRS (Sefaz Virtual RS)
# SVRS atende: AC, AL, AP, DF, MS, PB, RJ, RO, RR, SC, SE, TO

SEFAZ_ENDPOINTS_HOMOLOGACAO: Dict[str, Dict[str, str]] = {
    # Acre - Usa SVRS
    "AC": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Alagoas - Usa SVRS
    "AL": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Amazonas - Sefaz próprio
    "AM": {
        "autorizacao": "https://homnfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4",
        "retorno_autorizacao": "https://homnfe.sefaz.am.gov.br/services2/services/NfeRetAutorizacao4",
        "consulta": "https://homnfe.sefaz.am.gov.br/services2/services/NfeConsulta4",
        "status_servico": "https://homnfe.sefaz.am.gov.br/services2/services/NfeStatusServico4",
        "cancelamento": "https://homnfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4",
        "inutilizacao": "https://homnfe.sefaz.am.gov.br/services2/services/NfeInutilizacao4",
    },

    # Amapá - Usa SVRS
    "AP": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Bahia - Sefaz próprio
    "BA": {
        "autorizacao": "https://hnfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hnfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://hnfe.sefaz.ba.gov.br/webservices/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://hnfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://hnfe.sefaz.ba.gov.br/webservices/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hnfe.sefaz.ba.gov.br/webservices/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },

    # Ceará - Sefaz próprio
    "CE": {
        "autorizacao": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeRetAutorizacao4",
        "consulta": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeConsulta4",
        "status_servico": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeStatusServico4",
        "cancelamento": "https://nfeh.sefaz.ce.gov.br/nfe4/services/RecepcaoEvento4",
        "inutilizacao": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeInutilizacao4",
    },

    # Distrito Federal - Usa SVRS
    "DF": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Espírito Santo - Usa SVRS
    "ES": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Goiás - Sefaz próprio
    "GO": {
        "autorizacao": "https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://homolog.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4",
        "consulta": "https://homolog.sefaz.go.gov.br/nfe/services/NFeConsulta4",
        "status_servico": "https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
        "cancelamento": "https://homolog.sefaz.go.gov.br/nfe/services/RecepcaoEvento4",
        "inutilizacao": "https://homolog.sefaz.go.gov.br/nfe/services/NFeInutilizacao4",
    },

    # Maranhão - Usa SVAN (Sefaz Virtual Ambiente Nacional)
    "MA": {
        "autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://hom.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://hom.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },

    # Minas Gerais - Sefaz próprio
    "MG": {
        "autorizacao": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        "consulta": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsulta4",
        "status_servico": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
        "cancelamento": "https://hnfe.fazenda.mg.gov.br/nfe2/services/RecepcaoEvento4",
        "inutilizacao": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4",
    },

    # Mato Grosso do Sul - Sefaz próprio
    "MS": {
        "autorizacao": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4",
        "retorno_autorizacao": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeRetAutorizacao4",
        "consulta": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeConsulta4",
        "status_servico": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeStatusServico4",
        "cancelamento": "https://hom.nfe.sefaz.ms.gov.br/ws/RecepcaoEvento4",
        "inutilizacao": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeInutilizacao4",
    },

    # Mato Grosso - Sefaz próprio
    "MT": {
        "autorizacao": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4",
        "retorno_autorizacao": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeRetAutorizacao4",
        "consulta": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4",
        "status_servico": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeStatusServico4",
        "cancelamento": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4",
        "inutilizacao": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeInutilizacao4",
    },

    # Pará - Usa SVAN
    "PA": {
        "autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://hom.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://hom.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },

    # Paraíba - Usa SVRS
    "PB": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Pernambuco - Sefaz próprio
    "PE": {
        "autorizacao": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4",
        "consulta": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeConsulta4",
        "status_servico": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4",
        "cancelamento": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/RecepcaoEvento4",
        "inutilizacao": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeInutilizacao4",
    },

    # Piauí - Usa SVAN
    "PI": {
        "autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://hom.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://hom.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },

    # Paraná - Sefaz próprio
    "PR": {
        "autorizacao": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4",
        "retorno_autorizacao": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4",
        "consulta": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeConsulta4",
        "status_servico": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeStatusServico4",
        "cancelamento": "https://homologacao.nfe.sefa.pr.gov.br/nfe/RecepcaoEvento4",
        "inutilizacao": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeInutilizacao4",
    },

    # Rio de Janeiro - Usa SVRS
    "RJ": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Rio Grande do Norte - Usa SVRS
    "RN": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Rondônia - Usa SVRS
    "RO": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Roraima - Usa SVRS
    "RR": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Rio Grande do Sul - Sefaz próprio (SVRS hospeda outros estados)
    "RS": {
        "autorizacao": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Santa Catarina - Usa SVRS
    "SC": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # Sergipe - Usa SVRS
    "SE": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },

    # São Paulo - Sefaz próprio
    "SP": {
        "autorizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        "retorno_autorizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        "consulta": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsulta4.asmx",
        "status_servico": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        "cancelamento": "https://homologacao.nfe.fazenda.sp.gov.br/ws/recepcaoevento4.asmx",
        "inutilizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx",
    },

    # Tocantins - Usa SVRS
    "TO": {
        "autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://hom.nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://hom.nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://hom.nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://hom.nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
}

# ============================================
# ENDPOINTS NFeDistribuicaoDFe - AMBIENTE NACIONAL (AN)
# ============================================
# DistribuicaoDFe é um serviço CENTRALIZADO do Ambiente Nacional.
# Não depende da UF - existe uma unica URL por ambiente.
# REQUER certificado digital A1 (contrario ao que muitos acreditam).
# Referência: NT 2014.002

DISTRIBUICAO_DFE_ENDPOINTS = {
    "homologacao": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "producao": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}

# ============================================
# ENDPOINTS SEFAZ PRODUÇÃO - NF-e 4.0
# ============================================

SEFAZ_ENDPOINTS_PRODUCAO: Dict[str, Dict[str, str]] = {
    # Acre - Usa SVRS
    "AC": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Alagoas - Usa SVRS
    "AL": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Amazonas - Sefaz proprio
    "AM": {
        "autorizacao": "https://nfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.am.gov.br/services2/services/NfeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.am.gov.br/services2/services/NfeConsulta4",
        "status_servico": "https://nfe.sefaz.am.gov.br/services2/services/NfeStatusServico4",
        "cancelamento": "https://nfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.am.gov.br/services2/services/NfeInutilizacao4",
    },
    # Amapa - Usa SVRS
    "AP": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Bahia - Sefaz proprio
    "BA": {
        "autorizacao": "https://nfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.sefaz.ba.gov.br/webservices/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://nfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://nfe.sefaz.ba.gov.br/webservices/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.sefaz.ba.gov.br/webservices/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },
    # Ceara - Sefaz proprio
    "CE": {
        "autorizacao": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeConsulta4",
        "status_servico": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeStatusServico4",
        "cancelamento": "https://nfe.sefaz.ce.gov.br/nfe4/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeInutilizacao4",
    },
    # Distrito Federal - Usa SVRS
    "DF": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Espirito Santo - Usa SVRS
    "ES": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Goias - Sefaz proprio
    "GO": {
        "autorizacao": "https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.go.gov.br/nfe/services/NFeConsulta4",
        "status_servico": "https://nfe.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
        "cancelamento": "https://nfe.sefaz.go.gov.br/nfe/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.go.gov.br/nfe/services/NFeInutilizacao4",
    },
    # Maranhao - Usa SVAN
    "MA": {
        "autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://www.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://www.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://www.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },
    # Minas Gerais - Sefaz proprio
    "MG": {
        "autorizacao": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        "consulta": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeConsulta4",
        "status_servico": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
        "cancelamento": "https://nfe.fazenda.mg.gov.br/nfe2/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4",
    },
    # Mato Grosso do Sul - Sefaz proprio
    "MS": {
        "autorizacao": "https://nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.ms.gov.br/ws/NFeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.ms.gov.br/ws/NFeConsulta4",
        "status_servico": "https://nfe.sefaz.ms.gov.br/ws/NFeStatusServico4",
        "cancelamento": "https://nfe.sefaz.ms.gov.br/ws/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.ms.gov.br/ws/NFeInutilizacao4",
    },
    # Mato Grosso - Sefaz proprio
    "MT": {
        "autorizacao": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4",
        "status_servico": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeStatusServico4",
        "cancelamento": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeInutilizacao4",
    },
    # Para - Usa SVAN
    "PA": {
        "autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://www.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://www.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://www.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },
    # Paraiba - Usa SVRS
    "PB": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Pernambuco - Sefaz proprio
    "PE": {
        "autorizacao": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4",
        "consulta": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeConsulta4",
        "status_servico": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4",
        "cancelamento": "https://nfe.sefaz.pe.gov.br/nfe-service/services/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeInutilizacao4",
    },
    # Piaui - Usa SVAN
    "PI": {
        "autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        "consulta": "https://www.sefazvirtual.fazenda.gov.br/NFeConsulta4/NFeConsulta4.asmx",
        "status_servico": "https://www.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx",
        "cancelamento": "https://www.sefazvirtual.fazenda.gov.br/RecepcaoEvento4/RecepcaoEvento4.asmx",
        "inutilizacao": "https://www.sefazvirtual.fazenda.gov.br/NFeInutilizacao4/NFeInutilizacao4.asmx",
    },
    # Parana - Sefaz proprio
    "PR": {
        "autorizacao": "https://nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4",
        "retorno_autorizacao": "https://nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4",
        "consulta": "https://nfe.sefa.pr.gov.br/nfe/NFeConsulta4",
        "status_servico": "https://nfe.sefa.pr.gov.br/nfe/NFeStatusServico4",
        "cancelamento": "https://nfe.sefa.pr.gov.br/nfe/RecepcaoEvento4",
        "inutilizacao": "https://nfe.sefa.pr.gov.br/nfe/NFeInutilizacao4",
    },
    # Rio de Janeiro - Usa SVRS
    "RJ": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Rio Grande do Norte - Usa SVRS
    "RN": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Rondonia - Usa SVRS
    "RO": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Roraima - Usa SVRS
    "RR": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Rio Grande do Sul - Sefaz proprio
    "RS": {
        "autorizacao": "https://nfe.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.sefazrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.sefazrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Santa Catarina - Usa SVRS
    "SC": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Sergipe - Usa SVRS
    "SE": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
    # Sao Paulo - Sefaz proprio
    "SP": {
        "autorizacao": "https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        "consulta": "https://nfe.fazenda.sp.gov.br/ws/nfeconsulta4.asmx",
        "status_servico": "https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        "cancelamento": "https://nfe.fazenda.sp.gov.br/ws/recepcaoevento4.asmx",
        "inutilizacao": "https://nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx",
    },
    # Tocantins - Usa SVRS
    "TO": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "retorno_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "cancelamento": "https://nfe.svrs.rs.gov.br/ws/RecepcaoEvento/RecepcaoEvento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx",
    },
}

# ============================================
# FUNÇÕES AUXILIARES
# ============================================


def obter_endpoints_por_ambiente(ambiente: str = None) -> Dict[str, Dict[str, str]]:
    """
    Retorna o dicionario de endpoints conforme o ambiente.

    Args:
        ambiente: "producao" ou "homologacao". Se None, usa AMBIENTE_PADRAO.

    Returns:
        Dict com endpoints por UF
    """
    amb = ambiente or AMBIENTE_PADRAO
    if amb == "producao":
        return SEFAZ_ENDPOINTS_PRODUCAO
    return SEFAZ_ENDPOINTS_HOMOLOGACAO


def obter_endpoint_distribuicao(ambiente: str = None) -> str:
    """
    Retorna o endpoint do servico NFeDistribuicaoDFe (Ambiente Nacional).

    Args:
        ambiente: "producao" ou "homologacao". Se None, usa AMBIENTE_PADRAO.

    Returns:
        URL do endpoint DistribuicaoDFe
    """
    amb = ambiente or AMBIENTE_PADRAO
    return DISTRIBUICAO_DFE_ENDPOINTS.get(amb, DISTRIBUICAO_DFE_ENDPOINTS["producao"])


def obter_endpoint_sefaz(uf: str, operacao: str, ambiente: str = None) -> str:
    """
    Retorna o endpoint SEFAZ para a operacao especificada.

    Para operacao "distribuicao", use obter_endpoint_distribuicao() em vez
    deste metodo, pois DistribuicaoDFe e um servico do Ambiente Nacional.

    Args:
        uf: Sigla do estado (ex: "SP", "RJ")
        operacao: Tipo de operacao ("autorizacao", "consulta", etc)
        ambiente: "producao" ou "homologacao". Se None, usa AMBIENTE_PADRAO.

    Returns:
        URL do endpoint SEFAZ

    Raises:
        ValueError: Se UF ou operacao invalida
    """
    # DistribuicaoDFe e centralizado (Ambiente Nacional), nao por UF
    if operacao == "distribuicao":
        return obter_endpoint_distribuicao(ambiente)

    endpoints_map = obter_endpoints_por_ambiente(ambiente)

    if uf not in endpoints_map:
        raise ValueError(f"UF invalida: {uf}. Deve ser uma das 27 UF brasileiras.")

    endpoints = endpoints_map[uf]

    if operacao not in endpoints:
        raise ValueError(
            f"Operacao invalida: {operacao}. "
            f"Deve ser uma de: {', '.join(endpoints.keys())}"
        )

    return endpoints[operacao]


def obter_codigo_uf(uf: str) -> str:
    """
    Retorna o código IBGE da UF.

    Args:
        uf: Sigla do estado

    Returns:
        Código IBGE (2 dígitos)

    Raises:
        ValueError: Se UF inválida
    """
    if uf not in UF_CODES:
        raise ValueError(f"UF inválida: {uf}")

    return UF_CODES[uf]


def validar_uf(uf: str) -> bool:
    """
    Valida se a UF é válida.

    Args:
        uf: Sigla do estado

    Returns:
        True se válida, False caso contrário
    """
    return uf in UF_CODES


# ============================================
# CÓDIGOS DE STATUS SEFAZ (100-999)
# ============================================

SEFAZ_STATUS_CODES = {
    # Sucesso
    "100": "Autorizado o uso da NF-e",
    "101": "Cancelamento de NF-e homologado",
    "135": "Evento registrado e vinculado a NF-e",

    # Em processamento
    "105": "Lote em processamento",
    "106": "Lote processado",

    # Rejeitados - Certificado
    "213": "CNPJ-Base do Emitente difere do CNPJ-Base do Certificado Digital",
    "214": "Tamanho da mensagem excedeu o limite estabelecido",
    "243": "Emissor não habilitado para emissão da NF-e",
    "280": "Certificado Transmissor inválido",
    "281": "Certificado Transmissor Data Validade",
    "283": "Certificado Transmissor sem CNPJ",
    "286": "Certificado Transmissor revogado",
    "284": "Certificado Transmissor erro Cadeia de Certificação",
    "285": "Certificado Transmissor revogado",

    # Rejeitados - Duplicidade
    "204": "Duplicidade de NF-e",
    "205": "NF-e está denegada na base de dados da SEFAZ",
    "206": "NF-e já está inutilizada na Base de dados da SEFAZ",

    # Rejeitados - Dados inválidos
    "215": "Falha no schema XML",
    "225": "Falha no Schema XML da NFe",
    "226": "Código da UF do Emitente diverge da UF autorizadora",
    "227": "Erro na Chave de Acesso - Campo ID",
    "228": "Data de Emissão muito atrasada",
    "229": "IE do emitente não informada",
    "230": "IE do emitente não cadastrada",
    "231": "IE do emitente não vinculada ao CNPJ",
    "232": "IE do destinatário não informada",
    "233": "IE do destinatário não cadastrada",
    "234": "IE do destinatário não vinculada ao CNPJ",
    "235": "Inscrição SUFRAMA inválida",
    "236": "Chave de Acesso com dígito verificador inválido",
    "237": "CPF do destinatário inválido",
    "238": "Cabeçalho - Versão do arquivo XML superior a aceita",
    "239": "Cabeçalho - Versão do arquivo XML não suportada",
    "240": "Cancelamento/Inutilização - Irregularidade Fiscal do Emitente",
    "241": "Um número da faixa já foi utilizado",
    "242": "Cabeçalho - Falha no Schema XML",

    # Denegados
    "301": "Uso Denegado: Irregularidade fiscal do emitente",
    "302": "Uso Denegado: Irregularidade fiscal do destinatário",
    "303": "Uso Denegado: Destinatário não habilitado a operar na UF",

    # Erros do servidor
    "505": "Lote em processamento - Aguarde",
    "545": "Autorizador não disponível - Tente mais tarde",
    "656": "Consumo Indevido",
    "999": "Erro não catalogado",
}


def obter_mensagem_sefaz(codigo: str) -> str:
    """
    Retorna a mensagem descritiva do código SEFAZ.

    Args:
        codigo: Código de status SEFAZ (ex: "100", "204")

    Returns:
        Mensagem descritiva ou código se não encontrado
    """
    return SEFAZ_STATUS_CODES.get(codigo, f"Código {codigo} não catalogado")
