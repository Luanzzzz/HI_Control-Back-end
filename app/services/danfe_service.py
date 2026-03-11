"""
Serviço de geração de DANFE (Documento Auxiliar da NF-e) em PDF.

Suporta:
- DANFE NF-e (modelo 55) - formato retrato A4
- DANFCE NFC-e (modelo 65) - formato cupom com QR Code
- DACTE CT-e (modelo 57) - formato retrato A4

Usa ReportLab para geração de PDF.
"""
import io
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

logger = logging.getLogger(__name__)


class DanfeService:
    """Serviço para geração de DANFE/DANFCE/DACTE em PDF."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============================================
    # DANFE NF-e (modelo 55)
    # ============================================

    def gerar_danfe(self, xml_content: str) -> bytes:
        """
        Gera DANFE (PDF) a partir do XML autorizado da NF-e.

        Args:
            xml_content: XML completo da NF-e (procNFe ou NFe)

        Returns:
            Bytes do PDF gerado
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors

        # Parse XML
        dados = self._extrair_dados_nfe(xml_content)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Margens
        margin = 10 * mm
        usable_w = width - 2 * margin

        y = height - margin

        # === CABEÇALHO ===
        y = self._desenhar_cabecalho_danfe(c, dados, margin, y, usable_w)

        # === DESTINATÁRIO ===
        y = self._desenhar_destinatario(c, dados, margin, y, usable_w)

        # === PRODUTOS ===
        y = self._desenhar_produtos(c, dados, margin, y, usable_w)

        # === TOTAIS ===
        y = self._desenhar_totais(c, dados, margin, y, usable_w)

        # === TRANSPORTE ===
        y = self._desenhar_transporte(c, dados, margin, y, usable_w)

        # === INFORMAÇÕES COMPLEMENTARES ===
        self._desenhar_info_complementar(c, dados, margin, y, usable_w)

        c.save()
        return buffer.getvalue()

    def _desenhar_cabecalho_danfe(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm
        from reportlab.lib import colors

        box_h = 35 * mm
        y -= box_h

        # Box externo
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.rect(margin, y, w, box_h)

        # Emitente
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin + 3 * mm, y + box_h - 6 * mm,
                      dados.get("emit_nome", "")[:60])

        c.setFont("Helvetica", 7)
        cnpj = dados.get("emit_cnpj", "")
        ie = dados.get("emit_ie", "")
        c.drawString(margin + 3 * mm, y + box_h - 11 * mm,
                      f"CNPJ: {cnpj}  |  IE: {ie}")

        endereco = dados.get("emit_endereco", "")
        c.drawString(margin + 3 * mm, y + box_h - 15 * mm, endereco[:80])

        # DANFE título
        cx = margin + w * 0.55
        c.setFont("Helvetica-Bold", 14)
        c.drawString(cx, y + box_h - 8 * mm, "DANFE")

        c.setFont("Helvetica", 7)
        c.drawString(cx, y + box_h - 13 * mm,
                      "Documento Auxiliar da Nota Fiscal Eletrônica")

        entrada_saida = "1 - SAÍDA" if dados.get("tipo_nf") == "1" else "0 - ENTRADA"
        c.drawString(cx, y + box_h - 17 * mm, entrada_saida)

        c.drawString(cx, y + box_h - 22 * mm,
                      f"Nº: {dados.get('numero', '')}  Série: {dados.get('serie', '')}")

        # Chave de acesso
        c.setFont("Helvetica", 6)
        chave = dados.get("chave_acesso", "")
        c.drawString(margin + 3 * mm, y + 3 * mm,
                      f"CHAVE DE ACESSO: {chave}")

        return y - 2 * mm

    def _desenhar_destinatario(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm

        box_h = 18 * mm
        y -= box_h

        c.setLineWidth(0.5)
        c.rect(margin, y, w, box_h)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "DESTINATÁRIO/REMETENTE")

        c.setFont("Helvetica", 7)
        c.drawString(margin + 2 * mm, y + box_h - 9 * mm,
                      f"Nome: {dados.get('dest_nome', '')}")
        c.drawString(margin + 2 * mm, y + box_h - 13 * mm,
                      f"CNPJ/CPF: {dados.get('dest_cnpj', '')}  |  IE: {dados.get('dest_ie', '')}")
        c.drawString(margin + 2 * mm, y + box_h - 17 * mm,
                      f"Endereço: {dados.get('dest_endereco', '')}")

        return y - 2 * mm

    def _desenhar_produtos(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm

        produtos = dados.get("produtos", [])

        # Cabeçalho da tabela
        header_h = 6 * mm
        y -= header_h

        c.setFont("Helvetica-Bold", 6)
        c.rect(margin, y, w, header_h)

        cols = [
            ("CÓDIGO", 0.12), ("DESCRIÇÃO", 0.32), ("NCM", 0.08),
            ("UN", 0.05), ("QTD", 0.08), ("V.UNIT", 0.10),
            ("V.TOTAL", 0.10), ("ICMS", 0.08), ("IPI", 0.07),
        ]

        x = margin + 1 * mm
        for col_name, col_pct in cols:
            c.drawString(x, y + 2 * mm, col_name)
            x += w * col_pct

        # Linhas de produto
        c.setFont("Helvetica", 6)
        row_h = 4.5 * mm

        for prod in produtos[:30]:  # Limitar a 30 itens por página
            y -= row_h
            if y < 60 * mm:  # Espaço mínimo para totais
                break

            c.rect(margin, y, w, row_h)
            x = margin + 1 * mm

            values = [
                str(prod.get("codigo", ""))[:15],
                str(prod.get("descricao", ""))[:45],
                str(prod.get("ncm", "")),
                str(prod.get("unidade", "")),
                str(prod.get("quantidade", "")),
                str(prod.get("valor_unitario", "")),
                str(prod.get("valor_total", "")),
                str(prod.get("valor_icms", "")),
                str(prod.get("valor_ipi", "")),
            ]

            for i, (_, col_pct) in enumerate(cols):
                c.drawString(x, y + 1.2 * mm, values[i] if i < len(values) else "")
                x += w * col_pct

        return y - 2 * mm

    def _desenhar_totais(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm

        box_h = 12 * mm
        y -= box_h

        c.setLineWidth(0.5)
        c.rect(margin, y, w, box_h)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "CÁLCULO DO IMPOSTO")

        c.setFont("Helvetica", 6)
        totais = [
            f"BC ICMS: {dados.get('bc_icms', '0,00')}",
            f"V.ICMS: {dados.get('valor_icms', '0,00')}",
            f"V.IPI: {dados.get('valor_ipi', '0,00')}",
            f"V.PIS: {dados.get('valor_pis', '0,00')}",
            f"V.COFINS: {dados.get('valor_cofins', '0,00')}",
            f"V.FRETE: {dados.get('valor_frete', '0,00')}",
            f"V.DESC: {dados.get('valor_desconto', '0,00')}",
            f"V.TOTAL: {dados.get('valor_total', '0,00')}",
        ]

        x = margin + 2 * mm
        for t in totais:
            c.drawString(x, y + 3 * mm, t)
            x += w / len(totais)

        return y - 2 * mm

    def _desenhar_transporte(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm

        box_h = 10 * mm
        y -= box_h

        c.setLineWidth(0.5)
        c.rect(margin, y, w, box_h)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "TRANSPORTADOR/VOLUMES")

        c.setFont("Helvetica", 6)
        c.drawString(margin + 2 * mm, y + 2 * mm,
                      f"Frete: {dados.get('frete_tipo', 'Sem frete')}")

        return y - 2 * mm

    def _desenhar_info_complementar(self, c, dados, margin, y, w):
        from reportlab.lib.units import mm

        box_h = max(y - 15 * mm, 15 * mm)
        y_box = 15 * mm

        c.setLineWidth(0.5)
        c.rect(margin, y_box, w, box_h)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y_box + box_h - 4 * mm,
                      "INFORMAÇÕES COMPLEMENTARES")

        c.setFont("Helvetica", 6)
        info = dados.get("info_complementar", "")
        # Quebrar texto em linhas
        lines = info.split("\n")[:10]
        ty = y_box + box_h - 9 * mm
        for line in lines:
            c.drawString(margin + 2 * mm, ty, line[:120])
            ty -= 3 * mm

        # Protocolo
        c.setFont("Helvetica", 7)
        c.drawString(margin + 2 * mm, 8 * mm,
                      f"Protocolo: {dados.get('protocolo', '')}  |  "
                      f"Data autorização: {dados.get('data_autorizacao', '')}")

    def _extrair_dados_nfe(self, xml_content: str) -> Dict[str, Any]:
        """Extrai dados do XML da NF-e para geração do DANFE."""
        root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
        ns = "http://www.portalfiscal.inf.br/nfe"

        def gt(parent, tag):
            if parent is None:
                return ""
            elem = parent.find(f".//{{{ns}}}{tag}")
            if elem is None:
                elem = parent.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else ""

        inf = root.find(f".//{{{ns}}}infNFe")
        ide = root.find(f".//{{{ns}}}ide")
        emit = root.find(f".//{{{ns}}}emit")
        dest = root.find(f".//{{{ns}}}dest")
        total = root.find(f".//{{{ns}}}total")
        icms_tot = root.find(f".//{{{ns}}}ICMSTot")

        chave_raw = inf.get("Id", "") if inf is not None else ""
        chave = chave_raw.replace("NFe", "")

        # Endereço emitente
        emit_end = root.find(f".//{{{ns}}}enderEmit")
        emit_endereco = ""
        if emit_end is not None:
            emit_endereco = (
                f"{gt(emit_end, 'xLgr')}, {gt(emit_end, 'nro')} - "
                f"{gt(emit_end, 'xBairro')} - {gt(emit_end, 'xMun')}/{gt(emit_end, 'UF')}"
            )

        # Endereço destinatário
        dest_end = root.find(f".//{{{ns}}}enderDest")
        dest_endereco = ""
        if dest_end is not None:
            dest_endereco = (
                f"{gt(dest_end, 'xLgr')}, {gt(dest_end, 'nro')} - "
                f"{gt(dest_end, 'xBairro')} - {gt(dest_end, 'xMun')}/{gt(dest_end, 'UF')}"
            )

        # Produtos
        produtos = []
        for det in root.iter(f"{{{ns}}}det"):
            prod = det.find(f".//{{{ns}}}prod")
            imposto = det.find(f".//{{{ns}}}imposto")
            if prod is not None:
                produtos.append({
                    "codigo": gt(prod, "cProd"),
                    "descricao": gt(prod, "xProd"),
                    "ncm": gt(prod, "NCM"),
                    "unidade": gt(prod, "uCom"),
                    "quantidade": gt(prod, "qCom"),
                    "valor_unitario": gt(prod, "vUnCom"),
                    "valor_total": gt(prod, "vProd"),
                    "valor_icms": gt(imposto, "vICMS") if imposto is not None else "",
                    "valor_ipi": gt(imposto, "vIPI") if imposto is not None else "",
                })

        # Protocolo
        prot = root.find(f".//{{{ns}}}protNFe")
        protocolo = ""
        data_aut = ""
        if prot is not None:
            inf_prot = prot.find(f".//{{{ns}}}infProt")
            protocolo = gt(inf_prot, "nProt")
            data_aut = gt(inf_prot, "dhRecbto")

        # Info complementar
        inf_adic = root.find(f".//{{{ns}}}infAdic")
        info_comp = gt(inf_adic, "infCpl") if inf_adic is not None else ""

        return {
            "chave_acesso": chave,
            "numero": gt(ide, "nNF"),
            "serie": gt(ide, "serie"),
            "tipo_nf": gt(ide, "tpNF"),
            "data_emissao": gt(ide, "dhEmi"),
            "emit_nome": gt(emit, "xNome"),
            "emit_cnpj": gt(emit, "CNPJ"),
            "emit_ie": gt(emit, "IE"),
            "emit_endereco": emit_endereco,
            "dest_nome": gt(dest, "xNome"),
            "dest_cnpj": gt(dest, "CNPJ") or gt(dest, "CPF"),
            "dest_ie": gt(dest, "IE"),
            "dest_endereco": dest_endereco,
            "produtos": produtos,
            "bc_icms": gt(icms_tot, "vBC"),
            "valor_icms": gt(icms_tot, "vICMS"),
            "valor_ipi": gt(icms_tot, "vIPI"),
            "valor_pis": gt(icms_tot, "vPIS"),
            "valor_cofins": gt(icms_tot, "vCOFINS"),
            "valor_frete": gt(icms_tot, "vFrete"),
            "valor_desconto": gt(icms_tot, "vDesc"),
            "valor_total": gt(icms_tot, "vNF"),
            "protocolo": protocolo,
            "data_autorizacao": data_aut,
            "info_complementar": info_comp,
        }

    # ============================================
    # DANFCE NFC-e (modelo 65)
    # ============================================

    def gerar_danfce(self, xml_content: str, qr_code_url: str = "") -> bytes:
        """
        Gera DANFCE (cupom fiscal) a partir do XML da NFC-e.

        Args:
            xml_content: XML da NFC-e
            qr_code_url: URL do QR Code

        Returns:
            Bytes do PDF gerado
        """
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        dados = self._extrair_dados_nfe(xml_content)

        # Formato cupom: 80mm x variável
        page_w = 80 * mm
        page_h = 250 * mm  # Altura máxima

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(page_w, page_h))

        y = page_h - 5 * mm
        margin = 3 * mm
        usable_w = page_w - 2 * margin

        # Emitente
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(page_w / 2, y, dados.get("emit_nome", "")[:40])
        y -= 4 * mm
        c.setFont("Helvetica", 6)
        c.drawCentredString(page_w / 2, y, f"CNPJ: {dados.get('emit_cnpj', '')}")
        y -= 3 * mm
        c.drawCentredString(page_w / 2, y, dados.get("emit_endereco", "")[:50])
        y -= 5 * mm

        # Título
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(page_w / 2, y, "DANFE NFC-e - Documento Auxiliar")
        y -= 3 * mm
        c.drawCentredString(page_w / 2, y, "da Nota Fiscal de Consumidor Eletrônica")
        y -= 5 * mm

        # Linha
        c.line(margin, y, page_w - margin, y)
        y -= 4 * mm

        # Produtos
        c.setFont("Helvetica-Bold", 6)
        c.drawString(margin, y, "ITEM  DESCRIÇÃO                  QTD  V.UNIT  V.TOTAL")
        y -= 3 * mm

        c.setFont("Helvetica", 6)
        for i, prod in enumerate(dados.get("produtos", [])[:20], 1):
            desc = prod.get("descricao", "")[:25]
            qtd = prod.get("quantidade", "1")
            vunit = prod.get("valor_unitario", "0")
            vtotal = prod.get("valor_total", "0")
            c.drawString(margin, y, f"{i:03d}  {desc:<25}  {qtd:>5}  {vunit:>7}  {vtotal:>7}")
            y -= 3 * mm

        y -= 2 * mm
        c.line(margin, y, page_w - margin, y)
        y -= 4 * mm

        # Total
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(page_w / 2, y, f"TOTAL: R$ {dados.get('valor_total', '0,00')}")
        y -= 6 * mm

        # QR Code (placeholder - texto)
        if qr_code_url:
            try:
                import qrcode
                qr = qrcode.make(qr_code_url)
                qr_buffer = io.BytesIO()
                qr.save(qr_buffer, format="PNG")
                qr_buffer.seek(0)

                from reportlab.lib.utils import ImageReader
                qr_img = ImageReader(qr_buffer)
                qr_size = 30 * mm
                c.drawImage(qr_img, (page_w - qr_size) / 2, y - qr_size,
                            width=qr_size, height=qr_size)
                y -= qr_size + 3 * mm
            except ImportError:
                c.setFont("Helvetica", 6)
                c.drawCentredString(page_w / 2, y, "[QR Code]")
                y -= 5 * mm

        # Chave de acesso
        c.setFont("Helvetica", 5)
        c.drawCentredString(page_w / 2, y, f"Chave: {dados.get('chave_acesso', '')}")
        y -= 3 * mm
        c.drawCentredString(page_w / 2, y, f"Protocolo: {dados.get('protocolo', '')}")

        c.save()
        return buffer.getvalue()

    # ============================================
    # DACTE CT-e (modelo 57)
    # ============================================

    def gerar_dacte(self, xml_content: str) -> bytes:
        """
        Gera DACTE a partir do XML do CT-e.

        Args:
            xml_content: XML do CT-e

        Returns:
            Bytes do PDF gerado
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        dados = self._extrair_dados_cte(xml_content)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        margin = 10 * mm
        usable_w = width - 2 * margin

        y = height - margin

        # Cabeçalho
        box_h = 30 * mm
        y -= box_h
        c.rect(margin, y, usable_w, box_h)

        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(width / 2, y + box_h - 8 * mm, "DACTE")

        c.setFont("Helvetica", 7)
        c.drawCentredString(width / 2, y + box_h - 13 * mm,
                            "Documento Auxiliar do Conhecimento de Transporte Eletrônico")

        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin + 3 * mm, y + box_h - 20 * mm,
                      f"CT-e Nº: {dados.get('numero', '')}  Série: {dados.get('serie', '')}")

        c.setFont("Helvetica", 6)
        c.drawString(margin + 3 * mm, y + 3 * mm,
                      f"Chave: {dados.get('chave_acesso', '')}")

        y -= 3 * mm

        # Emitente
        box_h = 18 * mm
        y -= box_h
        c.rect(margin, y, usable_w, box_h)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "EMITENTE")
        c.setFont("Helvetica", 7)
        c.drawString(margin + 2 * mm, y + box_h - 9 * mm,
                      f"Nome: {dados.get('emit_nome', '')}")
        c.drawString(margin + 2 * mm, y + box_h - 13 * mm,
                      f"CNPJ: {dados.get('emit_cnpj', '')}  |  IE: {dados.get('emit_ie', '')}")

        y -= 3 * mm

        # Remetente/Destinatário
        box_h = 15 * mm
        y -= box_h
        c.rect(margin, y, usable_w, box_h)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "REMETENTE / DESTINATÁRIO")
        c.setFont("Helvetica", 7)
        c.drawString(margin + 2 * mm, y + box_h - 9 * mm,
                      f"Rem: {dados.get('rem_nome', '')} ({dados.get('rem_cnpj', '')})")
        c.drawString(margin + 2 * mm, y + box_h - 13 * mm,
                      f"Dest: {dados.get('dest_nome', '')} ({dados.get('dest_cnpj', '')})")

        y -= 3 * mm

        # Valores
        box_h = 12 * mm
        y -= box_h
        c.rect(margin, y, usable_w, box_h)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 2 * mm, y + box_h - 4 * mm, "VALORES DA PRESTAÇÃO")
        c.setFont("Helvetica", 8)
        c.drawString(margin + 2 * mm, y + 3 * mm,
                      f"Valor Total: R$ {dados.get('valor_total', '0,00')}  |  "
                      f"Valor Receber: R$ {dados.get('valor_receber', '0,00')}")

        # Protocolo
        c.setFont("Helvetica", 7)
        c.drawString(margin, 10 * mm,
                      f"Protocolo: {dados.get('protocolo', '')}  |  "
                      f"Modal: {dados.get('modal', '')}")

        c.save()
        return buffer.getvalue()

    def _extrair_dados_cte(self, xml_content: str) -> Dict[str, Any]:
        """Extrai dados do XML do CT-e para geração do DACTE."""
        root = etree.fromstring(
            xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
        )
        ns = "http://www.portalfiscal.inf.br/cte"

        def gt(parent, tag):
            if parent is None:
                return ""
            elem = parent.find(f".//{{{ns}}}{tag}")
            if elem is None:
                elem = parent.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else ""

        inf = root.find(f".//{{{ns}}}infCte")
        ide = root.find(f".//{{{ns}}}ide")
        emit = root.find(f".//{{{ns}}}emit")
        rem = root.find(f".//{{{ns}}}rem")
        dest = root.find(f".//{{{ns}}}dest")
        vprest = root.find(f".//{{{ns}}}vPrest")

        chave_raw = inf.get("Id", "") if inf is not None else ""
        chave = chave_raw.replace("CTe", "")

        prot = root.find(f".//{{{ns}}}protCTe")
        protocolo = ""
        if prot is not None:
            inf_prot = prot.find(f".//{{{ns}}}infProt")
            protocolo = gt(inf_prot, "nProt")

        return {
            "chave_acesso": chave,
            "numero": gt(ide, "nCT"),
            "serie": gt(ide, "serie"),
            "modal": gt(ide, "modal"),
            "emit_nome": gt(emit, "xNome"),
            "emit_cnpj": gt(emit, "CNPJ"),
            "emit_ie": gt(emit, "IE"),
            "rem_nome": gt(rem, "xNome"),
            "rem_cnpj": gt(rem, "CNPJ"),
            "dest_nome": gt(dest, "xNome"),
            "dest_cnpj": gt(dest, "CNPJ"),
            "valor_total": gt(vprest, "vTPrest"),
            "valor_receber": gt(vprest, "vRec"),
            "protocolo": protocolo,
        }


# Singleton
danfe_service = DanfeService()
