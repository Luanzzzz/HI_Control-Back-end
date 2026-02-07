"""
Service Layer para busca de Notas Fiscais - VERSAO REAL

Este servico consulta o BANCO DE DADOS local para buscar notas fiscais.
ZERO MOCK - Apenas dados reais.

Para obter notas:
1. Importar XML via endpoint /importar-xml
2. Consultar SEFAZ por chave via endpoint /consultar-chave
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

logger = logging.getLogger(__name__)


class BuscaNotaFiscalService:
    """
    Servico de busca de Notas Fiscais - VERSAO REAL

    Consulta o banco de dados local (Supabase) para buscar notas.
    NAO usa dados mockados.
    """

    @staticmethod
    async def validar_chave_acesso(chave: str) -> bool:
        """
        Valida chave de acesso de Nota Fiscal

        Args:
            chave: Chave de acesso (44 digitos)

        Returns:
            True se chave valida

        Raises:
            HTTPException 422: Se chave invalida
        """
        if not validar_chave_nfe(chave):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Chave de acesso invalida. Deve conter 44 digitos numericos validos."
            )
        return True

    @staticmethod
    async def buscar_notas(
        filtros: BuscaNotaFilter,
        empresa_id: str,
        usuario_id: Optional[str] = None
    ) -> List[NotaFiscalResponse]:
        """
        Busca notas fiscais no BANCO DE DADOS com filtros

        Args:
            filtros: Filtros de busca
            empresa_id: ID da empresa (obrigatorio)
            usuario_id: ID do usuario fazendo a busca (para auditoria)

        Returns:
            Lista de notas fiscais encontradas no banco

        Raises:
            HTTPException 400: Parametros invalidos
            HTTPException 422: Validacao fiscal falhou
        """
        # Validar periodo de busca
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
                detail="CNPJ do emitente invalido"
            )

        # Validar chave de acesso se fornecida
        if filtros.chave_acesso:
            await BuscaNotaFiscalService.validar_chave_acesso(filtros.chave_acesso)

        logger.info(f"Buscando notas no banco - Empresa: {empresa_id}, Usuario: {usuario_id}")

        try:
            from app.db.supabase_client import supabase_admin

            # Query base
            query = supabase_admin.table("notas_fiscais")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .order("data_emissao", desc=True)

            # Aplicar filtros
            if filtros.tipo_nf:
                query = query.eq("tipo_nf", filtros.tipo_nf)

            if filtros.situacao:
                query = query.eq("situacao", filtros.situacao)

            if filtros.cnpj_emitente:
                query = query.eq("cnpj_emitente", filtros.cnpj_emitente)

            if filtros.numero_nf:
                query = query.eq("numero_nf", filtros.numero_nf)

            if filtros.serie:
                query = query.eq("serie", filtros.serie)

            if filtros.chave_acesso:
                query = query.eq("chave_acesso", filtros.chave_acesso)

            if filtros.data_inicio:
                data_inicio_str = filtros.data_inicio.isoformat() if isinstance(filtros.data_inicio, date) else str(filtros.data_inicio)
                query = query.gte("data_emissao", data_inicio_str)

            if filtros.data_fim:
                data_fim_str = filtros.data_fim.isoformat() if isinstance(filtros.data_fim, date) else str(filtros.data_fim)
                query = query.lte("data_emissao", data_fim_str)

            # Executar query
            result = query.execute()

            if not result.data:
                logger.info(f"Nenhuma nota encontrada para empresa {empresa_id}")
                return []

            # Converter para NotaFiscalResponse
            notas = []
            for row in result.data:
                try:
                    nota = BuscaNotaFiscalService._row_to_response(row)
                    notas.append(nota)
                except Exception as e:
                    logger.error(f"Erro ao converter nota: {e}")
                    continue

            logger.info(f"Encontradas {len(notas)} notas fiscais no banco")
            return notas

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao buscar notas no banco: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao consultar banco de dados: {str(e)}"
            )

    @staticmethod
    async def buscar_notas_params(
        params: NotaFiscalSearchParams,
        empresa_id: str,
        usuario_id: Optional[str] = None
    ) -> List[NotaFiscalResponse]:
        """
        Busca notas usando NotaFiscalSearchParams (busca mais flexivel)

        Args:
            params: Parametros de busca
            empresa_id: ID da empresa
            usuario_id: ID do usuario

        Returns:
            Lista de notas fiscais
        """
        logger.info(f"Buscando notas (params) - Empresa: {empresa_id}, Usuario: {usuario_id}")

        try:
            from app.db.supabase_client import supabase_admin

            # Query base
            query = supabase_admin.table("notas_fiscais")\
                .select("*")\
                .eq("empresa_id", empresa_id)\
                .order("data_emissao", desc=True)

            # Filtro por tipo
            if params.tipo_nf and params.tipo_nf != "TODAS":
                query = query.eq("tipo_nf", params.tipo_nf)

            # Filtro por situacao
            if params.situacao:
                query = query.eq("situacao", params.situacao)

            # Filtro por CNPJ
            if params.cnpj_emitente:
                query = query.eq("cnpj_emitente", params.cnpj_emitente)

            # Filtro por periodo
            if params.data_inicio:
                data_inicio_str = params.data_inicio.isoformat() if isinstance(params.data_inicio, (date, datetime)) else str(params.data_inicio)
                query = query.gte("data_emissao", data_inicio_str)

            if params.data_fim:
                data_fim_str = params.data_fim.isoformat() if isinstance(params.data_fim, (date, datetime)) else str(params.data_fim)
                query = query.lte("data_emissao", data_fim_str)

            # Busca por termo geral (usar or_ do Supabase)
            if params.search_term:
                termo = params.search_term
                query = query.or_(
                    f"numero_nf.ilike.%{termo}%,"
                    f"nome_emitente.ilike.%{termo}%,"
                    f"cnpj_emitente.ilike.%{termo}%,"
                    f"chave_acesso.ilike.%{termo}%"
                )

            # Paginacao
            start = params.skip
            end = start + params.limit - 1
            query = query.range(start, end)

            # Executar
            result = query.execute()

            if not result.data:
                return []

            # Converter para NotaFiscalResponse
            notas = []
            for row in result.data:
                try:
                    nota = BuscaNotaFiscalService._row_to_response(row)
                    notas.append(nota)
                except Exception as e:
                    logger.error(f"Erro ao converter nota: {e}")
                    continue

            logger.info(f"Retornando {len(notas)} notas")
            return notas

        except Exception as e:
            logger.error(f"Erro ao buscar notas: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao consultar banco de dados: {str(e)}"
            )

    @staticmethod
    async def obter_detalhes_nota(chave: str, empresa_id: str) -> NotaFiscalDetalhada:
        """
        Obtem detalhes completos de uma nota fiscal pela chave de acesso

        Args:
            chave: Chave de acesso (44 digitos)
            empresa_id: ID da empresa

        Returns:
            Detalhes completos da nota fiscal

        Raises:
            HTTPException 404: Nota nao encontrada
            HTTPException 422: Chave invalida
        """
        # Validar chave
        await BuscaNotaFiscalService.validar_chave_acesso(chave)

        logger.info(f"Buscando detalhes da nota: {chave}")

        try:
            from app.db.supabase_client import supabase_admin

            result = supabase_admin.table("notas_fiscais")\
                .select("*")\
                .eq("chave_acesso", chave)\
                .eq("empresa_id", empresa_id)\
                .limit(1)\
                .execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Nota fiscal com chave {chave} nao encontrada"
                )

            row = result.data[0]

            # Converter para NotaFiscalDetalhada
            nota_detalhada = NotaFiscalDetalhada(
                id=row.get('id'),
                chave_acesso=row.get('chave_acesso', ''),
                numero_nf=row.get('numero_nf', ''),
                serie=row.get('serie', '1'),
                tipo_nf=row.get('tipo_nf', 'NFE'),
                data_emissao=row.get('data_emissao'),
                cnpj_emitente=row.get('cnpj_emitente', ''),
                nome_emitente=row.get('nome_emitente', ''),
                cnpj_destinatario=row.get('cnpj_destinatario'),
                nome_destinatario=row.get('nome_destinatario'),
                valor_total=Decimal(str(row.get('valor_total', 0))),
                valor_produtos=Decimal(str(row.get('valor_produtos', 0))) if row.get('valor_produtos') else None,
                situacao=row.get('situacao', 'autorizada'),
                valor_icms=Decimal(str(row.get('valor_icms', 0))) if row.get('valor_icms') else None,
                valor_ipi=Decimal(str(row.get('valor_ipi', 0))) if row.get('valor_ipi') else None,
                valor_pis=Decimal(str(row.get('valor_pis', 0))) if row.get('valor_pis') else None,
                valor_cofins=Decimal(str(row.get('valor_cofins', 0))) if row.get('valor_cofins') else None,
                motivo_cancelamento=row.get('motivo_cancelamento'),
                tags=row.get('tags', []),
            )

            return nota_detalhada

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao obter detalhes da nota: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao consultar banco de dados: {str(e)}"
            )

    @staticmethod
    async def baixar_xml(chave: str, empresa_id: str) -> bytes:
        """
        Baixa XML da nota fiscal

        Args:
            chave: Chave de acesso
            empresa_id: ID da empresa

        Returns:
            Conteudo do XML em bytes

        Raises:
            HTTPException 404: Nota/XML nao encontrado
            HTTPException 422: Chave invalida
        """
        # Validar chave
        await BuscaNotaFiscalService.validar_chave_acesso(chave)

        logger.info(f"Buscando XML da nota: {chave}")

        try:
            from app.db.supabase_client import supabase_admin

            # Buscar nota com XML
            result = supabase_admin.table("notas_fiscais")\
                .select("xml_resumo, xml_completo, chave_acesso, nome_emitente")\
                .eq("chave_acesso", chave)\
                .eq("empresa_id", empresa_id)\
                .limit(1)\
                .execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Nota fiscal com chave {chave} nao encontrada"
                )

            row = result.data[0]

            # Verificar se tem XML
            xml_content = row.get('xml_completo') or row.get('xml_resumo')

            if not xml_content:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"XML da nota {chave} nao disponivel. Importe o XML completo."
                )

            # Retornar XML como bytes
            if isinstance(xml_content, str):
                return xml_content.encode('utf-8')
            return xml_content

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao baixar XML: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao baixar XML: {str(e)}"
            )

    @staticmethod
    def _row_to_response(row: dict) -> NotaFiscalResponse:
        """Converte row do banco para NotaFiscalResponse"""
        return NotaFiscalResponse(
            id=row.get('id'),
            chave_acesso=row.get('chave_acesso', ''),
            numero_nf=row.get('numero_nf', ''),
            serie=row.get('serie', '1'),
            tipo_nf=row.get('tipo_nf', 'NFE'),
            data_emissao=row.get('data_emissao'),
            cnpj_emitente=row.get('cnpj_emitente', ''),
            nome_emitente=row.get('nome_emitente', ''),
            cnpj_destinatario=row.get('cnpj_destinatario'),
            nome_destinatario=row.get('nome_destinatario'),
            valor_total=Decimal(str(row.get('valor_total', 0))),
            valor_produtos=Decimal(str(row.get('valor_produtos', 0))) if row.get('valor_produtos') else None,
            situacao=row.get('situacao', 'autorizada'),
        )


# Instancia singleton do servico
busca_nf_service = BuscaNotaFiscalService()
