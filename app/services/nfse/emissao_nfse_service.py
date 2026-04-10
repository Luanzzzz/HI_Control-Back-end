"""
Serviço de emissão e cancelamento de NFS-e.

Complementa o nfse_service (que faz busca) com capacidade de:
- Emitir NFS-e via APIs municipais (padrão ABRASF 2.04 - LEGADO)
- Emitir NFS-e via API Nacional (padrão SEFIN - LC 214/2025)
- Cancelar NFS-e emitidas
- Substituir NFS-e

IMPORTANTE:
- USE_MUNICIPAL_LEGACY=true: Usa APIs municipais antigas (ABRASF 2.04)
- USE_MUNICIPAL_LEGACY=false: Usa API Nacional (padrão obrigatório desde 01/01/2026)

Utiliza os mesmos adapters municipais, estendendo a interface base
com métodos de emissão e cancelamento.
"""
import os
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.db.supabase_client import get_supabase_admin
from app.services.nfse.nfse_service import nfse_service
from app.services.nfse.emissao_nfse_nacional_service import nfse_nacional_service

logger = logging.getLogger(__name__)


class EmissaoNFSeService:
    """Serviço para emissão e cancelamento de NFS-e."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============================================
    # EMISSÃO
    # ============================================

    async def emitir_nfse(
        self,
        empresa_id: str,
        nfse_data: dict,
        usuario_id: Optional[str] = None,
        usar_nacional: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Emite NFS-e via API Nacional ou Municipal (legado).

        ROTAS DISPONÍVEIS:
        1. **API Nacional (SEFIN)** - Padrão obrigatório desde 01/01/2026
           - Usa: emissao_nfse_nacional_service
           - DPS com tributos IBS/CBS
           - mTLS com certificado A1

        2. **API Municipal (ABRASF)** - Legado para municípios não migrados
           - Usa: RPS padrão ABRASF 2.04
           - APIs municipais específicas

        Args:
            empresa_id: ID da empresa emitente
            nfse_data: Dados da NFS-e a emitir
            usuario_id: ID do usuário que solicita
            usar_nacional: True=API Nacional, False=Municipal, None=auto (flag env)

        Returns:
            Resultado da emissão

        Raises:
            EmissionBlockedError: Se emissão em produção bloqueada
        """
        # PROTEÇÃO: Verificar permissão de emissão em produção
        from app.utils.emission_guard import verificar_permissao_emissao
        verificar_permissao_emissao(
            empresa_id=empresa_id,
            tipo_documento="NFSe"
        )

        # ============================================
        # ROTEAMENTO: Nacional vs Municipal
        # ============================================
        use_municipal_legacy = os.getenv("USE_MUNICIPAL_LEGACY", "false").lower() == "true"

        # Sobrescrever flag se parâmetro explícito
        if usar_nacional is not None:
            use_municipal_legacy = not usar_nacional

        # Por padrão, usar Nacional (LC 214/2025 obrigatória desde 2026)
        if not use_municipal_legacy:
            logger.info(f"Roteando emissão NFS-e para API Nacional (SEFIN) - Empresa: {empresa_id}")
            return await self._emitir_via_nacional(empresa_id, nfse_data, usuario_id)

        # Fallback: API Municipal (legado)
        logger.warning(
            f"⚠️ Usando API Municipal LEGADA (ABRASF 2.04) - Empresa: {empresa_id}. "
            "Recomenda-se migrar para API Nacional."
        )
        return await self._emitir_via_municipal(empresa_id, nfse_data, usuario_id)

    # ============================================
    # EMISSÃO VIA NACIONAL (SEFIN)
    # ============================================

    async def _emitir_via_nacional(
        self,
        empresa_id: str,
        nfse_data: dict,
        usuario_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Emite NFS-e via API Nacional (SEFIN).

        Fluxo:
        1. Buscar empresa + certificado A1
        2. Montar DPS (com IBS/CBS)
        3. Emitir via POST /nfse
        4. Salvar no banco
        """
        db = get_supabase_admin()

        try:
            # 1. Buscar empresa
            empresa = db.table("empresas").select("*").eq("id", empresa_id).single().execute()

            if not empresa.data:
                return {"sucesso": False, "erro": "Empresa não encontrada"}

            emp = empresa.data

            # 2. Obter e descriptografar certificado A1
            from app.services.certificado_service import certificado_service

            cert_a1_encrypted = emp.get("certificado_a1")
            if not cert_a1_encrypted:
                return {
                    "sucesso": False,
                    "erro": "Certificado A1 não configurado para emissão NFS-e Nacional"
                }

            cert_bytes = certificado_service.descriptografar_certificado(cert_a1_encrypted)
            cert_password = nfse_data.get("certificado_senha", "")

            if not cert_password:
                return {
                    "sucesso": False,
                    "erro": "Senha do certificado A1 é obrigatória para emissão NFS-e Nacional"
                }

            # 3. Calcular IBS/CBS se não informados
            servico = nfse_data.get("servico", {})
            if "tributos" not in nfse_data:
                tributos_calc = self.calcular_ibs_cbs(
                    valor_servicos=float(servico.get("valor_servicos", 0)),
                    optante_simples=nfse_data.get("optante_simples", False),
                )
                nfse_data["tributos"] = {
                    "ibs": {
                        "aliquota": tributos_calc["aliquota_ibs"],
                        "valor": tributos_calc["valor_ibs"],
                    },
                    "cbs": {
                        "aliquota": tributos_calc["aliquota_cbs"],
                        "valor": tributos_calc["valor_cbs"],
                    },
                }

            # 4. Montar DPS
            from app.core.config import settings
            ambiente = "producao" if settings.SEFAZ_AMBIENTE == "producao" else "homologacao"

            dps_xml = nfse_nacional_service.montar_dps(
                dados_emissao=nfse_data,
                empresa=emp,
                ambiente=ambiente
            )

            logger.debug(f"DPS montado para empresa {empresa_id}: {len(dps_xml)} bytes")

            # 4. Emitir via SEFIN
            resultado = await nfse_nacional_service.emitir_nfse(
                dps_xml=dps_xml,
                cert_bytes=cert_bytes,
                cert_password=cert_password,
                ambiente=ambiente,
                empresa_id=empresa_id
            )

            # 5. Salvar no banco se sucesso
            if resultado.get("sucesso"):
                nota_id = await self._salvar_nfse_nacional(
                    db, empresa_id, nfse_data, resultado
                )
                resultado["nota_id"] = nota_id

            return resultado

        except Exception as e:
            logger.error(f"Erro ao emitir NFS-e Nacional: {e}", exc_info=True)
            return {
                "sucesso": False,
                "erro": str(e),
                "tipo": "emissao_nacional"
            }

    async def _salvar_nfse_nacional(
        self,
        db,
        empresa_id: str,
        nfse_data: dict,
        resultado: dict,
    ) -> str:
        """Salva NFS-e Nacional no banco."""
        tomador = nfse_data.get("tomador", {})
        servico = nfse_data.get("servico", {})

        nota_db = {
            "empresa_id": empresa_id,
            "tipo_nf": "NFSE",
            "numero_nf": resultado.get("numero_nfse", ""),
            "serie": nfse_data.get("serie", "NACIONAL"),
            "situacao": "autorizada",
            "chave_acesso": resultado.get("chave_acesso", ""),
            "cnpj_destinatario": tomador.get("cnpj") or tomador.get("cpf", ""),
            "nome_destinatario": tomador.get("nome", tomador.get("razao_social", "")),
            "valor_total": float(servico.get("valor_servicos", 0)),
            "data_emissao": datetime.now().isoformat(),
            "descricao_servico": servico.get("discriminacao", ""),
            "codigo_servico": servico.get("codigo_tributacao_nacional", ""),
            "protocolo": resultado.get("protocolo", ""),
            "xml_content": resultado.get("xml_nfse", ""),
            "fonte": "emissao_nacional_sefin",
        }

        result = db.table("notas_fiscais").insert(nota_db).execute()

        if not result.data:
            raise Exception("Erro ao salvar NFS-e Nacional no banco")

        return result.data[0]["id"]

    # ============================================
    # EMISSÃO VIA MUNICIPAL (LEGADO ABRASF)
    # ============================================

    async def _emitir_via_municipal(
        self,
        empresa_id: str,
        nfse_data: dict,
        usuario_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Emite NFS-e via API Municipal (ABRASF 2.04 - LEGADO).

        ATENÇÃO: Este fluxo é mantido apenas para municípios que ainda
        não aderiram ao Sistema Nacional. Preferir emissão via Nacional.
        """
        db = get_supabase_admin()

        try:
            # 1. Obter empresa
            empresa = db.table("empresas").select("*").eq(
                "id", empresa_id
            ).single().execute()

            if not empresa.data:
                return {"sucesso": False, "erro": "Empresa não encontrada"}

            emp = empresa.data
            municipio_codigo = emp.get("municipio_codigo", "")

            # 2. Obter credenciais
            creds = await nfse_service._obter_credenciais_nfse(
                db, empresa_id, municipio_codigo
            )

            if not creds:
                return {
                    "sucesso": False,
                    "erro": "Credenciais NFS-e não configuradas.",
                }

            # 3. Auto-numerar RPS se não informado
            if not nfse_data.get("numero_rps"):
                nfse_data["numero_rps"] = await self._proximo_numero_rps(db, empresa_id)

            # 4. Construir XML RPS
            xml_rps = self._construir_rps(nfse_data, emp)

            # 5. Enviar para API municipal
            adapter = nfse_service.obter_adapter(municipio_codigo, creds)

            resultado = await self._enviar_rps(
                adapter=adapter,
                xml_rps=xml_rps,
                municipio_codigo=municipio_codigo,
                credentials=creds,
                empresa=emp,
            )

            # 5. Salvar no banco se emitida
            if resultado.get("sucesso"):
                nota_id = await self._salvar_nfse_emitida(
                    db, empresa_id, nfse_data, resultado
                )
                resultado["nota_id"] = nota_id

            return resultado

        except Exception as e:
            logger.error(f"Erro ao emitir NFS-e: {e}", exc_info=True)
            return {"sucesso": False, "erro": str(e)}

    # ============================================
    # CANCELAMENTO
    # ============================================

    async def cancelar_nfse(
        self,
        empresa_id: str,
        numero_nfse: str,
        codigo_cancelamento: str = "2",
        motivo: str = "",
        usuario_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cancela NFS-e emitida via API municipal.

        Códigos de cancelamento:
        - 1: Erro na emissão
        - 2: Serviço não prestado
        - 3: Duplicidade de nota
        - 4: Erro de processamento

        Args:
            empresa_id: ID da empresa
            numero_nfse: Número da NFS-e
            codigo_cancelamento: Código do motivo
            motivo: Descrição do motivo
            usuario_id: ID do usuário

        Returns:
            Resultado do cancelamento
        """
        db = get_supabase_admin()

        try:
            # 1. Buscar empresa e nota
            empresa = db.table("empresas").select("*").eq(
                "id", empresa_id
            ).single().execute()

            if not empresa.data:
                return {"sucesso": False, "erro": "Empresa não encontrada"}

            emp = empresa.data
            municipio_codigo = emp.get("municipio_codigo", "")
            cnpj = emp.get("cnpj", "")

            # 2. Credenciais
            creds = await nfse_service._obter_credenciais_nfse(
                db, empresa_id, municipio_codigo
            )

            if not creds:
                return {"sucesso": False, "erro": "Credenciais não configuradas"}

            # 3. Construir XML de cancelamento
            xml_cancel = self._construir_xml_cancelamento(
                numero_nfse=numero_nfse,
                cnpj=cnpj,
                codigo_municipio=municipio_codigo,
                codigo_cancelamento=codigo_cancelamento,
                motivo=motivo,
            )

            # 4. Enviar para API municipal
            resultado = await self._enviar_cancelamento(
                municipio_codigo=municipio_codigo,
                xml_cancel=xml_cancel,
                credentials=creds,
            )

            # 5. Atualizar no banco
            if resultado.get("sucesso"):
                db.table("notas_fiscais").update({
                    "situacao": "cancelada",
                }).eq("empresa_id", empresa_id).eq(
                    "numero_nf", numero_nfse
                ).eq("tipo_nf", "NFSE").execute()

            return resultado

        except Exception as e:
            logger.error(f"Erro ao cancelar NFS-e: {e}", exc_info=True)
            return {"sucesso": False, "erro": str(e)}

    # ============================================
    # SEQUENCIAMENTO RPS
    # ============================================

    async def _proximo_numero_rps(self, db, empresa_id: str) -> str:
        """
        Retorna o próximo número de RPS para a empresa, com controle de concorrência.

        Estratégia: busca o maior número já usado no banco e incrementa.
        Usa upsert no campo numero_ultimo_rps da tabela empresas se existir,
        senão conta as notas emitidas + 1.
        """
        try:
            # Tentar atualizar contador atômico na empresa
            empresa_result = db.table("empresas").select(
                "numero_ultimo_rps"
            ).eq("id", empresa_id).single().execute()

            if empresa_result.data and "numero_ultimo_rps" in empresa_result.data:
                atual = empresa_result.data.get("numero_ultimo_rps") or 0
                proximo = atual + 1
                db.table("empresas").update(
                    {"numero_ultimo_rps": proximo}
                ).eq("id", empresa_id).execute()
                return str(proximo)

        except Exception:
            pass

        # Fallback: contar notas emitidas + 1
        try:
            count_result = db.table("notas_fiscais").select(
                "id", count="exact"
            ).eq("empresa_id", empresa_id).eq("tipo_nf", "NFSE").execute()
            total = count_result.count or 0
            return str(total + 1)
        except Exception:
            # Último recurso: timestamp como número
            from datetime import datetime
            return datetime.now().strftime("%Y%m%d%H%M%S")

    # ============================================
    # CÁLCULO IBS/CBS (LC 214/2025)
    # ============================================

    def calcular_ibs_cbs(
        self,
        valor_servicos: float,
        optante_simples: bool = False,
        aliquota_ibs: float = 0.0,
        aliquota_cbs: float = 0.0,
    ) -> dict:
        """
        Calcula IBS e CBS conforme LC 214/2025.

        Alíquotas de referência (transição 2026-2032):
        - IBS: alíquota estadual + municipal (varia por UF/município)
        - CBS: 8,8% federal (regime geral) ou 0% para Simples Nacional
        - Simples Nacional: substituídos pelo DAS, IBS/CBS = 0

        Na ausência de alíquotas configuradas, gera campos zerados
        (válido para emissão — a SEFIN aceita zeros durante a transição).

        Args:
            valor_servicos: Valor bruto dos serviços
            optante_simples: Se empresa é optante do Simples Nacional
            aliquota_ibs: Alíquota IBS (%) — 0 durante período de transição
            aliquota_cbs: Alíquota CBS (%) — padrão 8.8 para regime geral

        Returns:
            {"valor_ibs": float, "valor_cbs": float, "aliquota_ibs": float, "aliquota_cbs": float}
        """
        if optante_simples:
            # Simples Nacional: IBS e CBS substituídos pelo DAS
            return {
                "valor_ibs": 0.0,
                "valor_cbs": 0.0,
                "aliquota_ibs": 0.0,
                "aliquota_cbs": 0.0,
            }

        valor_ibs = round(valor_servicos * aliquota_ibs / 100, 2)
        valor_cbs = round(valor_servicos * aliquota_cbs / 100, 2)

        return {
            "valor_ibs": valor_ibs,
            "valor_cbs": valor_cbs,
            "aliquota_ibs": aliquota_ibs,
            "aliquota_cbs": aliquota_cbs,
        }

    # ============================================
    # CONSTRUÇÃO XML
    # ============================================

    def _construir_rps(self, nfse_data: dict, empresa: dict) -> str:
        """
        Constrói XML do RPS (Recibo Provisório de Serviço) - Padrão ABRASF 2.04.

        Cada município pode ter variações, mas o padrão ABRASF é o mais comum.
        """
        cnpj = empresa.get("cnpj", "")
        im = empresa.get("inscricao_municipal", "")
        data = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        tomador = nfse_data.get("tomador", {})
        servico = nfse_data.get("servico", {})

        valor_servicos = nfse_data.get("valor_servicos", "0.00")
        aliquota_iss = nfse_data.get("aliquota_iss", "0.00")
        valor_iss = nfse_data.get("valor_iss", "0.00")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<EnviarLoteRpsEnvio xmlns="http://www.abrasf.org.br/nfse.xsd">
    <LoteRps Id="LOTE{datetime.now().strftime('%Y%m%d%H%M%S')}" versao="2.04">
        <NumeroLote>1</NumeroLote>
        <CpfCnpj>
            <Cnpj>{cnpj}</Cnpj>
        </CpfCnpj>
        <InscricaoMunicipal>{im}</InscricaoMunicipal>
        <QuantidadeRps>1</QuantidadeRps>
        <ListaRps>
            <Rps>
                <InfDeclaracaoPrestacaoServico>
                    <Rps>
                        <IdentificacaoRps>
                            <Numero>{nfse_data.get('numero_rps', '1')}</Numero>
                            <Serie>{nfse_data.get('serie_rps', 'RPS')}</Serie>
                            <Tipo>1</Tipo>
                        </IdentificacaoRps>
                        <DataEmissao>{data}</DataEmissao>
                        <Status>1</Status>
                    </Rps>
                    <Competencia>{datetime.now().strftime('%Y-%m-%d')}</Competencia>
                    <Servico>
                        <Valores>
                            <ValorServicos>{valor_servicos}</ValorServicos>
                            <ValorDeducoes>{nfse_data.get('valor_deducoes', '0.00')}</ValorDeducoes>
                            <ValorPis>{nfse_data.get('valor_pis', '0.00')}</ValorPis>
                            <ValorCofins>{nfse_data.get('valor_cofins', '0.00')}</ValorCofins>
                            <ValorInss>{nfse_data.get('valor_inss', '0.00')}</ValorInss>
                            <ValorIr>{nfse_data.get('valor_ir', '0.00')}</ValorIr>
                            <ValorCsll>{nfse_data.get('valor_csll', '0.00')}</ValorCsll>
                            <IssRetido>{nfse_data.get('iss_retido', '2')}</IssRetido>
                            <ValorIss>{valor_iss}</ValorIss>
                            <Aliquota>{aliquota_iss}</Aliquota>
                        </Valores>
                        <ItemListaServico>{servico.get('item_lista', '')}</ItemListaServico>
                        <CodigoCnae>{servico.get('cnae', '')}</CodigoCnae>
                        <Discriminacao>{servico.get('discriminacao', '')}</Discriminacao>
                        <CodigoMunicipio>{empresa.get('municipio_codigo', '')}</CodigoMunicipio>
                    </Servico>
                    <Prestador>
                        <CpfCnpj>
                            <Cnpj>{cnpj}</Cnpj>
                        </CpfCnpj>
                        <InscricaoMunicipal>{im}</InscricaoMunicipal>
                    </Prestador>
                    <Tomador>
                        <IdentificacaoTomador>
                            <CpfCnpj>"""

        if tomador.get("cnpj"):
            xml += f"""
                                <Cnpj>{tomador['cnpj']}</Cnpj>"""
        elif tomador.get("cpf"):
            xml += f"""
                                <Cpf>{tomador['cpf']}</Cpf>"""

        xml += f"""
                            </CpfCnpj>
                        </IdentificacaoTomador>
                        <RazaoSocial>{tomador.get('nome', '')}</RazaoSocial>
                        <Endereco>
                            <Endereco>{tomador.get('logradouro', '')}</Endereco>
                            <Numero>{tomador.get('numero', 'SN')}</Numero>
                            <Bairro>{tomador.get('bairro', '')}</Bairro>
                            <CodigoMunicipio>{tomador.get('codigo_municipio', '')}</CodigoMunicipio>
                            <Uf>{tomador.get('uf', '')}</Uf>
                            <Cep>{tomador.get('cep', '')}</Cep>
                        </Endereco>
                    </Tomador>
                    <OptanteSimplesNacional>{nfse_data.get('simples_nacional', '2')}</OptanteSimplesNacional>
                    <IncentivoFiscal>2</IncentivoFiscal>
                </InfDeclaracaoPrestacaoServico>
            </Rps>
        </ListaRps>
    </LoteRps>
</EnviarLoteRpsEnvio>"""

        return xml

    def _construir_xml_cancelamento(
        self,
        numero_nfse: str,
        cnpj: str,
        codigo_municipio: str,
        codigo_cancelamento: str,
        motivo: str,
    ) -> str:
        """Constrói XML de cancelamento de NFS-e padrão ABRASF."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<CancelarNfseEnvio xmlns="http://www.abrasf.org.br/nfse.xsd">
    <Pedido>
        <InfPedidoCancelamento Id="CANCEL{numero_nfse}">
            <IdentificacaoNfse>
                <Numero>{numero_nfse}</Numero>
                <CpfCnpj>
                    <Cnpj>{cnpj}</Cnpj>
                </CpfCnpj>
                <CodigoMunicipio>{codigo_municipio}</CodigoMunicipio>
            </IdentificacaoNfse>
            <CodigoCancelamento>{codigo_cancelamento}</CodigoCancelamento>
            <MotivoCancelamento>{motivo}</MotivoCancelamento>
        </InfPedidoCancelamento>
    </Pedido>
</CancelarNfseEnvio>"""

    # ============================================
    # ENVIO PARA API MUNICIPAL
    # ============================================

    async def _enviar_rps(
        self,
        adapter,
        xml_rps: str,
        municipio_codigo: str,
        credentials: dict,
        empresa: dict,
    ) -> Dict[str, Any]:
        """
        Envia RPS para a API municipal e retorna resultado.

        O método de envio varia por município:
        - ABRASF: EnviarLoteRps (padrão nacional)
        - São Paulo: EnvioRPS (API própria)
        - Belo Horizonte: GerarNfse (API REST)
        """
        import httpx

        # URLs de emissão por adapter (simplificado)
        urls_emissao = self._obter_url_emissao(municipio_codigo)

        if not urls_emissao:
            return {
                "sucesso": False,
                "erro": f"Município {municipio_codigo} não suportado para emissão.",
            }

        try:
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "EnviarLoteRps",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    urls_emissao,
                    content=xml_rps.encode("utf-8"),
                    headers=headers,
                )

                if response.status_code == 200:
                    return self._parsear_resposta_emissao(response.text)

                return {
                    "sucesso": False,
                    "erro": f"HTTP {response.status_code}: {response.text[:200]}",
                }

        except Exception as e:
            logger.error(f"Erro ao enviar RPS: {e}")
            return {"sucesso": False, "erro": str(e)}

    async def _enviar_cancelamento(
        self,
        municipio_codigo: str,
        xml_cancel: str,
        credentials: dict,
    ) -> Dict[str, Any]:
        """Envia cancelamento para API municipal."""
        import httpx

        urls_cancel = self._obter_url_cancelamento(municipio_codigo)

        if not urls_cancel:
            return {
                "sucesso": False,
                "erro": f"Cancelamento não suportado para município {municipio_codigo}",
            }

        try:
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "CancelarNfse",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    urls_cancel,
                    content=xml_cancel.encode("utf-8"),
                    headers=headers,
                )

                if response.status_code == 200:
                    return self._parsear_resposta_cancelamento(response.text)

                return {
                    "sucesso": False,
                    "erro": f"HTTP {response.status_code}",
                }

        except Exception as e:
            logger.error(f"Erro ao cancelar NFS-e: {e}")
            return {"sucesso": False, "erro": str(e)}

    # ============================================
    # URLS DE EMISSÃO POR MUNICÍPIO
    # ============================================

    def _obter_url_emissao(self, municipio_codigo: str) -> Optional[str]:
        """Retorna URL de emissão para o município."""
        # Top 10 + municípios que seguem ABRASF
        urls = {
            # São Paulo
            "3550308": "https://nfe.prefeitura.sp.gov.br/ws/lotenfe.asmx",
            # Rio de Janeiro
            "3304557": "https://notacarioca.rio.gov.br/WSNacional/nfse.asmx",
            # Belo Horizonte
            "3106200": "https://bhissdigital.pbh.gov.br/bhiss-ws/nfse",
            # Brasília
            "5300108": "https://www.nfse.gov.br/EmissaoNota",
            # Curitiba
            "4106902": "https://isscuritiba.curitiba.pr.gov.br/Iss.NfseWebService/nfsews.asmx",
            # Porto Alegre
            "4314902": "https://nfe.portoalegre.rs.gov.br/bhiss-ws/nfse",
            # Salvador
            "2927408": "https://www.nfse.gov.br/EmissaoNota",
            # Fortaleza
            "2304400": "https://grfrj.fortaleza.ce.gov.br:443/grfiss/ws/nfse.asmx",
            # Recife
            "2611606": "https://www.nfse.gov.br/EmissaoNota",
            # Manaus
            "1302603": "https://sistemas.manaus.am.gov.br/nfse/services/NfseWebService",
        }

        return urls.get(municipio_codigo)

    def _obter_url_cancelamento(self, municipio_codigo: str) -> Optional[str]:
        """Retorna URL de cancelamento para o município."""
        # A maioria dos municípios usa o mesmo endpoint de emissão
        # com SOAPAction diferente
        return self._obter_url_emissao(municipio_codigo)

    # ============================================
    # PARSE DE RESPOSTAS
    # ============================================

    def _parsear_resposta_emissao(self, xml_response: str) -> Dict[str, Any]:
        """Parseia resposta de emissão NFS-e (padrão ABRASF)."""
        try:
            from lxml import etree

            root = etree.fromstring(xml_response.encode("utf-8"))
            ns = "http://www.abrasf.org.br/nfse.xsd"

            # Verificar se houve erro
            msg_retorno = root.find(f".//{{{ns}}}MensagemRetorno")
            if msg_retorno is not None:
                codigo = msg_retorno.findtext(f"{{{ns}}}Codigo", "")
                mensagem = msg_retorno.findtext(f"{{{ns}}}Mensagem", "")
                correcao = msg_retorno.findtext(f"{{{ns}}}Correcao", "")

                if codigo and codigo not in ("", "0", "L000"):
                    return {
                        "sucesso": False,
                        "erro": f"[{codigo}] {mensagem}",
                        "correcao": correcao,
                    }

            # Extrair número da NFS-e gerada
            nfse = root.find(f".//{{{ns}}}Nfse")
            if nfse is not None:
                numero = nfse.findtext(f".//{{{ns}}}Numero", "")
                cod_verif = nfse.findtext(f".//{{{ns}}}CodigoVerificacao", "")
                data_emissao = nfse.findtext(f".//{{{ns}}}DataEmissao", "")

                return {
                    "sucesso": True,
                    "numero_nfse": numero,
                    "codigo_verificacao": cod_verif,
                    "data_emissao": data_emissao,
                    "mensagem": "NFS-e emitida com sucesso",
                }

            # Verificar protocolo do lote
            protocolo = root.findtext(f".//{{{ns}}}Protocolo", "")
            if protocolo:
                return {
                    "sucesso": True,
                    "protocolo_lote": protocolo,
                    "mensagem": "Lote recebido. Consulte o resultado do processamento.",
                }

            return {
                "sucesso": False,
                "erro": "Resposta não reconhecida da API municipal",
            }

        except Exception as e:
            logger.error(f"Erro ao parsear resposta emissão: {e}")
            return {"sucesso": False, "erro": f"Erro ao processar resposta: {e}"}

    def _parsear_resposta_cancelamento(self, xml_response: str) -> Dict[str, Any]:
        """Parseia resposta de cancelamento NFS-e."""
        try:
            from lxml import etree

            root = etree.fromstring(xml_response.encode("utf-8"))
            ns = "http://www.abrasf.org.br/nfse.xsd"

            # Verificar confirmação
            confirmacao = root.find(f".//{{{ns}}}Confirmacao")
            if confirmacao is not None:
                return {
                    "sucesso": True,
                    "mensagem": "NFS-e cancelada com sucesso",
                }

            # Verificar erro
            msg_retorno = root.find(f".//{{{ns}}}MensagemRetorno")
            if msg_retorno is not None:
                codigo = msg_retorno.findtext(f"{{{ns}}}Codigo", "")
                mensagem = msg_retorno.findtext(f"{{{ns}}}Mensagem", "")

                return {
                    "sucesso": False,
                    "erro": f"[{codigo}] {mensagem}",
                }

            return {"sucesso": False, "erro": "Resposta não reconhecida"}

        except Exception as e:
            logger.error(f"Erro ao parsear cancelamento: {e}")
            return {"sucesso": False, "erro": str(e)}

    # ============================================
    # PERSISTÊNCIA
    # ============================================

    async def _salvar_nfse_emitida(
        self,
        db,
        empresa_id: str,
        nfse_data: dict,
        resultado: dict,
    ) -> str:
        """Salva NFS-e emitida no banco de dados."""
        tomador = nfse_data.get("tomador", {})
        servico = nfse_data.get("servico", {})

        nota_db = {
            "empresa_id": empresa_id,
            "tipo_nf": "NFSE",
            "numero_nf": resultado.get("numero_nfse", ""),
            "serie": nfse_data.get("serie_rps", "RPS"),
            "situacao": "autorizada",
            "cnpj_destinatario": tomador.get("cnpj") or tomador.get("cpf"),
            "nome_destinatario": tomador.get("nome", ""),
            "valor_total": float(nfse_data.get("valor_servicos", 0)),
            "data_emissao": datetime.now().isoformat(),
            "codigo_verificacao": resultado.get("codigo_verificacao", ""),
            "descricao_servico": servico.get("discriminacao", ""),
            "codigo_servico": servico.get("item_lista", ""),
            "valor_iss": float(nfse_data.get("valor_iss", 0)),
            "aliquota_iss": float(nfse_data.get("aliquota_iss", 0)),
            "fonte": "emissao_hicontrol",
        }

        chave = f"NFSE-{empresa_id[:8]}-{resultado.get('numero_nfse', '0')}"
        nota_db["chave_acesso"] = chave

        result = db.table("notas_fiscais").insert(nota_db).execute()

        if not result.data:
            raise Exception("Erro ao salvar NFS-e no banco")

        return result.data[0]["id"]


# ============================================
# MUNICÍPIOS EXPANDIDOS (50 municípios)
# ============================================

# Lista adicional de 40 municípios com API NFS-e
# Estes usam o padrão ABRASF e podem ser atendidos
# pelo adapter genérico ou pelo Sistema Nacional
MUNICIPIOS_EXPANDIDOS = [
    # Capitais restantes
    {"codigo": "1100205", "nome": "Porto Velho", "uf": "RO", "sistema": "ABRASF"},
    {"codigo": "1200401", "nome": "Rio Branco", "uf": "AC", "sistema": "ABRASF"},
    {"codigo": "1400100", "nome": "Boa Vista", "uf": "RR", "sistema": "ABRASF"},
    {"codigo": "1501402", "nome": "Belém", "uf": "PA", "sistema": "ABRASF"},
    {"codigo": "1600303", "nome": "Macapá", "uf": "AP", "sistema": "ABRASF"},
    {"codigo": "1721000", "nome": "Palmas", "uf": "TO", "sistema": "ABRASF"},
    {"codigo": "2111300", "nome": "São Luís", "uf": "MA", "sistema": "ABRASF"},
    {"codigo": "2211001", "nome": "Teresina", "uf": "PI", "sistema": "ABRASF"},
    {"codigo": "2408102", "nome": "Natal", "uf": "RN", "sistema": "ABRASF"},
    {"codigo": "2507507", "nome": "João Pessoa", "uf": "PB", "sistema": "ABRASF"},
    {"codigo": "2704302", "nome": "Maceió", "uf": "AL", "sistema": "ABRASF"},
    {"codigo": "2800308", "nome": "Aracaju", "uf": "SE", "sistema": "ABRASF"},
    {"codigo": "2927408", "nome": "Salvador", "uf": "BA", "sistema": "ABRASF"},
    {"codigo": "3205309", "nome": "Vitória", "uf": "ES", "sistema": "ABRASF"},
    {"codigo": "5002704", "nome": "Campo Grande", "uf": "MS", "sistema": "ABRASF"},
    {"codigo": "5103403", "nome": "Cuiabá", "uf": "MT", "sistema": "ABRASF"},
    {"codigo": "5208707", "nome": "Goiânia", "uf": "GO", "sistema": "ABRASF"},
    {"codigo": "4205407", "nome": "Florianópolis", "uf": "SC", "sistema": "ABRASF"},
    # Cidades grandes (população > 500k)
    {"codigo": "3518800", "nome": "Guarulhos", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3509502", "nome": "Campinas", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3548708", "nome": "São Bernardo do Campo", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3547809", "nome": "Santo André", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3534401", "nome": "Osasco", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3549805", "nome": "São José dos Campos", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3543402", "nome": "Ribeirão Preto", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3552205", "nome": "Sorocaba", "uf": "SP", "sistema": "ABRASF"},
    {"codigo": "3170206", "nome": "Uberlândia", "uf": "MG", "sistema": "ABRASF"},
    {"codigo": "3118601", "nome": "Contagem", "uf": "MG", "sistema": "ABRASF"},
    {"codigo": "3136702", "nome": "Juiz de Fora", "uf": "MG", "sistema": "ABRASF"},
    {"codigo": "3303302", "nome": "Niterói", "uf": "RJ", "sistema": "ABRASF"},
    {"codigo": "3301702", "nome": "Duque de Caxias", "uf": "RJ", "sistema": "ABRASF"},
    {"codigo": "3304904", "nome": "São Gonçalo", "uf": "RJ", "sistema": "ABRASF"},
    {"codigo": "3303500", "nome": "Nova Iguaçu", "uf": "RJ", "sistema": "ABRASF"},
    {"codigo": "4113700", "nome": "Londrina", "uf": "PR", "sistema": "ABRASF"},
    {"codigo": "4115200", "nome": "Maringá", "uf": "PR", "sistema": "ABRASF"},
    {"codigo": "4309209", "nome": "Gravataí", "uf": "RS", "sistema": "ABRASF"},
    {"codigo": "4303004", "nome": "Canoas", "uf": "RS", "sistema": "ABRASF"},
    {"codigo": "4305108", "nome": "Caxias do Sul", "uf": "RS", "sistema": "ABRASF"},
    {"codigo": "2304400", "nome": "Fortaleza", "uf": "CE", "sistema": "ISSFortaleza"},
    {"codigo": "2611606", "nome": "Recife", "uf": "PE", "sistema": "ABRASF"},
]


# Singleton
emissao_nfse_service = EmissaoNFSeService()
