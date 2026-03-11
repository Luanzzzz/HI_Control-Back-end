"""
Serviço para emissão de NFC-e (Nota Fiscal de Consumidor Eletrônica - Modelo 65).

Diferenças em relação à NF-e (Modelo 55):
- Modelo 65 (vs 55)
- QR Code obrigatório
- CSC (Código de Segurança do Contribuinte) obrigatório
- Destinatário opcional (venda a consumidor)
- DANFCE formato cupom
"""
import hashlib
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class NFCeService:
    """Serviço para operações com NFC-e."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============================================
    # QR CODE
    # ============================================

    def gerar_qrcode_nfce(
        self,
        chave_acesso: str,
        ambiente: str,
        csc_id: str,
        csc_token: str,
        uf: str,
    ) -> str:
        """
        Gera URL do QR Code para NFC-e.

        O QR Code da NFC-e contém uma URL que permite ao consumidor
        consultar a nota fiscal diretamente no site da SEFAZ.

        Args:
            chave_acesso: Chave de acesso de 44 dígitos
            ambiente: '1' (produção) ou '2' (homologação)
            csc_id: ID do CSC cadastrado na SEFAZ
            csc_token: Token do CSC
            uf: Sigla da UF

        Returns:
            URL do QR Code
        """
        # URL base por UF (exemplos - cada UF tem sua URL)
        urls_qrcode = self._obter_url_qrcode(uf, ambiente)

        # Concatenar para hash: chave|2|csc_id|hash
        # Hash = sha1(chave_acesso + CSC)
        concat = f"{chave_acesso}{csc_token}"
        hash_qr = hashlib.sha1(concat.encode()).hexdigest()

        url = f"{urls_qrcode}?p={chave_acesso}|{ambiente}|{csc_id}|{hash_qr}"

        return url

    def _obter_url_qrcode(self, uf: str, ambiente: str) -> str:
        """Retorna URL base do QR Code por UF."""
        # URLs de produção (simplificado - cada UF tem suas URLs)
        urls_prod = {
            "AC": "http://www.sefaznet.ac.gov.br/nfce/qrcode",
            "AL": "http://nfce.sefaz.al.gov.br/QRCode/consultarNFCe.jsp",
            "AM": "http://sistemas.sefaz.am.gov.br/nfceweb/consultarNFCe.jsp",
            "AP": "https://www.sefaz.ap.gov.br/nfce/nfcep.php",
            "BA": "http://nfe.sefaz.ba.gov.br/servicos/nfce/modulos/geral/NFCEC_consulta_chave_acesso.aspx",
            "CE": "http://nfce.sefaz.ce.gov.br/pages/ShowNFCe.html",
            "DF": "http://dec.fazenda.df.gov.br/ConsultarNFCe.aspx",
            "ES": "http://app.sefaz.es.gov.br/ConsultaNFCe",
            "GO": "http://nfe.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
            "MA": "http://www.nfce.sefaz.ma.gov.br/portal/consultarNFCe.jsp",
            "MG": "https://nfce.fazenda.mg.gov.br/portalnfce",
            "MS": "http://www.dfe.ms.gov.br/nfce/qrcode",
            "MT": "http://www.sefaz.mt.gov.br/nfce/consultanfce",
            "PA": "https://appnfc.sefa.pa.gov.br/portal/view/consultas/nfce/nfceForm.seam",
            "PB": "http://www.receita.pb.gov.br/nfce",
            "PE": "http://nfce.sefaz.pe.gov.br/nfce/consulta",
            "PI": "http://www.sefaz.pi.gov.br/nfce/qrcode",
            "PR": "http://www.fazenda.pr.gov.br/nfce/qrcode",
            "RJ": "http://www4.fazenda.rj.gov.br/consultaNFCe/QRCode",
            "RN": "http://nfce.set.rn.gov.br/consultarNFCe.aspx",
            "RO": "http://www.nfce.sefin.ro.gov.br/consultanfce/consulta.jsp",
            "RR": "https://www.sefaz.rr.gov.br/nfce/servlet/qrcode",
            "RS": "https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx",
            "SC": "https://sat.sef.sc.gov.br/nfce/consulta",
            "SE": "http://www.nfce.se.gov.br/portal/consultarNFCe.jsp",
            "SP": "https://www.nfce.fazenda.sp.gov.br/NFCeConsultaPublica",
            "TO": "http://apps.sefaz.to.gov.br/portal-nfce/qrcodeNFCe",
        }

        urls_homolog = {uf_key: url.replace("www.", "homologacao.").replace("http://", "https://")
                        for uf_key, url in urls_prod.items()}

        if ambiente == "2":
            return urls_homolog.get(uf, urls_prod.get("SP", ""))
        return urls_prod.get(uf, urls_prod.get("SP", ""))

    # ============================================
    # AUTORIZAÇÃO
    # ============================================

    async def autorizar_nfce(
        self,
        nfce_data: dict,
        empresa: dict,
        cert_bytes: bytes,
        senha_cert: str,
    ) -> Dict[str, Any]:
        """
        Autoriza NFC-e junto à SEFAZ.

        Diferenças da NF-e:
        - Modelo 65
        - QR Code obrigatório
        - CSC obrigatório
        - Destinatário pode ser omitido

        Args:
            nfce_data: Dados da NFC-e
            empresa: Dados da empresa
            cert_bytes: Certificado A1
            senha_cert: Senha do certificado

        Returns:
            Resultado da autorização
        """
        from app.services.sefaz_service import sefaz_service

        # Validar CSC
        csc_id = empresa.get("csc_id")
        csc_token = empresa.get("csc_token")

        if not csc_id or not csc_token:
            return {
                "autorizado": False,
                "erro": "CSC (Código de Segurança do Contribuinte) não configurado. "
                        "Configure o CSC no cadastro da empresa.",
            }

        # Preparar dados com modelo 65
        nfce_data["modelo"] = "65"

        # Gerar QR Code URL (será inserido no XML)
        # A chave será gerada durante a criação do XML
        # Por ora, marcar que precisa de QR Code
        nfce_data["requer_qrcode"] = True
        nfce_data["csc_id"] = csc_id
        nfce_data["csc_token"] = csc_token

        try:
            # Usar o mesmo fluxo do sefaz_service mas com modelo 65
            response = sefaz_service.autorizar_nfe(
                nfe_data=nfce_data,
                cert_bytes=cert_bytes,
                senha_cert=senha_cert,
                empresa_cnpj=empresa["cnpj"],
                empresa_ie=empresa.get("inscricao_estadual", "ISENTO"),
                empresa_razao_social=empresa["razao_social"],
                empresa_uf=empresa["uf"],
            )

            if response.autorizado:
                # Gerar QR Code
                qr_url = self.gerar_qrcode_nfce(
                    chave_acesso=response.chave_acesso,
                    ambiente="1",  # TODO: usar config
                    csc_id=csc_id,
                    csc_token=csc_token,
                    uf=empresa["uf"],
                )

                return {
                    "autorizado": True,
                    "chave_acesso": response.chave_acesso,
                    "protocolo": response.protocolo,
                    "qrcode_url": qr_url,
                    "status_codigo": response.status_codigo,
                    "status_descricao": response.status_descricao,
                }

            return {
                "autorizado": False,
                "status_codigo": response.status_codigo,
                "status_descricao": response.status_descricao,
                "rejeicoes": response.rejeicoes,
            }

        except Exception as e:
            logger.error(f"Erro ao autorizar NFC-e: {e}")
            return {
                "autorizado": False,
                "erro": str(e),
            }


# Singleton
nfce_service = NFCeService()
