"""
Serviço de gerenciamento de Notas Fiscais
"""
from typing import List
from supabase import Client
from app.models.nota_fiscal import NotaFiscalResponse, NotaFiscalSearchParams


async def buscar_notas_fiscais(
    db: Client,
    params: NotaFiscalSearchParams,
    usuario: dict
) -> List[NotaFiscalResponse]:
    """
    Busca notas fiscais com filtros

    Args:
        db: Cliente Supabase
        params: Parâmetros de busca
        usuario: Dados do usuário autenticado

    Returns:
        Lista de notas fiscais encontradas
    """
    try:
        # Buscar empresas do usuário
        empresas_response = db.table("empresas")\
            .select("id")\
            .eq("usuario_id", usuario["id"])\
            .eq("ativa", True)\
            .execute()

        if not empresas_response.data:
            return []

        empresa_ids = [emp["id"] for emp in empresas_response.data]

        # Construir query base
        query = db.table("notas_fiscais").select("*")

        # Filtrar por empresas do usuário
        query = query.in_("empresa_id", empresa_ids)

        # Aplicar filtro de busca geral (OR conditions)
        if params.search_term:
            # Supabase postgrest usa 'or' para múltiplas condições
            # Precisamos fazer múltiplas queries ou usar textSearch
            # Por simplicidade, vamos buscar em cada campo separadamente
            # e combinar os resultados (não é ideal, mas funciona)
            search_queries = []

            # Buscar em cada campo
            for campo in ["numero_nf", "chave_acesso", "nome_emitente", "cnpj_emitente"]:
                q = db.table("notas_fiscais").select("*")\
                    .in_("empresa_id", empresa_ids)\
                    .ilike(campo, f"%{params.search_term}%")

                # Aplicar outros filtros também
                if params.tipo_nf and params.tipo_nf != "TODAS":
                    q = q.eq("tipo_nf", params.tipo_nf)
                if params.situacao:
                    q.eq("situacao", params.situacao)
                if params.cnpj_emitente:
                    q = q.eq("cnpj_emitente", params.cnpj_emitente)
                if params.data_inicio:
                    q = q.gte("data_emissao", params.data_inicio.isoformat())
                if params.data_fim:
                    q = q.lte("data_emissao", params.data_fim.isoformat())

                search_queries.append(q)

            # Executar todas as queries e combinar resultados
            all_notas = []
            seen_ids = set()

            for q in search_queries:
                response = q.execute()
                for nota in response.data:
                    if nota["id"] not in seen_ids:
                        all_notas.append(nota)
                        seen_ids.add(nota["id"])

            # Ordenar por data de emissão (mais recentes primeiro)
            all_notas.sort(key=lambda x: x["data_emissao"], reverse=True)

            # Aplicar paginação manual
            paginated_notas = all_notas[params.skip:params.skip + params.limit]

            return [NotaFiscalResponse(**nota) for nota in paginated_notas]

        # Se não há search_term, usar query normal
        if params.tipo_nf and params.tipo_nf != "TODAS":
            query = query.eq("tipo_nf", params.tipo_nf)

        if params.situacao:
            query = query.eq("situacao", params.situacao)

        if params.cnpj_emitente:
            query = query.eq("cnpj_emitente", params.cnpj_emitente)

        if params.data_inicio:
            query = query.gte("data_emissao", params.data_inicio.isoformat())

        if params.data_fim:
            query = query.lte("data_emissao", params.data_fim.isoformat())

        # Ordenação por data de emissão (mais recentes primeiro)
        query = query.order("data_emissao", desc=True)

        # Paginação
        query = query.range(params.skip, params.skip + params.limit - 1)

        # Executar query
        response = query.execute()

        # Converter para schema de resposta
        return [NotaFiscalResponse(**nota) for nota in response.data]

    except Exception as e:
        print(f"Erro ao buscar notas fiscais: {e}")
        return []
