"""
Service Layer para busca de Notas Fiscais
TODO: Substituir mock por integração real com python-nfe e Portal Nacional SEFAZ
"""
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from fastapi import HTTPException, status
import logging

from app.models.nota_fiscal import (
    NotaFiscalResponse,
    NotaFiscalDetalhada,
    BuscaNotaFilter,
    NotaFiscalSearchParams
)
from app.utils.validators import (
    validar_cnpj,
    validar_chave_nfe,
    validar_periodo_busca,
    extrair_info_chave_nfe
)
from app.utils.mock_data import get_notas_mock

logger = logging.getLogger(__name__)


class BuscaNotaFiscalService:
    """
    Serviço de busca de Notas Fiscais
    Centraliza a lógica de negócio relacionada à consulta de NF-e
    """

    @staticmethod
    async def validar_chave_acesso(chave: str) -> bool:
        """
        Valida chave de acesso de Nota Fiscal

        Args:
            chave: Chave de acesso (44 dígitos)

        Returns:
            True se chave válida

        Raises:
            HTTPException 422: Se chave inválida
        """
        if not validar_chave_nfe(chave):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Chave de acesso inválida. Deve conter 44 dígitos numéricos válidos."
            )
        return True

    @staticmethod
    async def buscar_notas(
        filtros: BuscaNotaFilter,
        usuario_id: Optional[str] = None
    ) -> List[NotaFiscalResponse]:
        """
        Busca notas fiscais com filtros

        Args:
            filtros: Filtros de busca
            usuario_id: ID do usuário fazendo a busca (para auditoria)

        Returns:
            Lista de notas fiscais encontradas

        Raises:
            HTTPException 400: Parâmetros inválidos
            HTTPException 422: Validação fiscal falhou
        """
        # Validar período de busca
        valido, erro = validar_periodo_busca(filtros.data_inicio, filtros.data_fim, max_dias=90)
        if not valido:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=erro
            )

        # Validar CNPJ se fornecido
        if filtros.cnpj_emitente and not validar_cnpj(filtros.cnpj_emitente):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CNPJ do emitente inválido"
            )

        # Validar chave de acesso se fornecida
        if filtros.chave_acesso:
            await BuscaNotaFiscalService.validar_chave_acesso(filtros.chave_acesso)

        # TODO: Substituir por consulta real ao banco de dados / Portal Nacional
        logger.info(f"Buscando notas fiscais - Usuário: {usuario_id}, Filtros: {filtros}")

        notas = get_notas_mock()

        # Aplicar filtros
        notas_filtradas = []

        for nota in notas:
            # Filtro por tipo
            if filtros.tipo_nf and nota.tipo_nf != filtros.tipo_nf:
                continue

            # Filtro por período
            data_nota = nota.data_emissao.date() if isinstance(nota.data_emissao, datetime) else nota.data_emissao
            if data_nota < filtros.data_inicio or data_nota > filtros.data_fim:
                continue

            # Filtro por CNPJ emitente
            if filtros.cnpj_emitente and nota.cnpj_emitente != filtros.cnpj_emitente:
                continue

            # Filtro por número
            if filtros.numero_nf and nota.numero_nf != filtros.numero_nf:
                continue

            # Filtro por série
            if filtros.serie and nota.serie != filtros.serie:
                continue

            # Filtro por situação
            if filtros.situacao and nota.situacao != filtros.situacao:
                continue

            # Filtro por chave de acesso
            if filtros.chave_acesso and nota.chave_acesso != filtros.chave_acesso:
                continue

            notas_filtradas.append(nota)

        logger.info(f"Encontradas {len(notas_filtradas)} notas fiscais")
        return notas_filtradas

    @staticmethod
    async def buscar_notas_params(
        params: NotaFiscalSearchParams,
        usuario_id: Optional[str] = None
    ) -> List[NotaFiscalResponse]:
        """
        Busca notas usando NotaFiscalSearchParams (busca mais flexível)

        Args:
            params: Parâmetros de busca
            usuario_id: ID do usuário

        Returns:
            Lista de notas fiscais
        """
        # TODO: Substituir por consulta real ao banco de dados
        logger.info(f"Buscando notas fiscais (params) - Usuário: {usuario_id}")

        notas = get_notas_mock()
        notas_filtradas = []

        for nota in notas:
            # Busca por termo geral
            if params.search_term:
                termo = params.search_term.lower()
                if not (
                    termo in nota.numero_nf.lower() or
                    termo in (nota.nome_emitente or "").lower() or
                    termo in (nota.cnpj_emitente or "").lower() or
                    (nota.chave_acesso and termo in nota.chave_acesso.lower())
                ):
                    continue

            # Filtro por tipo
            if params.tipo_nf and params.tipo_nf != "TODAS" and nota.tipo_nf != params.tipo_nf:
                continue

            # Filtro por situação
            if params.situacao and nota.situacao != params.situacao:
                continue

            # Filtro por CNPJ
            if params.cnpj_emitente and nota.cnpj_emitente != params.cnpj_emitente:
                continue

            # Filtro por período
            if params.data_inicio or params.data_fim:
                data_nota = nota.data_emissao.date() if isinstance(nota.data_emissao, datetime) else nota.data_emissao

                if params.data_inicio:
                    data_inicio = params.data_inicio.date() if isinstance(params.data_inicio, datetime) else params.data_inicio
                    if data_nota < data_inicio:
                        continue

                if params.data_fim:
                    data_fim = params.data_fim.date() if isinstance(params.data_fim, datetime) else params.data_fim
                    if data_nota > data_fim:
                        continue

            notas_filtradas.append(nota)

        # Paginação
        start = params.skip
        end = start + params.limit
        notas_paginadas = notas_filtradas[start:end]

        logger.info(f"Retornando {len(notas_paginadas)} de {len(notas_filtradas)} notas")
        return notas_paginadas

    @staticmethod
    async def obter_detalhes_nota(chave: str) -> NotaFiscalDetalhada:
        """
        Obtém detalhes completos de uma nota fiscal pela chave de acesso

        Args:
            chave: Chave de acesso (44 dígitos)

        Returns:
            Detalhes completos da nota fiscal

        Raises:
            HTTPException 404: Nota não encontrada
            HTTPException 422: Chave inválida
        """
        # Validar chave
        await BuscaNotaFiscalService.validar_chave_acesso(chave)

        # TODO: Substituir por consulta real ao banco/SEFAZ
        logger.info(f"Buscando detalhes da nota: {chave}")

        notas = get_notas_mock()
        nota = next((n for n in notas if n.chave_acesso == chave), None)

        if not nota:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nota fiscal com chave {chave} não encontrada"
            )

        # Converter para NotaFiscalDetalhada (adicionar impostos mock)
        nota_detalhada = NotaFiscalDetalhada(
            **nota.model_dump(),
            valor_icms=nota.valor_total * Decimal("0.12") if nota.valor_total else None,
            valor_ipi=nota.valor_total * Decimal("0.03") if nota.valor_total else None,
            valor_pis=nota.valor_total * Decimal("0.0165") if nota.valor_total else None,
            valor_cofins=nota.valor_total * Decimal("0.076") if nota.valor_total else None,
            motivo_cancelamento="Cancelamento a pedido do cliente" if nota.situacao == "cancelada" else None,
            tags=["venda", "produto"] if nota.valor_produtos else ["servico"]
        )

        return nota_detalhada

    @staticmethod
    async def baixar_xml(chave: str) -> bytes:
        """
        Baixa XML da nota fiscal

        Args:
            chave: Chave de acesso

        Returns:
            Conteúdo do XML em bytes

        Raises:
            HTTPException 404: Nota/XML não encontrado
            HTTPException 422: Chave inválida
        """
        # Validar chave
        await BuscaNotaFiscalService.validar_chave_acesso(chave)

        # TODO: Substituir por download real do XML do Supabase Storage ou SEFAZ
        logger.warning(f"Download de XML ainda não implementado: {chave}")

        # Verificar se nota existe
        nota = await BuscaNotaFiscalService.obter_detalhes_nota(chave)

        # Gerar XML mockado (apenas para demonstração)
        info_chave = extrair_info_chave_nfe(chave)

        xml_mock = f"""<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe Id="NFe{chave}">
        <ide>
            <cUF>{info_chave['uf']}</cUF>
            <cNF>{info_chave['codigo_numerico']}</cNF>
            <natOp>Venda de Mercadorias</natOp>
            <mod>{info_chave['modelo']}</mod>
            <serie>{info_chave['serie']}</serie>
            <nNF>{info_chave['numero']}</nNF>
            <dhEmi>{nota.data_emissao.isoformat()}</dhEmi>
        </ide>
        <emit>
            <CNPJ>{info_chave['cnpj_emitente'].replace('.', '').replace('/', '').replace('-', '')}</CNPJ>
            <xNome>{nota.nome_emitente}</xNome>
        </emit>
        <total>
            <ICMSTot>
                <vNF>{nota.valor_total}</vNF>
            </ICMSTot>
        </total>
    </infNFe>
</NFe>"""

        return xml_mock.encode('utf-8')


# Instância singleton do serviço
busca_nf_service = BuscaNotaFiscalService()
