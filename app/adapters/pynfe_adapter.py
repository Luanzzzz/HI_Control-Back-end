"""
Adapter para conversão entre modelos Hi-Control (Pydantic) e PyNFE.

Este adapter implementa o padrão Adapter Pattern para permitir
comunicação entre sistemas com estruturas de dados incompatíveis.

Responsabilidades:
- Converter NotaFiscalCompletaCreate → objetos PyNFE (Emitente, Cliente, NotaFiscal)
- Converter XML de resposta SEFAZ → SefazResponseModel
- Extrair informações de XMLs (chave de acesso, protocolo, rejeições)
"""
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, date
import tempfile
import os

try:
    from lxml import etree
except ImportError:
    etree = None

try:
    from pynfe.entidades.emitente import Emitente
    from pynfe.entidades.cliente import Cliente
    from pynfe.entidades.notafiscal import NotaFiscal
    from pynfe.entidades.produto import Produto
    from pynfe.entidades.transporte import Transportadora, TransporteVolume
    from pynfe.processamento.serializacao import SerializacaoXML
    from pynfe.processamento.assinatura import AssinaturaA1
    from pynfe.utils.flags import CODIGO_BRASIL
except ImportError:
    # Mock para desenvolvimento sem PyNFE instalado
    Emitente = None
    Cliente = None
    NotaFiscal = None
    Produto = None
    Transportadora = None
    TransporteVolume = None
    SerializacaoXML = None
    AssinaturaA1 = None
    CODIGO_BRASIL = '1058'

from app.models.nfe_completa import (
    NotaFiscalCompletaCreate,
    ItemNFeBase,
    DestinatarioNFe,
    SefazResponseModel,
    SefazRejeicao,
)

logger = logging.getLogger(__name__)

# Namespace NFe 4.0
NAMESPACE_NFE = "http://www.portalfiscal.inf.br/nfe"


class PyNFeAdapter:
    """
    Adapter para conversão bidirecional entre modelos Hi-Control e PyNFE.
    """

    def __init__(self):
        if SerializacaoXML:
            self.serializador = SerializacaoXML()
        else:
            self.serializador = None
            logger.warning("PyNFE não disponível - adapter em modo mock")

    # ============================================
    # CONVERSÃO: Hi-Control → PyNFE
    # ============================================

    def to_pynfe_emitente(self, empresa_dados: Dict[str, Any]) -> Any:
        """
        Converte dados da empresa (dict do Supabase) para Emitente do PyNFE.

        Args:
            empresa_dados: Dados da empresa do banco

        Returns:
            Objeto Emitente do PyNFE
        """
        if Emitente is None:
            raise ValueError("PyNFE não instalado")

        # Extrair apenas números do CNPJ
        cnpj = ''.join(filter(str.isdigit, empresa_dados.get('cnpj', '')))

        emitente = Emitente(
            razao_social=empresa_dados.get('razao_social', ''),
            nome_fantasia=empresa_dados.get('nome_fantasia') or empresa_dados.get('razao_social', ''),
            cnpj=cnpj,
            codigo_de_regime_tributario='1',  # 1=Simples Nacional (ajustar conforme regime)
            inscricao_estadual=empresa_dados.get('inscricao_estadual', ''),
            inscricao_municipal=empresa_dados.get('inscricao_municipal', ''),
            cnae_fiscal=empresa_dados.get('cnae_fiscal', ''),
            endereco_logradouro=empresa_dados.get('logradouro', 'Rua Principal'),
            endereco_numero=empresa_dados.get('numero', 'SN'),
            endereco_complemento=empresa_dados.get('complemento', ''),
            endereco_bairro=empresa_dados.get('bairro', 'Centro'),
            endereco_municipio=empresa_dados.get('cidade', 'Sao Paulo'),
            endereco_uf=empresa_dados.get('uf', 'SP'),
            endereco_cep=''.join(filter(str.isdigit, empresa_dados.get('cep', '01310000'))),
            endereco_pais=CODIGO_BRASIL,
        )

        return emitente

    def to_pynfe_cliente(self, destinatario: DestinatarioNFe) -> Any:
        """
        Converte DestinatarioNFe (Pydantic) para Cliente do PyNFE.

        Args:
            destinatario: Modelo Pydantic do destinatário

        Returns:
            Objeto Cliente do PyNFE
        """
        if Cliente is None:
            raise ValueError("PyNFE não instalado")

        # Determinar tipo de documento
        if destinatario.cpf:
            tipo_documento = 'CPF'
            numero_documento = ''.join(filter(str.isdigit, destinatario.cpf))
        elif destinatario.cnpj:
            tipo_documento = 'CNPJ'
            numero_documento = ''.join(filter(str.isdigit, destinatario.cnpj))
        else:
            raise ValueError("Destinatário deve ter CPF ou CNPJ")

        # Indicador IE: 1=Contribuinte, 2=Isento, 9=Não contribuinte
        indicador_ie = int(destinatario.indicador_inscricao_estadual)

        cliente = Cliente(
            razao_social=destinatario.razao_social,
            tipo_documento=tipo_documento,
            email=destinatario.email or '',
            numero_documento=numero_documento,
            indicador_ie=indicador_ie,
            inscricao_estadual=destinatario.inscricao_estadual or '',
            endereco_logradouro=destinatario.endereco_logradouro,
            endereco_numero=destinatario.endereco_numero,
            endereco_complemento=destinatario.endereco_complemento or '',
            endereco_bairro=destinatario.endereco_bairro,
            endereco_municipio=destinatario.municipio,
            endereco_uf=destinatario.uf,
            endereco_cep=''.join(filter(str.isdigit, destinatario.cep)),
            endereco_pais=destinatario.codigo_pais or CODIGO_BRASIL,
            endereco_telefone=destinatario.telefone or '',
        )

        return cliente

    def to_pynfe_produto(self, item: ItemNFeBase) -> Any:
        """
        Converte ItemNFeBase (Pydantic) para Produto do PyNFE.

        Args:
            item: Item da NF-e

        Returns:
            Objeto Produto do PyNFE configurado
        """
        if Produto is None:
            raise ValueError("PyNFE não instalado")

        # Importar classes de impostos
        try:
            from pynfe.entidades.produto import ICMS, IPI, PIS, COFINS
        except ImportError:
            raise ValueError("Módulo pynfe.entidades.produto não disponível")

        # Criar produto base
        produto = Produto(
            codigo=item.codigo_produto,
            descricao=item.descricao,
            ncm=item.ncm,
            cfop=item.cfop,
            unidade_comercial=item.unidade_comercial,
            quantidade_comercial=float(item.quantidade_comercial),
            valor_unitario_comercial=float(item.valor_unitario_comercial),
            valor_total_bruto=float(item.valor_total_bruto),
            unidade_tributavel=item.unidade_tributavel or item.unidade_comercial,
            quantidade_tributavel=float(item.quantidade_tributavel or item.quantidade_comercial),
            valor_unitario_tributavel=float(item.valor_unitario_tributavel or item.valor_unitario_comercial),
            ean=item.ean or 'SEM GTIN',
            ean_tributavel=item.ean_tributavel or item.ean or 'SEM GTIN',
            ind_total=1,  # 1=Compõe total da NF-e
            cest=item.cest,
            valor_frete=float(item.valor_frete or 0),
            valor_seguro=float(item.valor_seguro or 0),
            valor_desconto=float(item.valor_desconto or 0),
            valor_outras_despesas=float(item.valor_outras_despesas or 0),
        )

        # Configurar ICMS
        icms = ICMS(
            origem=int(item.impostos.icms.origem),
            situacao_tributaria=item.impostos.icms.cst,
            modalidade_base_calculo=item.impostos.icms.modalidade_bc or 0,
            base_calculo=float(item.impostos.icms.base_calculo),
            aliquota=float(item.impostos.icms.aliquota),
            valor=float(item.impostos.icms.valor),
        )

        # ICMS ST (se houver)
        if item.impostos.icms.base_calculo_st:
            icms.modalidade_base_calculo_st = item.impostos.icms.modalidade_bc_st or 4
            icms.base_calculo_st = float(item.impostos.icms.base_calculo_st)
            icms.aliquota_st = float(item.impostos.icms.aliquota_st or 0)
            icms.valor_st = float(item.impostos.icms.valor_st or 0)

        produto.icms = [icms]

        # IPI (opcional)
        if item.impostos.ipi:
            ipi = IPI(
                situacao_tributaria=item.impostos.ipi.cst,
                base_calculo=float(item.impostos.ipi.base_calculo),
                aliquota=float(item.impostos.ipi.aliquota),
                valor=float(item.impostos.ipi.valor),
            )
            produto.ipi = [ipi]

        # PIS
        pis = PIS(
            situacao_tributaria=item.impostos.pis.cst,
            base_calculo=float(item.impostos.pis.base_calculo),
            aliquota=float(item.impostos.pis.aliquota),
            valor=float(item.impostos.pis.valor),
        )
        produto.pis = [pis]

        # COFINS
        cofins = COFINS(
            situacao_tributaria=item.impostos.cofins.cst,
            base_calculo=float(item.impostos.cofins.base_calculo),
            aliquota=float(item.impostos.cofins.aliquota),
            valor=float(item.impostos.cofins.valor),
        )
        produto.cofins = [cofins]

        return produto

    def to_pynfe_nota_fiscal(
        self,
        nfe_data: NotaFiscalCompletaCreate,
        emitente: Any,
        cliente: Any,
        empresa_dados: Dict[str, Any]
    ) -> Any:
        """
        Converte NotaFiscalCompletaCreate completo para NotaFiscal do PyNFE.

        Args:
            nfe_data: Dados completos da NF-e (Pydantic)
            emitente: Emitente já convertido
            cliente: Cliente já convertido
            empresa_dados: Dados adicionais da empresa

        Returns:
            Objeto NotaFiscal do PyNFE pronto para serialização
        """
        if NotaFiscal is None:
            raise ValueError("PyNFE não instalado")

        # Calcular totais
        totais = nfe_data.calcular_totais()

        # Criar NotaFiscal
        nota = NotaFiscal(
            emitente=emitente,
            cliente=cliente,
            uf=empresa_dados.get('uf', 'SP'),
            natureza_operacao=self._determinar_natureza_operacao(nfe_data),
            forma_pagamento=0 if not nfe_data.cobranca else 1,  # 0=à vista, 1=a prazo
            tipo_pagamento=1,  # 1=Dinheiro
            modelo=int(nfe_data.modelo),
            serie=nfe_data.serie,
            numero_nf=nfe_data.numero_nf,
            data_emissao=datetime.now(),
            data_saida_entrada=datetime.now(),
            tipo_documento=1,  # 1=Saída
            municipio=empresa_dados.get('cidade', 'Sao Paulo'),
            tipo_impressao_danfe=1,  # 1=Retrato
            forma_emissao='1',  # 1=Normal
            cliente_final=1,  # 1=Consumidor final
            indicador_destino=1,  # 1=Operação interna
            indicador_presencial=1,  # 1=Presencial
            finalidade_emissao='1',  # 1=Normal
            processo_emissao='0',  # 0=Aplicação do contribuinte
            transporte_modalidade_frete=nfe_data.transporte.modalidade_frete if nfe_data.transporte else 9,
            informacoes_adicionais_interesse_fisco=nfe_data.informacoes_fisco or '',
            informacoes_complementares_interesse_contribuinte=nfe_data.informacoes_complementares or '',
            totais_tributos_aproximado=float(
                totais['total_icms'] + totais['total_pis'] + totais['total_cofins']
            ),
        )

        # Adicionar produtos
        for item_data in nfe_data.itens:
            produto = self.to_pynfe_produto(item_data)
            nota.adicionar_produto_servico(produto)

        # Adicionar transportadora (se houver)
        if nfe_data.transporte and nfe_data.transporte.transportadora:
            transportadora = self._criar_transportadora(nfe_data.transporte.transportadora)
            nota.adicionar_responsavel_transporte(transportadora)

        # Adicionar duplicatas (se houver)
        if nfe_data.cobranca and nfe_data.cobranca.duplicatas:
            for dup in nfe_data.cobranca.duplicatas:
                nota.adicionar_duplicata(
                    numero=dup.numero_duplicata,
                    data_vencimento=dup.data_vencimento,
                    valor=str(dup.valor)
                )

        return nota

    def _criar_transportadora(self, transp_data) -> Any:
        """Cria objeto Transportadora do PyNFE"""
        if Transportadora is None:
            return None

        return Transportadora(
            razao_social=transp_data.razao_social or '',
            cpf_cnpj=''.join(filter(str.isdigit, transp_data.cnpj_cpf or '')),
            inscricao_estadual=transp_data.inscricao_estadual or '',
            endereco=transp_data.endereco or '',
            municipio=transp_data.municipio or '',
            uf=transp_data.uf or '',
        )

    def _determinar_natureza_operacao(self, nfe_data: NotaFiscalCompletaCreate) -> str:
        """
        Determina natureza da operação baseado no CFOP.
        """
        if not nfe_data.itens:
            return "Venda de Mercadoria"

        cfop = nfe_data.itens[0].cfop
        primeiro_digito = cfop[0]

        naturezas = {
            '5': 'Venda de Mercadoria',
            '6': 'Venda Interestadual',
            '1': 'Compra de Mercadoria',
            '2': 'Compra Interestadual',
            '7': 'Venda para Exterior',
        }

        return naturezas.get(primeiro_digito, 'Operação Comercial')

    # ============================================
    # SERIALIZAÇÃO E ASSINATURA
    # ============================================

    def gerar_xml_nfe(self, nota_fiscal: Any, ambiente: str) -> str:
        """
        Gera XML da NF-e usando SerializacaoXML do PyNFE.

        Args:
            nota_fiscal: Objeto NotaFiscal do PyNFE
            ambiente: '1' (produção) ou '2' (homologação)

        Returns:
            String XML da NF-e
        """
        if self.serializador is None:
            raise ValueError("SerializacaoXML não disponível")

        xml_nfe = self.serializador._serializar_nfe(
            nota_fiscal,
            ambiente=int(ambiente),
        )

        logger.info("XML da NF-e gerado com sucesso")
        return xml_nfe

    def assinar_xml(
        self,
        xml_string: str,
        cert_bytes: bytes,
        senha_cert: str
    ) -> str:
        """
        Assina XML digitalmente com certificado A1.

        Args:
            xml_string: XML da NF-e não assinado
            cert_bytes: Bytes do certificado .pfx
            senha_cert: Senha do certificado

        Returns:
            XML assinado digitalmente

        Raises:
            ValueError: Se assinatura falhar
        """
        if AssinaturaA1 is None:
            raise ValueError("AssinaturaA1 não disponível")

        try:
            # PyNFE AssinaturaA1 precisa de arquivo, não bytes
            # Criar arquivo temporário
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pfx') as tmp:
                tmp.write(cert_bytes)
                cert_path = tmp.name

            try:
                # Criar assinador
                assinador = AssinaturaA1(cert_path, senha_cert)

                # Assinar XML
                xml_assinado = assinador.assinar(xml_string)

                logger.info("XML assinado digitalmente com sucesso")
                return xml_assinado

            finally:
                # Limpar arquivo temporário
                if os.path.exists(cert_path):
                    os.remove(cert_path)

        except Exception as e:
            logger.error(f"Erro ao assinar XML: {e}", exc_info=True)
            raise ValueError(f"Falha na assinatura digital: {str(e)}")

    # ============================================
    # CONVERSÃO: PyNFE/SEFAZ → Hi-Control
    # ============================================

    def parsear_resposta_sefaz(
        self,
        xml_retorno: str,
        uf: str,
        ambiente: str
    ) -> SefazResponseModel:
        """
        Converte XML de resposta da SEFAZ para SefazResponseModel.

        Args:
            xml_retorno: XML da resposta SEFAZ
            uf: UF emitente
            ambiente: '1' ou '2'

        Returns:
            SefazResponseModel com dados parseados
        """
        if etree is None:
            raise ValueError("lxml não disponível para parsear XML")

        try:
            # Parse XML
            root = etree.fromstring(xml_retorno.encode('utf-8'))

            # Namespace
            ns = {'nfe': NAMESPACE_NFE}

            # Extrair status
            codigo_elem = root.find('.//nfe:cStat', ns) or root.find('.//cStat')
            codigo = codigo_elem.text if codigo_elem is not None else '000'

            motivo_elem = root.find('.//nfe:xMotivo', ns) or root.find('.//xMotivo')
            descricao = motivo_elem.text if motivo_elem is not None else 'Erro desconhecido'

            # Extrair protocolo
            protocolo_elem = root.find('.//nfe:nProt', ns) or root.find('.//nProt')
            protocolo = protocolo_elem.text if protocolo_elem is not None else None

            # Extrair chave de acesso
            chave_elem = root.find('.//nfe:chNFe', ns) or root.find('.//chNFe')
            chave_acesso = chave_elem.text if chave_elem is not None else None

            # Processar rejeições
            rejeicoes = []

            # Códigos de erro (diferente de 100=autorizado)
            if codigo not in ['100', '101', '102', '135', '150', '151']:
                rejeicoes.append(
                    SefazRejeicao(
                        codigo=codigo,
                        motivo=descricao,
                        correcao=self._obter_sugestao_correcao(codigo),
                    )
                )

            # Criar response
            response = SefazResponseModel(
                status_codigo=codigo,
                status_descricao=descricao,
                protocolo=protocolo,
                chave_acesso=chave_acesso,
                rejeicoes=rejeicoes,
            )

            return response

        except Exception as e:
            logger.error(f"Erro ao parsear resposta SEFAZ: {e}", exc_info=True)

            # Retornar erro genérico
            return SefazResponseModel(
                status_codigo='999',
                status_descricao=f'Erro ao processar retorno: {str(e)}',
                rejeicoes=[
                    SefazRejeicao(
                        codigo='999',
                        motivo=str(e),
                        correcao='Verifique os logs do servidor'
                    )
                ],
            )

    def _obter_sugestao_correcao(self, codigo: str) -> Optional[str]:
        """
        Retorna sugestão de correção para códigos de rejeição comuns.
        """
        sugestoes = {
            '204': 'Verifique a duplicidade de NF-e no sistema',
            '205': 'CNPJ do emitente não habilitado para emissão de NF-e',
            '206': 'Inscrição Estadual inválida',
            '213': 'CNPJ do destinatário inválido',
            '214': 'CPF do destinatário inválido',
            '226': 'Código da UF diverge da UF autorizadora',
            '227': 'Data de emissão muito antiga',
            '231': 'Número da NF-e já está em uso',
            '232': 'Série inválida',
            '401': 'CPF do remetente inválido',
            '403': 'NCM inexistente ou inválido',
            '404': 'Valor do ICMS diverge do calculado',
            '539': 'Certificado digital vencido ou inválido',
        }

        return sugestoes.get(codigo)


# ============================================
# INSTÂNCIA GLOBAL
# ============================================
pynfe_adapter = PyNFeAdapter()
