"""
Serviço de geração de DANFSE (Documento Auxiliar da NFS-e) em PDF.

Gera o documento auxiliar para NFS-e municipal (ABRASF) e Nacional (SEFIN).
Usa ReportLab para geração do PDF.
"""
import io
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DanfseService:
    """Gerador de DANFSE em PDF para NFS-e."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============================================
    # ENTRADA PRINCIPAL
    # ============================================

    def gerar_danfse(
        self,
        dados: Dict[str, Any],
        empresa: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        Gera DANFSE (PDF) a partir dos dados da NFS-e.

        Aceita dados vindos de duas origens:
        - Banco de dados local (notas_fiscais): usa _normalizar_dados_banco
        - Resposta de emissão direta: usa dados como vieram

        Args:
            dados: Dados da NFS-e (banco ou emissão direta)
            empresa: Dados da empresa prestadora (opcional, enriquece o PDF)

        Returns:
            Bytes do PDF gerado
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors

        dados_norm = self._normalizar_dados(dados, empresa)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        largura, altura = A4
        margem = 10 * mm
        util_w = largura - 2 * margem
        y = altura - margem

        y = self._cabecalho(c, dados_norm, margem, y, util_w, largura)
        y = self._bloco_prestador(c, dados_norm, margem, y, util_w)
        y = self._bloco_tomador(c, dados_norm, margem, y, util_w)
        y = self._bloco_servico(c, dados_norm, margem, y, util_w)
        y = self._bloco_valores(c, dados_norm, margem, y, util_w)
        self._bloco_verificacao(c, dados_norm, margem, y, util_w)

        c.save()
        return buffer.getvalue()

    # ============================================
    # NORMALIZAÇÃO DE DADOS
    # ============================================

    def _normalizar_dados(
        self,
        dados: Dict[str, Any],
        empresa: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Normaliza dados de diferentes origens para formato único."""
        return {
            # Identificação
            "numero_nfse": dados.get("numero_nfse") or dados.get("numero_nf", ""),
            "chave_acesso": dados.get("chave_acesso", ""),
            "codigo_verificacao": dados.get("codigo_verificacao", ""),
            "data_emissao": self._formatar_data(
                dados.get("data_emissao") or dados.get("data_autorizacao", "")
            ),
            "competencia": dados.get("competencia", ""),
            "link_visualizacao": dados.get("link_visualizacao", ""),
            # Prestador
            "prestador_razao_social": (empresa or {}).get("razao_social", dados.get("prestador_nome", "")),
            "prestador_cnpj": self._formatar_cnpj((empresa or {}).get("cnpj", dados.get("prestador_cnpj", ""))),
            "prestador_im": (empresa or {}).get("inscricao_municipal", ""),
            "prestador_municipio": (empresa or {}).get("municipio_nome", ""),
            "prestador_uf": (empresa or {}).get("uf", ""),
            "prestador_endereco": self._montar_endereco(empresa or {}),
            # Tomador
            "tomador_nome": dados.get("nome_destinatario", dados.get("tomador_nome", "")),
            "tomador_cnpj_cpf": self._formatar_doc(dados.get("cnpj_destinatario", dados.get("tomador_cnpj", ""))),
            "tomador_endereco": dados.get("tomador_endereco", ""),
            "tomador_email": dados.get("tomador_email", ""),
            # Serviço
            "descricao_servico": dados.get("descricao_servico", dados.get("discriminacao", "")),
            "codigo_servico": dados.get("codigo_servico", ""),
            "municipio_prestacao": dados.get("municipio_nome", dados.get("municipio_prestacao", "")),
            # Valores
            "valor_servicos": float(dados.get("valor_total", dados.get("valor_servicos", 0))),
            "valor_deducoes": float(dados.get("valor_deducoes", 0)),
            "valor_iss": float(dados.get("valor_iss", 0)),
            "aliquota_iss": float(dados.get("aliquota_iss", 0)),
            "valor_pis": float(dados.get("valor_pis", 0)),
            "valor_cofins": float(dados.get("valor_cofins", 0)),
            "valor_inss": float(dados.get("valor_inss", 0)),
            "valor_ir": float(dados.get("valor_ir", 0)),
            "valor_csll": float(dados.get("valor_csll", 0)),
            "valor_liquido": float(dados.get("valor_liquido", dados.get("valor_total", dados.get("valor_servicos", 0)))),
            "iss_retido": dados.get("iss_retido", "2") == "1",
            # IBS/CBS (padrão nacional LC 214/2025)
            "valor_ibs": float(dados.get("valor_ibs", 0)),
            "valor_cbs": float(dados.get("valor_cbs", 0)),
            # Situação
            "situacao": dados.get("situacao", "autorizada"),
        }

    def _montar_endereco(self, empresa: Dict) -> str:
        partes = []
        if empresa.get("logradouro"):
            partes.append(empresa["logradouro"])
        if empresa.get("numero"):
            partes.append(f"nº {empresa['numero']}")
        if empresa.get("bairro"):
            partes.append(empresa["bairro"])
        return ", ".join(partes)

    def _formatar_cnpj(self, cnpj: str) -> str:
        digits = "".join(c for c in (cnpj or "") if c.isdigit())
        if len(digits) == 14:
            return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
        return cnpj or ""

    def _formatar_doc(self, doc: str) -> str:
        digits = "".join(c for c in (doc or "") if c.isdigit())
        if len(digits) == 14:
            return self._formatar_cnpj(digits)
        if len(digits) == 11:
            return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
        return doc or ""

    def _formatar_data(self, data_str: str) -> str:
        if not data_str:
            return ""
        try:
            if "T" in data_str:
                dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
                return dt.strftime("%d/%m/%Y %H:%M")
            return data_str[:10].replace("-", "/")[::-1].replace("/", "/", 2)
        except Exception:
            return data_str[:10] if len(data_str) >= 10 else data_str

    # ============================================
    # BLOCOS DO PDF
    # ============================================

    def _cabecalho(self, c, d, x, y, w, largura):
        from reportlab.lib.units import mm
        from reportlab.lib import colors

        # Faixa de título
        c.setFillColor(colors.HexColor("#1a3a5c"))
        c.rect(x, y - 16 * mm, w, 16 * mm, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(largura / 2, y - 10 * mm, "NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e")

        y -= 17 * mm

        # Linha de identificação: número + data
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y, f"Número: {d['numero_nfse'] or 'Em processamento'}")
        c.drawRightString(x + w, y, f"Data de Emissão: {d['data_emissao']}")
        y -= 5 * mm

        # Chave de acesso
        if d["chave_acesso"]:
            c.setFont("Helvetica", 7)
            c.drawString(x, y, f"Chave de Acesso: {d['chave_acesso']}")
            y -= 5 * mm

        # Situação
        situacao = d["situacao"].upper()
        cor_sit = colors.HexColor("#2e7d32") if situacao == "AUTORIZADA" else colors.HexColor("#c62828")
        c.setFillColor(cor_sit)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"Situação: {situacao}")
        c.setFillColor(colors.black)
        y -= 6 * mm

        self._linha_divisoria(c, x, y, w)
        return y - 3 * mm

    def _bloco_prestador(self, c, d, x, y, w):
        from reportlab.lib.units import mm

        y = self._titulo_bloco(c, "PRESTADOR DE SERVIÇOS", x, y, w)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, d["prestador_razao_social"])
        y -= 4 * mm

        c.setFont("Helvetica", 8)
        linha = f"CNPJ: {d['prestador_cnpj']}"
        if d["prestador_im"]:
            linha += f"   IM: {d['prestador_im']}"
        c.drawString(x, y, linha)
        y -= 4 * mm

        if d["prestador_endereco"]:
            mun = d.get("prestador_municipio", "")
            uf = d.get("prestador_uf", "")
            c.drawString(x, y, f"{d['prestador_endereco']} — {mun}/{uf}")
            y -= 4 * mm

        self._linha_divisoria(c, x, y, w)
        return y - 3 * mm

    def _bloco_tomador(self, c, d, x, y, w):
        from reportlab.lib.units import mm

        y = self._titulo_bloco(c, "TOMADOR DE SERVIÇOS", x, y, w)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, d["tomador_nome"] or "(Consumidor Final)")
        y -= 4 * mm

        c.setFont("Helvetica", 8)
        if d["tomador_cnpj_cpf"]:
            c.drawString(x, y, f"CPF/CNPJ: {d['tomador_cnpj_cpf']}")
            y -= 4 * mm
        if d["tomador_endereco"]:
            c.drawString(x, y, d["tomador_endereco"])
            y -= 4 * mm
        if d["tomador_email"]:
            c.drawString(x, y, f"E-mail: {d['tomador_email']}")
            y -= 4 * mm

        self._linha_divisoria(c, x, y, w)
        return y - 3 * mm

    def _bloco_servico(self, c, d, x, y, w):
        from reportlab.lib.units import mm

        y = self._titulo_bloco(c, "DISCRIMINAÇÃO DO SERVIÇO", x, y, w)

        c.setFont("Helvetica", 8)
        if d["codigo_servico"]:
            c.drawString(x, y, f"Código LC 116: {d['codigo_servico']}")
            y -= 4 * mm
        if d["municipio_prestacao"]:
            c.drawString(x, y, f"Município de Prestação: {d['municipio_prestacao']}")
            y -= 4 * mm

        # Discriminação (texto longo com quebra de linha)
        descricao = d["descricao_servico"] or ""
        y = self._texto_multilinhas(c, descricao, x, y, w, fonte_tam=8, interlinhas=4)

        self._linha_divisoria(c, x, y, w)
        return y - 3 * mm

    def _bloco_valores(self, c, d, x, y, w):
        from reportlab.lib.units import mm

        y = self._titulo_bloco(c, "VALORES", x, y, w)

        col_label = x
        col_value = x + w * 0.55
        col_right_label = x + w * 0.6
        col_right_value = x + w

        linhas = [
            ("Valor dos Serviços:", d["valor_servicos"]),
            ("(-) Deduções:", d["valor_deducoes"]),
            ("(=) Base de Cálculo:", d["valor_servicos"] - d["valor_deducoes"]),
        ]
        impostos = [
            ("ISS" + (" (Retido)" if d["iss_retido"] else "") + f" ({d['aliquota_iss']:.2f}%):", d["valor_iss"]),
            ("PIS:", d["valor_pis"]),
            ("COFINS:", d["valor_cofins"]),
            ("INSS:", d["valor_inss"]),
            ("IR:", d["valor_ir"]),
            ("CSLL:", d["valor_csll"]),
        ]
        if d["valor_ibs"] > 0:
            impostos.append(("IBS (LC 214/2025):", d["valor_ibs"]))
        if d["valor_cbs"] > 0:
            impostos.append(("CBS (LC 214/2025):", d["valor_cbs"]))

        c.setFont("Helvetica", 8)
        # Coluna esquerda: base de cálculo
        for label, valor in linhas:
            c.drawString(col_label, y, label)
            c.drawRightString(col_value - 2, y, f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            y -= 4 * mm

        # Coluna direita (impostos) — reposicionar y ao início
        y_impostos = y + len(linhas) * 4 * mm
        c.setFont("Helvetica", 8)
        for label, valor in impostos:
            if valor > 0:
                c.drawString(col_right_label, y_impostos, label)
                c.drawRightString(col_right_value, y_impostos, f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                y_impostos -= 4 * mm

        # Valor líquido
        y = min(y, y_impostos) - 2 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y, "VALOR LÍQUIDO:")
        c.drawRightString(x + w, y, f"R$ {d['valor_liquido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        y -= 6 * mm

        self._linha_divisoria(c, x, y, w)
        return y - 3 * mm

    def _bloco_verificacao(self, c, d, x, y, w):
        from reportlab.lib.units import mm
        from reportlab.lib import colors

        if not d["codigo_verificacao"] and not d["link_visualizacao"]:
            return

        y = self._titulo_bloco(c, "AUTENTICAÇÃO / VERIFICAÇÃO", x, y, w)

        c.setFont("Helvetica", 8)
        if d["codigo_verificacao"]:
            c.drawString(x, y, f"Código de Verificação: {d['codigo_verificacao']}")
            y -= 4 * mm

        if d["link_visualizacao"]:
            c.setFillColor(colors.HexColor("#1565c0"))
            c.drawString(x, y, f"Consulta online: {d['link_visualizacao']}")
            c.setFillColor(colors.black)
            y -= 4 * mm

            # QR Code do link
            try:
                import qrcode
                qr = qrcode.make(d["link_visualizacao"])
                qr_buffer = io.BytesIO()
                qr.save(qr_buffer, format="PNG")
                qr_buffer.seek(0)
                from reportlab.lib.utils import ImageReader
                img = ImageReader(qr_buffer)
                c.drawImage(img, x + w - 25 * mm, y - 20 * mm, width=25 * mm, height=25 * mm)
            except Exception:
                pass

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawCentredString(
            x + w / 2,
            y - 8 * mm,
            "Documento gerado eletronicamente. Verifique a autenticidade no portal da prefeitura.",
        )

    # ============================================
    # UTILITÁRIOS DE DESENHO
    # ============================================

    def _titulo_bloco(self, c, titulo: str, x, y, w):
        from reportlab.lib.units import mm
        from reportlab.lib import colors

        c.setFillColor(colors.HexColor("#e8eaf6"))
        c.rect(x, y - 5 * mm, w, 5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1a237e"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 2, y - 3.5 * mm, titulo)
        c.setFillColor(colors.black)
        return y - 7 * mm

    def _linha_divisoria(self, c, x, y, w):
        from reportlab.lib import colors
        c.setStrokeColor(colors.HexColor("#bdbdbd"))
        c.setLineWidth(0.5)
        c.line(x, y, x + w, y)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)

    def _texto_multilinhas(self, c, texto: str, x, y, w, fonte_tam=8, interlinhas=4):
        from reportlab.lib.units import mm

        if not texto:
            return y

        c.setFont("Helvetica", fonte_tam)
        chars_por_linha = int(w / (fonte_tam * 0.55))
        palavras = texto.split()
        linha_atual = ""

        for palavra in palavras:
            teste = f"{linha_atual} {palavra}".strip()
            if len(teste) <= chars_por_linha:
                linha_atual = teste
            else:
                c.drawString(x, y, linha_atual)
                y -= interlinhas * mm
                linha_atual = palavra

        if linha_atual:
            c.drawString(x, y, linha_atual)
            y -= interlinhas * mm

        return y


# Singleton
danfse_service = DanfseService()
