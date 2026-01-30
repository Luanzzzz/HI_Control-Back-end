"""
Script de teste para validar busca de NFes (DistribuicaoDFe).

Testa a integração completa sem necessidade de certificado digital.

Execução:
    cd backend
    venv/Scripts/python scripts/test_busca_nfe.py
"""

import sys
from pathlib import Path

# Adicionar backend ao path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

import os
os.environ["USE_MOCK_SEFAZ"] = "true"  # Forçar uso de mock

print("=" * 70)
print("TESTE DE BUSCA DE NFEs - DistribuicaoDFe")
print("=" * 70)
print()

# ============================================
# 1. Testar Mock Client
# ============================================
print("[1/4] Testando Mock Client...")

try:
    from app.adapters.mock_sefaz_client import (
        MockDistribuicaoDFeClient,
        extrair_resumos_mock
    )
    
    client = MockDistribuicaoDFeClient()
    xml = client.consultar(cnpj="12345678000190", nsu_inicial=0)
    resumos = extrair_resumos_mock(xml)
    
    print(f"✅ Mock retornou {len(resumos)} notas")
    for r in resumos:
        print(f"   - Chave: {r['chave'][:15]}... | Valor: R$ {r['valor']}")
except Exception as e:
    print(f"❌ Erro no mock client: {e}")
    import traceback
    traceback.print_exc()

print()

# ============================================
# 2. Testar Parsing de XML
# ============================================
print("[2/4] Testando funções de parsing XML...")

try:
    from app.utils.xml_utils import (
        extrair_cnpj_emitente,
        extrair_valor_total,
        extrair_nsu,
        extrair_chave_acesso,
    )
    
    # Usar primeiro resumo do mock
    if resumos:
        primeiro_xml = f'''<resNFe>
            <chNFe>{resumos[0]['chave']}</chNFe>
            <CNPJ>{resumos[0]['cnpj']}</CNPJ>
            <vNF>{resumos[0]['valor']}</vNF>
            <NSU>{resumos[0]['nsu']}</NSU>
        </resNFe>'''
        
        chave = extrair_chave_acesso(primeiro_xml)
        cnpj = extrair_cnpj_emitente(primeiro_xml)
        valor = extrair_valor_total(primeiro_xml)
        nsu = extrair_nsu(primeiro_xml)
        
        print(f"✅ Chave extraída: {chave[:15]}...")
        print(f"✅ CNPJ extraído: {cnpj}")
        print(f"✅ Valor extraído: R$ {valor}")
        print(f"✅ NSU extraído: {nsu}")
    else:
        print("⚠️ Sem resumos para testar parsing")
        
except Exception as e:
    print(f"❌ Erro ao testar parsing: {e}")
    import traceback
    traceback.print_exc()

print()

# ============================================
# 3. Testar Modelos Pydantic
# ============================================
print("[3/4] Testando modelos Pydantic...")

try:
    from app.models.nfe_busca import (
        ConsultaDistribuicaoRequest,
        NFeBuscadaMetadata,
        DistribuicaoResponseModel,
        mapear_situacao_nfe,
    )
    from datetime import datetime
    from decimal import Decimal
    
    # Criar request
    request = ConsultaDistribuicaoRequest(
        cnpj="12345678000190",
        nsu_inicial=0,
        max_notas=50
    )
    print(f"✅ Request criado: CNPJ={request.cnpj}, NSU={request.nsu_inicial}")
    
    # Criar metadata de nota
    nota = NFeBuscadaMetadata(
        chave_acesso="35260112345678000190550010000001231123456789",
        nsu=123456,
        data_emissao=datetime.now(),
        tipo_operacao="1",
        valor_total=Decimal("1500.00"),
        cnpj_emitente="12345678000190",
        nome_emitente="EMPRESA TESTE",
        situacao="autorizada",
        situacao_codigo="1",
    )
    print(f"✅ Nota criada: {nota.chave_acesso[:15]}... | Valor: R$ {nota.valor_total}")
    
    # Mapear situação
    situacao = mapear_situacao_nfe("1")
    print(f"✅ Situação mapeada: {situacao}")

except Exception as e:
    print(f"❌ Erro ao testar modelos: {e}")
    import traceback
    traceback.print_exc()

print()

# ============================================
# 4. Testar SefazService (Integração Completa)
# ============================================
print("[4/4] Testando buscar_notas_por_cnpj (integração completa)...")

try:
    from app.services.sefaz_service import sefaz_service
    
    response = sefaz_service.buscar_notas_por_cnpj(
        cnpj="12345678000190",
        empresa_id="test-empresa-123",
        nsu_inicial=0
    )
    
    print(f"✅ Busca concluída!")
    print(f"   - Status: {response.status_codigo} - {response.motivo}")
    print(f"   - Notas encontradas: {response.total_notas}")
    print(f"   - Último NSU: {response.ultimo_nsu}")
    print(f"   - Tem mais notas: {response.tem_mais_notas}")
    print()
    
    if response.notas_encontradas:
        print("   Detalhes das notas:")
        for i, nota in enumerate(response.notas_encontradas, 1):
            print(f"   {i}. Chave: {nota.chave_acesso[:20]}...")
            print(f"      Emitente: {nota.nome_emitente}")
            print(f"      Valor: R$ {nota.valor_total}")
            print(f"      Situação: {nota.situacao}")
            print()
    
except Exception as e:
    print(f"❌ Erro ao testar sefaz_service: {e}")
    import traceback
    traceback.print_exc()

print("=" * 70)
print("✅ TESTE COMPLETO!")
print("=" * 70)
print()
print("PRÓXIMOS PASSOS:")
print("1. Testar endpoint REST: POST http://localhost:8000/api/v1/nfe/buscar")
print("2. Implementar integração com banco de dados")
print("3. Adicionar validação de plano de usuário")
print("4. Criar interface TypeScript no frontend")
print("=" * 70)
