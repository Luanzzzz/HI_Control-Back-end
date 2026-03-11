"""
Serviço de contingência para emissão de NF-e quando SEFAZ está indisponível.

Modos suportados:
- EPEC (Evento Prévio de Emissão em Contingência): registra evento no AN
- SVC-AN (SEFAZ Virtual de Contingência - Ambiente Nacional)
- SVC-RS (SEFAZ Virtual de Contingência - RS)

Fluxo:
1. Detectar indisponibilidade do SEFAZ (timeout, erro 5xx)
2. Registrar EPEC no Ambiente Nacional
3. Emitir NF-e em contingência com tpEmis alterado
4. Background job para reprocessar quando SEFAZ voltar
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ContingenciaMode:
    """Enumeração dos modos de contingência."""
    NORMAL = "1"
    EPEC = "4"
    SVC_AN = "6"
    SVC_RS = "7"


# URLs dos serviços de contingência
CONTINGENCIA_URLS = {
    "SVC_AN": {
        "autorizacao": "https://www.svc.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno": "https://www.svc.fazenda.gov.br/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
    },
    "SVC_RS": {
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao4/NFeAutorizacao4.asmx",
        "retorno": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao4/NFeRetAutorizacao4.asmx",
    },
    "EPEC": {
        "recepcao": "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
    },
}

# UFs que usam SVC-AN (demais usam SVC-RS)
UFS_SVC_AN = {"AM", "BA", "CE", "GO", "MA", "MS", "MT", "PA", "PE", "PI", "PR"}


class ContingenciaService:
    """Serviço para gerenciamento de contingência NF-e."""

    _instance = None
    _modo_atual: str = ContingenciaMode.NORMAL
    _ativado_em: Optional[datetime] = None
    _motivo: str = ""
    _falhas_consecutivas: int = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def em_contingencia(self) -> bool:
        return self._modo_atual != ContingenciaMode.NORMAL

    @property
    def modo_atual(self) -> str:
        return self._modo_atual

    def obter_status(self) -> Dict[str, Any]:
        """Retorna status atual do modo de contingência."""
        return {
            "em_contingencia": self.em_contingencia,
            "modo": self._modo_atual,
            "modo_nome": self._nome_modo(self._modo_atual),
            "ativado_em": self._ativado_em.isoformat() if self._ativado_em else None,
            "motivo": self._motivo,
            "falhas_consecutivas": self._falhas_consecutivas,
        }

    def _nome_modo(self, modo: str) -> str:
        nomes = {
            "1": "Normal",
            "4": "EPEC - Evento Prévio de Emissão em Contingência",
            "6": "SVC-AN - SEFAZ Virtual de Contingência - Ambiente Nacional",
            "7": "SVC-RS - SEFAZ Virtual de Contingência - Rio Grande do Sul",
        }
        return nomes.get(modo, "Desconhecido")

    # ============================================
    # DETECÇÃO DE FALHAS
    # ============================================

    def registrar_falha(self, erro: str):
        """
        Registra falha na comunicação com SEFAZ.
        Após 3 falhas consecutivas, ativa contingência automaticamente.
        """
        self._falhas_consecutivas += 1
        logger.warning(
            f"Falha SEFAZ #{self._falhas_consecutivas}: {erro}"
        )

        if self._falhas_consecutivas >= 3 and not self.em_contingencia:
            self.ativar_contingencia(
                modo=ContingenciaMode.SVC_AN,
                motivo=f"SEFAZ indisponível após {self._falhas_consecutivas} tentativas: {erro}",
            )

    def registrar_sucesso(self):
        """Registra sucesso na comunicação - reseta contador de falhas."""
        if self._falhas_consecutivas > 0:
            logger.info(
                f"SEFAZ respondeu com sucesso após {self._falhas_consecutivas} falhas"
            )
        self._falhas_consecutivas = 0

        # Se estava em contingência, verificar se pode voltar ao normal
        if self.em_contingencia:
            logger.info("SEFAZ voltou. Desativando contingência...")
            self.desativar_contingencia()

    # ============================================
    # ATIVAÇÃO/DESATIVAÇÃO
    # ============================================

    def ativar_contingencia(
        self,
        modo: str = ContingenciaMode.SVC_AN,
        motivo: str = "SEFAZ indisponível",
    ):
        """Ativa modo de contingência."""
        self._modo_atual = modo
        self._ativado_em = datetime.now(timezone.utc)
        self._motivo = motivo

        logger.warning(
            f"CONTINGÊNCIA ATIVADA: {self._nome_modo(modo)} - {motivo}"
        )

    def desativar_contingencia(self):
        """Desativa modo de contingência e volta ao normal."""
        modo_anterior = self._modo_atual
        self._modo_atual = ContingenciaMode.NORMAL
        self._motivo = ""
        self._falhas_consecutivas = 0

        logger.info(
            f"CONTINGÊNCIA DESATIVADA. Modo anterior: {self._nome_modo(modo_anterior)}"
        )

    # ============================================
    # DETERMINAÇÃO DO MODO
    # ============================================

    def obter_modo_contingencia(self, uf: str) -> str:
        """
        Determina o melhor modo de contingência para a UF.

        Args:
            uf: Sigla da UF (ex: 'SP')

        Returns:
            Modo de contingência a usar
        """
        if uf.upper() in UFS_SVC_AN:
            return ContingenciaMode.SVC_AN
        return ContingenciaMode.SVC_RS

    def obter_urls_contingencia(self, uf: str) -> Dict[str, str]:
        """Retorna URLs do web service de contingência para a UF."""
        if uf.upper() in UFS_SVC_AN:
            return CONTINGENCIA_URLS["SVC_AN"]
        return CONTINGENCIA_URLS["SVC_RS"]

    # ============================================
    # EPEC (Evento Prévio)
    # ============================================

    async def registrar_epec(
        self,
        chave_acesso: str,
        cnpj_emitente: str,
        uf_emitente: str,
        ie_emitente: str,
        cnpj_destinatario: str,
        uf_destinatario: str,
        valor_total: float,
        valor_icms: float,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> Dict[str, Any]:
        """
        Registra Evento Prévio de Emissão em Contingência (EPEC).

        O EPEC notifica o Ambiente Nacional que uma NF-e será emitida
        em contingência e deve ser transmitida em até 168h (7 dias).

        Args:
            chave_acesso: Chave de acesso da NF-e
            cnpj_emitente: CNPJ do emitente
            uf_emitente: UF do emitente
            ie_emitente: IE do emitente
            cnpj_destinatario: CNPJ do destinatário
            uf_destinatario: UF do destinatário
            valor_total: Valor total da NF-e
            valor_icms: Valor do ICMS
            cert_bytes: Certificado digital
            senha_cert: Senha do certificado

        Returns:
            Resultado do registro EPEC
        """
        import httpx
        from lxml import etree

        # Construir XML do evento EPEC
        xml_epec = self._construir_xml_epec(
            chave_acesso=chave_acesso,
            cnpj_emitente=cnpj_emitente,
            uf_emitente=uf_emitente,
            ie_emitente=ie_emitente,
            cnpj_destinatario=cnpj_destinatario,
            uf_destinatario=uf_destinatario,
            valor_total=valor_total,
            valor_icms=valor_icms,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    CONTINGENCIA_URLS["EPEC"]["recepcao"],
                    content=xml_epec,
                    headers={"Content-Type": "text/xml; charset=utf-8"},
                )

                if response.status_code == 200:
                    return {
                        "sucesso": True,
                        "mensagem": "EPEC registrado com sucesso",
                        "protocolo": "",  # Extrair do XML de resposta
                    }
                else:
                    return {
                        "sucesso": False,
                        "mensagem": f"Erro ao registrar EPEC: HTTP {response.status_code}",
                    }

        except Exception as e:
            logger.error(f"Erro ao registrar EPEC: {e}")
            return {
                "sucesso": False,
                "mensagem": f"Erro: {str(e)}",
            }

    def _construir_xml_epec(self, **kwargs) -> str:
        """Constrói XML do evento EPEC."""
        from datetime import datetime

        data_evento = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-03:00")
        seq = "1"

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
            <idLote>1</idLote>
            <evento versao="1.00">
                <infEvento Id="ID110140{kwargs['chave_acesso']}{seq.zfill(2)}">
                    <cOrgao>91</cOrgao>
                    <tpAmb>1</tpAmb>
                    <CNPJ>{kwargs['cnpj_emitente']}</CNPJ>
                    <chNFe>{kwargs['chave_acesso']}</chNFe>
                    <dhEvento>{data_evento}</dhEvento>
                    <tpEvento>110140</tpEvento>
                    <nSeqEvento>{seq}</nSeqEvento>
                    <verEvento>1.00</verEvento>
                    <detEvento versao="1.00">
                        <descEvento>EPEC</descEvento>
                        <cOrgaoAutor>91</cOrgaoAutor>
                        <tpAutor>1</tpAutor>
                        <verAplic>HI-CONTROL1.0</verAplic>
                        <dhEmi>{data_evento}</dhEmi>
                        <tpNF>1</tpNF>
                        <IE>{kwargs['ie_emitente']}</IE>
                        <dest>
                            <UF>{kwargs['uf_destinatario']}</UF>
                            <CNPJ>{kwargs['cnpj_destinatario']}</CNPJ>
                            <vNF>{kwargs['valor_total']:.2f}</vNF>
                            <vICMS>{kwargs['valor_icms']:.2f}</vICMS>
                            <vST>0.00</vST>
                        </dest>
                    </detEvento>
                </infEvento>
            </evento>
        </envEvento>"""

        return xml

    # ============================================
    # REPROCESSAMENTO
    # ============================================

    async def reprocessar_contingencia(self, empresa_id: str):
        """
        Reprocessa NF-e emitidas em contingência.

        Busca notas com situação 'contingencia' e tenta autorizar normalmente.
        Deve ser chamado por background job quando SEFAZ voltar.
        """
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()

        try:
            result = (
                db.table("notas_fiscais")
                .select("*")
                .eq("empresa_id", empresa_id)
                .eq("situacao", "contingencia")
                .execute()
            )

            if not result.data:
                logger.info("Nenhuma NF-e em contingência para reprocessar")
                return

            logger.info(
                f"Reprocessando {len(result.data)} NF-e em contingência"
            )

            for nota in result.data:
                try:
                    # Tentar autorizar normalmente
                    # O sefaz_service deve ser chamado com o XML original
                    logger.info(
                        f"Reprocessando NF-e {nota.get('numero_nf')} "
                        f"(chave: {nota.get('chave_acesso')})"
                    )

                    # Atualizar status para 'reprocessando'
                    db.table("notas_fiscais").update({
                        "situacao": "processando",
                    }).eq("id", nota["id"]).execute()

                    # TODO: Reenviar XML ao SEFAZ e atualizar status

                except Exception as e:
                    logger.error(
                        f"Erro ao reprocessar NF-e {nota.get('numero_nf')}: {e}"
                    )

        except Exception as e:
            logger.error(f"Erro no reprocessamento de contingência: {e}")


# Singleton
contingencia_service = ContingenciaService()
