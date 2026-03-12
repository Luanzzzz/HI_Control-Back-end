# ⚠️ ATENÇÃO: Schemas Incorretos Detectados

## Problema Atual

Você baixou os schemas do **NFGas** (Nota Fiscal de Gás Natural), mas o Hi-Control precisa dos schemas da **NF-e** (Nota Fiscal Eletrônica modelo 55).

---

## ✅ Como Baixar os Schemas CORRETOS

### Opção 1: Download Manual (RECOMENDADO)

#### Passo 1: Acessar Portal NF-e
1. Abra seu navegador
2. Acesse: https://www.nfe.fazenda.gov.br/portal/principal.aspx

#### Passo 2: Navegar até Schemas
1. No menu esquerdo, clique em **"Documentos"**
2. Clique em **"Schemas XML"**
3. Ou acesse diretamente: https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=

#### Passo 3: Baixar Pacote Correto
Procure pelo link:
- **"Pacote de Liberação No. 18 (Schemas XML)"**
- Ou **"Schemas XML da NF-e - Versão 4.00"**

O arquivo será algo como: `PL_008i2_00.zip` ou similar.

#### Passo 4: Extrair Arquivos Necessários
Após baixar o ZIP, extraia **APENAS** os seguintes arquivos:

```
PL_008i2_00/
├── nfe_v4.00.xsd                  ⬅️ PRINCIPAL (obrigatório)
├── tiposBasico_v4.00.xsd           ⬅️ Tipos básicos (obrigatório)
├── consSitNFe_v4.00.xsd            ⬅️ Consulta (recomendado)
├── evCancNFe_v1.00.xsd             ⬅️ Cancelamento (recomendado)
├── inutNFe_v4.00.xsd               ⬅️ Inutilização (recomendado)
└── xmldsig-core-schema_v1.01.xsd   ⬅️ Assinatura digital (obrigatório)
```

#### Passo 5: Mover para Diretório Correto
Copie os arquivos acima para:
```
D:\Projetos\Hi_Control\backend\app\schemas\xsd\
```

**NÃO** crie subdiretórios. Os arquivos devem ficar diretamente em `xsd/`.

---

### Opção 2: Download Direto (se link disponível)

Se o Portal NF-e disponibilizar link direto, use:

```bash
# Windows PowerShell
cd D:\Projetos\Hi_Control\backend\app\schemas\xsd\

# Baixar pacote (ajuste a URL conforme Portal NF-e)
Invoke-WebRequest -Uri "https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=XXXXX" -OutFile "schemas_nfe_v4.zip"

# Extrair
Expand-Archive -Path "schemas_nfe_v4.zip" -DestinationPath "temp"

# Mover arquivos necessários
Move-Item "temp/nfe_v4.00.xsd" .
Move-Item "temp/tiposBasico_v4.00.xsd" .
Move-Item "temp/xmldsig-core-schema_v1.01.xsd" .

# Limpar
Remove-Item "temp" -Recurse -Force
Remove-Item "schemas_nfe_v4.zip"
```

---

## 🔍 Como Verificar se Baixou Correto

Após extrair, execute:

```bash
# Verificar se arquivos corretos estão presentes
ls D:\Projetos\Hi_Control\backend\app\schemas\xsd\nfe_v4.00.xsd
ls D:\Projetos\Hi_Control\backend\app\schemas\xsd\tiposBasico_v4.00.xsd
ls D:\Projetos\Hi_Control\backend\app\schemas\xsd\xmldsig-core-schema_v1.01.xsd
```

Se os 3 comandos acima retornarem os arquivos (sem erro), está correto!

---

## ⚠️ Arquivos ERRADOS que Você Baixou

Você baixou schemas do **NFGas** (Nota Fiscal de Gás):
- `nfgas_v1.00.xsd` ❌
- `nfgasTiposBasico_v1.00.xsd` ❌

Esses NÃO são compatíveis com NF-e modelo 55.

---

## 🧹 Limpeza (Opcional)

Para remover os schemas incorretos:

```bash
# Remover diretório NFGas
Remove-Item "D:\Projetos\Hi_Control\backend\app\schemas\xsd\PL_NFGas_1.00d" -Recurse -Force
```

---

## ✅ Próximos Passos

Após baixar os schemas corretos:

1. **Verificar instalação:**
   ```bash
   cd D:\Projetos\Hi_Control\backend
   python -m pytest tests/unit/test_xsd_validation.py::test_schemas_xsd_existem -v
   ```

   Deve retornar: **PASSED** (não SKIPPED)

2. **Executar todos os testes:**
   ```bash
   pytest tests/unit/test_xsd_validation.py -v
   ```

   Esperado: **9 passed, 0 skipped**

3. **Fazer commit:**
   ```bash
   git add backend/app/schemas/xsd/
   git commit -m "feat: Adicionar schemas XSD oficiais da NF-e v4.00"
   ```

---

## 📞 Precisa de Ajuda?

Se tiver dificuldade para encontrar o link correto no Portal NF-e, me avise que eu crio um script alternativo para ajudar.

**Última atualização:** 2026-03-12
