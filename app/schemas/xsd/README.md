# Schemas XSD Oficiais da NF-e

Este diretório contém os schemas XSD oficiais para validação de XMLs fiscais.

## 📂 Estrutura de Arquivos

### NF-e versão 4.00 (OBRIGATÓRIO)
- **`nfe_v4.00.xsd`** - Schema principal da NF-e 4.0
- **`tiposBasico_v4.00.xsd`** - Tipos básicos utilizados pela NF-e
- **`xmldsig-core-schema_v1.01.xsd`** - Schema de assinatura digital XML

### Outros documentos fiscais (OPCIONAL)
- **`consReciNFe_v4.00.xsd`** - Schema de consulta de recibo
- **`consSitNFe_v4.00.xsd`** - Schema de consulta de situação
- **`evCancNFe_v1.00.xsd`** - Schema de evento de cancelamento
- **`inutNFe_v4.00.xsd`** - Schema de inutilização

## 📥 Fonte Oficial

Os schemas XSD oficiais devem ser baixados do Portal Nacional da NF-e:

**Link oficial:**
https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=

### Passos para Download Manual

1. Acesse o Portal Nacional NF-e
2. Vá em "Documentos" → "Schemas XML"
3. Baixe o pacote "Schemas XML da NF-e versão 4.0"
4. Extraia os seguintes arquivos para este diretório:
   - `nfe_v4.00.xsd`
   - `tiposBasico_v4.00.xsd`
   - `xmldsig-core-schema_v1.01.xsd`

### Download via wget (Linux/Mac)

```bash
cd backend/app/schemas/xsd/

# Baixar pacote completo (substitua pela URL correta)
wget https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=vdmSFa8473Y= -O schemas_nfe_v4.00.zip

# Extrair apenas os arquivos necessários
unzip schemas_nfe_v4.00.zip "nfe_v4.00.xsd" "tiposBasico_v4.00.xsd" "xmldsig-core-schema_v1.01.xsd"

# Limpar arquivo zip
rm schemas_nfe_v4.00.zip
```

## ⚠️ IMPORTANTE

- **NÃO** versione schemas XSD no Git se houver restrição de licença
- **SEMPRE** use schemas oficiais (não modificados)
- Verifique periodicamente por atualizações de versão

## 🔍 Validação

Para testar se os schemas estão corretos:

```bash
# Executar teste de validação XSD
pytest backend/tests/unit/test_xsd_validation.py -v
```

Se o teste `test_schemas_xsd_existem` falhar, os arquivos XSD não estão no diretório.

## 📖 Referências

- [Portal Nacional NF-e](https://www.nfe.fazenda.gov.br/portal/principal.aspx)
- [Manual de Orientação do Contribuinte v7.0](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=)
- [Esquemas XML v4.0](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=)

---

**Última atualização:** 2026-03-12
**Versão dos schemas:** 4.00
**Responsável:** Claude Sonnet 4.5
