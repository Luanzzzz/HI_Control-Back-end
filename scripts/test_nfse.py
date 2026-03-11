"""
Script de teste para verificar configuração NFS-e.

Uso:
    python scripts/test_nfse.py <empresa_id>

Este script verifica:
1. Se a empresa existe e tem municipio_codigo configurado
2. Se há credenciais NFS-e cadastradas
3. Testa conexão com a API municipal
4. Tenta buscar notas (opcional)
"""
import sys
import asyncio
from datetime import date, timedelta
from app.db.supabase_client import get_supabase_admin
from app.services.nfse.nfse_service import nfse_service


async def testar_nfse(empresa_id: str, buscar_notas: bool = False):
    """
    Testa configuração e busca de NFS-e para uma empresa.
    """
    db = get_supabase_admin()

    print(f"\n{'='*60}")
    print(f"TESTE DE CONFIGURAÇÃO NFS-e")
    print(f"{'='*60}\n")
    print(f"Empresa ID: {empresa_id}\n")

    # 1. Verificar se empresa existe
    print("1️⃣ Verificando empresa...")
    try:
        empresa_result = db.table("empresas")\
            .select("id, cnpj, razao_social, municipio_codigo, municipio_nome, cidade, estado")\
            .eq("id", empresa_id)\
            .single()\
            .execute()

        if not empresa_result.data:
            print("❌ Empresa não encontrada!")
            return False

        empresa = empresa_result.data
        print(f"✅ Empresa encontrada: {empresa.get('razao_social')}")
        print(f"   CNPJ: {empresa.get('cnpj')}")
        print(f"   Cidade: {empresa.get('cidade', 'N/A')}")
        print(f"   Estado: {empresa.get('estado', 'N/A')}")

        municipio_codigo = empresa.get("municipio_codigo")
        if not municipio_codigo:
            print("\n⚠️  ATENÇÃO: Empresa não tem 'municipio_codigo' configurado!")
            print("   Você precisa adicionar o código IBGE do município.")
            print("   Exemplos:")
            print("   - Belo Horizonte/MG: 3106200")
            print("   - São Paulo/SP: 3550308")
            print("\n   Execute no Supabase SQL Editor:")
            print(f"   UPDATE empresas SET municipio_codigo = '3106200' WHERE id = '{empresa_id}';")
            return False

        print(f"   Código IBGE: {municipio_codigo}")
        print(f"   Município: {empresa.get('municipio_nome', 'N/A')}")

    except Exception as e:
        print(f"❌ Erro ao buscar empresa: {e}")
        return False

    # 2. Verificar credenciais NFS-e
    print("\n2️⃣ Verificando credenciais NFS-e...")
    try:
        cred_result = db.table("credenciais_nfse")\
            .select("id, municipio_codigo, usuario, ativo, created_at")\
            .eq("empresa_id", empresa_id)\
            .eq("ativo", True)\
            .execute()

        if not cred_result.data:
            print("❌ Nenhuma credencial NFS-e configurada!")
            print("\n   Você precisa cadastrar credenciais NFS-e.")
            print("   Use o endpoint:")
            print(f"   POST /api/v1/nfse/empresas/{empresa_id}/credenciais")
            print("\n   Ou execute no Supabase SQL Editor:")
            print(f"   INSERT INTO credenciais_nfse (empresa_id, municipio_codigo, usuario, senha, ativo)")
            print(f"   VALUES ('{empresa_id}', '{municipio_codigo}', 'seu_usuario', 'sua_senha', true);")
            return False

        credenciais = cred_result.data
        print(f"✅ {len(credenciais)} credencial(is) encontrada(s):")
        for cred in credenciais:
            print(f"   - Município: {cred.get('municipio_codigo')}")
            print(f"     Usuário: {cred.get('usuario')}")
            print(f"     Ativo: {cred.get('ativo')}")

    except Exception as e:
        print(f"❌ Erro ao buscar credenciais: {e}")
        return False

    # 3. Testar conexão (se buscar_notas = False)
    if not buscar_notas:
        print("\n3️⃣ Testando conexão com API municipal...")
        try:
            # Buscar credenciais para o município
            cred_municipio = None
            for cred in cred_result.data:
                if cred.get("municipio_codigo") == municipio_codigo:
                    cred_municipio = cred
                    break

            if not cred_municipio:
                print(f"⚠️  Nenhuma credencial específica para município {municipio_codigo}")
                print("   Usando primeira credencial disponível...")
                cred_municipio = credenciais[0]

            # Obter senha completa
            cred_full = db.table("credenciais_nfse")\
                .select("*")\
                .eq("id", cred_municipio["id"])\
                .single()\
                .execute()

            if not cred_full.data:
                print("❌ Erro ao obter credenciais completas")
                return False

            cred_data = cred_full.data
            credentials = {
                "usuario": cred_data.get("usuario"),
                "senha": cred_data.get("senha"),
                "token": cred_data.get("token"),
                "cnpj": cred_data.get("cnpj") or empresa.get("cnpj"),
            }

            # Selecionar adapter
            adapter = nfse_service.obter_adapter(municipio_codigo, credentials)
            print(f"   Sistema: {adapter.SISTEMA_NOME}")

            # Tentar autenticar
            try:
                token = await adapter.autenticar()
                print(f"✅ Autenticação bem-sucedida!")
                print(f"   Token obtido: {token[:20]}..." if token else "   Token: N/A")
            except Exception as auth_err:
                print(f"❌ Falha na autenticação: {auth_err}")
                print("\n   Verifique:")
                print("   - Usuário e senha estão corretos?")
                print("   - A API municipal está acessível?")
                print("   - As credenciais são válidas para este município?")
                return False

        except Exception as e:
            print(f"❌ Erro ao testar conexão: {e}")
            return False

    # 4. Buscar notas (se solicitado)
    if buscar_notas:
        print("\n4️⃣ Buscando NFS-e...")
        try:
            data_fim = date.today()
            data_inicio = data_fim - timedelta(days=30)

            print(f"   Período: {data_inicio} a {data_fim}")

            resultado = await nfse_service.buscar_notas_empresa(
                empresa_id=empresa_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )

            if resultado.get("success"):
                quantidade = resultado.get("quantidade", 0)
                print(f"✅ Busca concluída!")
                print(f"   Notas encontradas: {quantidade}")
                print(f"   Sistema usado: {resultado.get('sistema', 'N/A')}")
                print(f"   Tempo: {resultado.get('tempo_ms', 0)}ms")

                if quantidade > 0:
                    print(f"\n   Primeiras notas:")
                    notas = resultado.get("notas", [])[:3]
                    for nota in notas:
                        print(f"   - Nº {nota.get('numero_nf')} | "
                              f"Valor: R$ {nota.get('valor_total', 0):.2f} | "
                              f"Data: {nota.get('data_emissao')}")
            else:
                print(f"⚠️  Busca não teve sucesso")
                print(f"   Mensagem: {resultado.get('mensagem', 'N/A')}")

        except Exception as e:
            print(f"❌ Erro ao buscar notas: {e}")
            import traceback
            traceback.print_exc()
            return False

    print(f"\n{'='*60}")
    print("✅ TESTE CONCLUÍDO")
    print(f"{'='*60}\n")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/test_nfse.py <empresa_id> [--buscar-notas]")
        print("\nExemplo:")
        print("  python scripts/test_nfse.py 123e4567-e89b-12d3-a456-426614174000")
        print("  python scripts/test_nfse.py 123e4567-e89b-12d3-a456-426614174000 --buscar-notas")
        sys.exit(1)

    empresa_id = sys.argv[1]
    buscar_notas = "--buscar-notas" in sys.argv

    asyncio.run(testar_nfse(empresa_id, buscar_notas))
