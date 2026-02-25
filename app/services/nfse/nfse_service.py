"""
Serviço orquestrador para busca de NFS-e (Nota Fiscal de Serviço Eletrônica).

Responsabilidades:
- Selecionar o adapter correto com base no município da empresa
- Gerenciar credenciais de acesso às APIs municipais
- Orquestrar busca, processamento e persistência das notas
- Registrar auditoria de consultas

Uso:
    from app.services.nfse.nfse_service import nfse_service

    resultado = await nfse_service.buscar_notas_empresa(
        empresa_id="uuid",
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 2, 1)
    )
"""
from datetime import date, datetime
from typing import Any, List, Dict, Optional, Type
import hashlib
import logging
import os
import re

from app.db.supabase_client import get_supabase_admin
from app.services.nfse.base_adapter import (
    BaseNFSeAdapter,
    NFSeException,
    NFSeSearchException,
    NFSeConfigException,
)
from app.services.nfse.sistema_nacional import SistemaNacionalAdapter
from app.services.nfse.belo_horizonte import BeloHorizonteAdapter
from app.services.nfse.sao_paulo import SaoPauloAdapter
from app.services.nfse.rio_de_janeiro import RioDeJaneiroAdapter
from app.services.nfse.curitiba import CuritibaAdapter
from app.services.nfse.porto_alegre import PortoAlegreAdapter
from app.services.nfse.fortaleza import FortalezaAdapter
from app.services.nfse.manaus import ManausAdapter

logger = logging.getLogger(__name__)


class NFSeService:
    """
    Serviço orquestrador para busca de NFS-e.
    Seleciona o adapter apropriado com base no município.
    Padrão singleton (instância global no final do arquivo).
    """

    # Mapeamento de códigos IBGE → Adapter específico
    # Municípios não listados aqui usam o Sistema Nacional como fallback
    MUNICIPIO_ADAPTERS: Dict[str, Type[BaseNFSeAdapter]] = {
        "3106200": BeloHorizonteAdapter,   # Belo Horizonte/MG
        "3550308": SaoPauloAdapter,        # São Paulo/SP
        "3304557": RioDeJaneiroAdapter,    # Rio de Janeiro/RJ
        "4106902": CuritibaAdapter,        # Curitiba/PR
        "4314902": PortoAlegreAdapter,     # Porto Alegre/RS
        "2304400": FortalezaAdapter,       # Fortaleza/CE
        "1302603": ManausAdapter,          # Manaus/AM
        # Brasília (5300108), Salvador (2927408), Recife (2611606)
        # usam o Sistema Nacional (ABRASF) como fallback
    }

    # Info dos municípios suportados (para endpoint de listagem)
    MUNICIPIOS_INFO = [
        {
            "codigo_ibge": "3550308",
            "nome": "São Paulo",
            "uf": "SP",
            "sistema": "NF Paulistana (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "3304557",
            "nome": "Rio de Janeiro",
            "uf": "RJ",
            "sistema": "Nota Carioca (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "3106200",
            "nome": "Belo Horizonte",
            "uf": "MG",
            "sistema": "BHISSDigital (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "5300108",
            "nome": "Brasília",
            "uf": "DF",
            "sistema": "Sistema Nacional de NFS-e (ABRASF)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "4106902",
            "nome": "Curitiba",
            "uf": "PR",
            "sistema": "ISSCuritiba (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "4314902",
            "nome": "Porto Alegre",
            "uf": "RS",
            "sistema": "ISSQN POA (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "2927408",
            "nome": "Salvador",
            "uf": "BA",
            "sistema": "Sistema Nacional de NFS-e (ABRASF)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "2304400",
            "nome": "Fortaleza",
            "uf": "CE",
            "sistema": "ISSFortaleza (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "2611606",
            "nome": "Recife",
            "uf": "PE",
            "sistema": "Sistema Nacional de NFS-e (ABRASF)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "1302603",
            "nome": "Manaus",
            "uf": "AM",
            "sistema": "SEMEF Manaus (API Própria)",
            "status": "implementado",
        },
        {
            "codigo_ibge": "default",
            "nome": "Demais municípios",
            "uf": "Todos",
            "sistema": "Sistema Nacional de NFS-e (ABRASF)",
            "status": "implementado",
        },
    ]

    def _forcar_sistema_nacional(self) -> bool:
        """
        Define o padrão de integração NFS-e.
        Default: Sistema Nacional para todas as empresas.
        """
        valor = os.getenv("NFSE_FORCAR_SISTEMA_NACIONAL", "true").strip().lower()
        return valor not in {"0", "false", "no", "off"}

    def obter_adapter(
        self,
        municipio_codigo: str,
        credentials: Dict[str, str],
        homologacao: bool = False,
    ) -> BaseNFSeAdapter:
        """
        Retorna o adapter apropriado para o município.
        Se não houver adapter específico, usa Sistema Nacional.

        Args:
            municipio_codigo: Código IBGE do município (7 dígitos)
            credentials: Credenciais de acesso à API
            homologacao: Se True, usa ambiente de homologação

        Returns:
            Instância do adapter configurado
        """
        if self._forcar_sistema_nacional():
            return SistemaNacionalAdapter(credentials, homologacao=homologacao)

        adapter_class = self.MUNICIPIO_ADAPTERS.get(
            municipio_codigo,
            SistemaNacionalAdapter,
        )

        return adapter_class(credentials, homologacao=homologacao)

    async def buscar_notas_empresa(
        self,
        empresa_id: str,
        data_inicio: date,
        data_fim: date,
        usuario_id: Optional[str] = None,
    ) -> Dict:
        """
        Busca NFS-e de uma empresa no período especificado.

        Fluxo:
        1. Busca dados da empresa no banco
        2. Busca credenciais NFS-e configuradas
        3. Seleciona adapter do município
        4. Realiza autenticação + busca na API municipal
        5. Salva notas no banco (upsert)
        6. Retorna resultado formatado

        Args:
            empresa_id: UUID da empresa no Hi-Control
            data_inicio: Data inicial da consulta
            data_fim: Data final da consulta
            usuario_id: ID do usuário que solicitou (para auditoria)

        Returns:
            Dict com notas encontradas e metadados

        Raises:
            NFSeConfigException: Credenciais não configuradas
            NFSeSearchException: Erro na busca
            ValueError: Empresa não encontrada
        """
        inicio = datetime.now()
        db = get_supabase_admin()

        try:
            # 1. Buscar dados da empresa
            empresa = await self._obter_empresa(db, empresa_id)

            if not empresa:
                raise ValueError(f"Empresa {empresa_id} não encontrada")

            cnpj = empresa.get("cnpj", "")
            municipio_codigo = empresa.get("municipio_codigo") or ""
            razao_social = empresa.get("razao_social", "N/A")

            logger.info(
                f"[NFS-e] Buscando notas para empresa '{razao_social}' "
                f"(CNPJ: {cnpj}, Município: {municipio_codigo})"
            )

            # 2. Buscar credenciais NFS-e da empresa
            # Se não houver credenciais manuais, tenta auto-configurar via certificado A1.
            credentials = await self._obter_credenciais_nfse(db, empresa, municipio_codigo)

            if not credentials:
                logger.warning(
                    f"[NFS-e] Empresa {empresa_id} sem credenciais NFS-e configuradas "
                    f"para município {municipio_codigo}"
                )
                return {
                    "success": False,
                    "notas": [],
                    "quantidade": 0,
                    "periodo": {
                        "inicio": data_inicio.isoformat(),
                        "fim": data_fim.isoformat(),
                    },
                    "mensagem": (
                        "Credenciais NFS-e não configuradas para esta empresa "
                        "e não foi possível auto-configurar via certificado A1. "
                        "Configure as credenciais no menu Configurações > NFS-e."
                    ),
                    "erro_tipo": "credenciais_ausentes",
                }

            # 3. Selecionar adapter apropriado
            adapter = self.obter_adapter(municipio_codigo, credentials)

            logger.info(
                f"[NFS-e] Usando adapter: {adapter.SISTEMA_NOME} "
                f"para município {municipio_codigo}"
            )

            # 4. Buscar notas na API municipal
            notas = await adapter.buscar_notas(cnpj, data_inicio, data_fim)

            # 5. Salvar notas no banco
            notas_salvas = await self._salvar_notas(
                db=db,
                empresa_id=empresa_id,
                notas=notas,
                empresa_cnpj=cnpj,
            )

            # 5.1 Persistir cursor NSU automatico (quando o adapter suporta ADN).
            await self._persistir_cursor_nsu_automatico(db, credentials, adapter)

            # 6. Registrar auditoria
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            await self._registrar_auditoria(
                db=db,
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                municipio_codigo=municipio_codigo,
                sistema=adapter.SISTEMA_NOME,
                quantidade=len(notas_salvas),
                sucesso=True,
                tempo_ms=tempo_ms,
            )

            logger.info(
                f"[NFS-e] {len(notas_salvas)} notas importadas para empresa "
                f"'{razao_social}' em {tempo_ms}ms"
            )

            return {
                "success": True,
                "notas": notas_salvas,
                "quantidade": len(notas_salvas),
                "periodo": {
                    "inicio": data_inicio.isoformat(),
                    "fim": data_fim.isoformat(),
                },
                "sistema": adapter.SISTEMA_NOME,
                "municipio": {
                    "codigo": municipio_codigo,
                    "nome": empresa.get("municipio_nome", ""),
                },
                "tempo_ms": tempo_ms,
            }

        except (NFSeException, ValueError):
            raise
        except Exception as e:
            logger.error(f"[NFS-e] Erro ao buscar notas: {e}", exc_info=True)

            # Registrar falha na auditoria
            try:
                tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
                await self._registrar_auditoria(
                    db=db,
                    empresa_id=empresa_id,
                    usuario_id=usuario_id,
                    municipio_codigo="",
                    sistema="",
                    quantidade=0,
                    sucesso=False,
                    tempo_ms=tempo_ms,
                    erro=str(e),
                )
            except Exception:
                pass

            raise NFSeSearchException(f"Erro ao buscar NFS-e: {e}")

    # ============================================
    # MÉTODOS PRIVADOS
    # ============================================

    async def _obter_empresa(self, db, empresa_id: str) -> Optional[Dict]:
        """
        Busca dados da empresa no banco.

        Args:
            db: Cliente Supabase admin
            empresa_id: UUID da empresa

        Returns:
            Dict com dados da empresa ou None
        """
        try:
            result = db.table("empresas")\
                .select(
                    "id, cnpj, razao_social, municipio_codigo, municipio_nome, estado, "
                    "certificado_a1, certificado_senha_encrypted"
                )\
                .eq("id", empresa_id)\
                .single()\
                .execute()

            return result.data if result.data else None

        except Exception as e:
            logger.error(f"[NFS-e] Erro ao buscar empresa {empresa_id}: {e}")
            return None

    async def _obter_credenciais_nfse(
        self,
        db,
        empresa: Dict[str, Any],
        municipio_codigo: str,
    ) -> Optional[Dict]:
        """
        Busca credenciais NFS-e da empresa para o município.

        As credenciais são armazenadas na tabela 'credenciais_nfse'
        e são específicas por empresa + município.

        Args:
            db: Cliente Supabase admin
            empresa_id: UUID da empresa
            municipio_codigo: Código IBGE do município

        Returns:
            Dict com credenciais ou None se não configuradas
        """
        empresa_id = str(empresa.get("id") or "")
        try:
            result = db.table("credenciais_nfse")\
                .select("id, usuario, senha, token, cnpj, municipio_codigo")\
                .eq("empresa_id", empresa_id)\
                .eq("ativo", True)\
                .execute()

            if not result.data:
                return await self._gerar_credencial_auto_certificado(
                    db=db,
                    empresa=empresa,
                    municipio_codigo=municipio_codigo,
                )

            # Priorizar credencial específica do município
            for cred in result.data:
                if cred.get("municipio_codigo") == municipio_codigo:
                    return self._anexar_certificado_nas_credenciais(cred, empresa)

            # Fallback: usar primeira credencial ativa disponível
            return self._anexar_certificado_nas_credenciais(result.data[0], empresa)

        except Exception as e:
            logger.warning(f"[NFS-e] Erro ao buscar credenciais: {e}")
            return None

    def _anexar_certificado_nas_credenciais(
        self,
        credencial: Dict[str, Any],
        empresa: Dict[str, Any],
    ) -> Dict[str, Any]:
        cred = {
            "credencial_id": credencial.get("id"),
            "usuario": credencial.get("usuario"),
            "senha": credencial.get("senha"),
            "token": credencial.get("token"),
            "cnpj": credencial.get("cnpj") or empresa.get("cnpj"),
            "municipio_codigo": credencial.get("municipio_codigo") or empresa.get("municipio_codigo"),
            "nsu_inicial": self._extrair_nsu_cursor_token(credencial.get("token")),
        }

        cert_a1 = empresa.get("certificado_a1")
        cert_senha_encrypted = empresa.get("certificado_senha_encrypted")
        if cert_a1 and cert_senha_encrypted:
            cred["certificado_a1"] = cert_a1
            cred["certificado_senha_encrypted"] = cert_senha_encrypted
            cred["modo_autenticacao"] = "certificado_a1"

        return cred

    async def _gerar_credencial_auto_certificado(
        self,
        db,
        empresa: Dict[str, Any],
        municipio_codigo: str,
    ) -> Optional[Dict[str, Any]]:
        cert_a1 = empresa.get("certificado_a1")
        cert_senha_encrypted = empresa.get("certificado_senha_encrypted")
        if not cert_a1 or not cert_senha_encrypted:
            return None

        empresa_id = str(empresa.get("id") or "")
        municipio = str(municipio_codigo or empresa.get("municipio_codigo") or "").strip() or "0000000"
        cnpj_limpo = self._normalizar_cnpj(str(empresa.get("cnpj") or ""))

        credencial_auto = {
            "empresa_id": empresa_id,
            "municipio_codigo": municipio,
            "usuario": "AUTO_CERT_A1",
            "senha": None,
            "token": "AUTO_CERT_A1|NSU:0",
            "cnpj": cnpj_limpo or None,
            "ativo": True,
        }

        try:
            db.table("credenciais_nfse").upsert(
                credencial_auto,
                on_conflict="empresa_id,municipio_codigo",
            ).execute()
            logger.info(
                "[NFS-e] Credencial tecnica auto-configurada via certificado para empresa %s (municipio=%s)",
                empresa_id,
                municipio,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[NFS-e] Falha ao persistir credencial tecnica via certificado (empresa=%s): %s",
                empresa_id,
                exc,
            )

        return self._anexar_certificado_nas_credenciais(credencial_auto, empresa)

    def _normalizar_cnpj(self, cnpj: str) -> str:
        return re.sub(r"\D", "", cnpj or "")

    def _extrair_nsu_cursor_token(self, token: Optional[str]) -> int:
        valor = str(token or "").strip()
        if not valor:
            return 0
        token_upper = valor.upper()

        # Quando o bootstrap recente ja foi concluido, prioriza o cursor HOTNSU.
        if "HOTDONE:1" in token_upper:
            match_hot = re.search(r"(?:^|\|)HOTNSU:(\d+)", valor, re.IGNORECASE)
            if match_hot:
                try:
                    return int(match_hot.group(1))
                except ValueError:
                    pass

        match = re.search(r"(?:^|\|)NSU:(\d+)", valor, re.IGNORECASE)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except ValueError:
            return 0

    async def _persistir_cursor_nsu_automatico(self, db, credentials: Dict[str, Any], adapter: Any) -> None:
        credencial_id = credentials.get("credencial_id")
        if not credencial_id:
            return

        if str(credentials.get("modo_autenticacao") or "").strip().lower() != "certificado_a1":
            return

        token_atual = str(credentials.get("token") or "")
        token_upper = token_atual.upper()
        if token_upper and not token_upper.startswith("AUTO_CERT_A1"):
            return

        token_sugerido = str(getattr(adapter, "cursor_sugerido_token", "") or "").strip()
        if token_sugerido and token_sugerido != token_atual:
            try:
                db.table("credenciais_nfse").update({"token": token_sugerido}).eq("id", credencial_id).execute()
                credentials["token"] = token_sugerido
                credentials["nsu_inicial"] = self._extrair_nsu_cursor_token(token_sugerido)
                logger.info(
                    "[NFS-e] Cursor/token atualizado pela estrategia de prioridade na credencial %s: %s",
                    credencial_id,
                    token_sugerido,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[NFS-e] Falha ao persistir token sugerido da credencial %s: %s",
                    credencial_id,
                    exc,
                )
            return

        if not bool(getattr(adapter, "persistir_cursor_nsu", True)):
            return

        nsu_final = int(getattr(adapter, "nsu_final", 0) or 0)
        if nsu_final <= 0:
            return

        novo_token = f"AUTO_CERT_A1|NSU:{nsu_final}"
        if token_atual == novo_token:
            return

        try:
            db.table("credenciais_nfse").update({"token": novo_token}).eq("id", credencial_id).execute()
            credentials["token"] = novo_token
            credentials["nsu_inicial"] = nsu_final
            logger.info(
                "[NFS-e] Cursor NSU atualizado na credencial %s para %s",
                credencial_id,
                nsu_final,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[NFS-e] Falha ao persistir cursor NSU da credencial %s: %s",
                credencial_id,
                exc,
            )

    async def _salvar_notas(
        self,
        db,
        empresa_id: str,
        notas: List[Dict],
        empresa_cnpj: str = "",
    ) -> List[Dict]:
        """
        Salva notas NFS-e no banco de dados usando upsert.

        A chave de conflito é baseada na combinação de:
        município + número + código de verificação

        Args:
            db: Cliente Supabase admin
            empresa_id: UUID da empresa
            notas: Lista de notas no formato padrão

        Returns:
            Lista de notas salvas com IDs do banco
        """
        notas_salvas = []
        empresa_cnpj_limpo = self._normalizar_cnpj(empresa_cnpj)
        notas_ordenadas = sorted(
            notas,
            key=lambda n: str(n.get("data_emissao") or ""),
            reverse=True,
        )

        for nota in notas_ordenadas:
            try:
                # Gerar chave de acesso única para NFS-e
                # NFS-e não tem chave de 44 dígitos como NF-e
                chave_acesso = self._gerar_chave_nfse(nota)
                cnpj_prestador = self._normalizar_cnpj(str(nota.get("cnpj_prestador", "")))
                tipo_operacao = "saida" if empresa_cnpj_limpo and cnpj_prestador == empresa_cnpj_limpo else "entrada"
                xml_content = nota.get("xml_content", "")

                nota_db = {
                    "empresa_id": empresa_id,
                    "tipo_nf": "NFSe",
                    "numero_nf": nota.get("numero", ""),
                    "serie": nota.get("serie", ""),
                    "chave_acesso": chave_acesso,
                    "cnpj_emitente": nota.get("cnpj_prestador", ""),
                    "nome_emitente": nota.get("prestador_nome", ""),
                    "cnpj_destinatario": nota.get("cnpj_tomador", ""),
                    "nome_destinatario": nota.get("tomador_nome", ""),
                    "valor_total": nota.get("valor_total", 0),
                    "data_emissao": nota.get("data_emissao"),
                    "situacao": self._normalizar_status(nota.get("status", "")),
                    "xml_completo": xml_content,
                    "xml_resumo": xml_content,
                    "municipio_codigo": nota.get("municipio_codigo", ""),
                    "municipio_nome": nota.get("municipio_nome", ""),
                    "codigo_verificacao": nota.get("codigo_verificacao", ""),
                    "link_visualizacao": nota.get("link_visualizacao", ""),
                    "pdf_url": nota.get("pdf_url", ""),
                    "descricao_servico": nota.get("descricao_servico", ""),
                    "codigo_servico": nota.get("codigo_servico", ""),
                    "valor_iss": nota.get("valor_iss", 0),
                    "aliquota_iss": nota.get("aliquota_iss", 0),
                    "tipo_operacao": tipo_operacao,
                    "fonte": "sefaz_nacional",
                    "nsu": nota.get("nsu"),
                }

                # Upsert: insert ou update se chave_acesso já existir
                result = db.table("notas_fiscais")\
                    .upsert(nota_db, on_conflict="chave_acesso")\
                    .execute()

                if result.data:
                    notas_salvas.append(result.data[0])
                    logger.debug(
                        f"[NFS-e] Nota {nota.get('numero')} salva (chave: {chave_acesso})"
                    )

            except Exception as e:
                logger.error(
                    f"[NFS-e] Erro ao salvar nota {nota.get('numero', '?')}: {e}"
                )
                continue

        return notas_salvas

    def _gerar_chave_nfse(self, nota: Dict) -> str:
        """
        Gera chave de acesso única para NFS-e.

        Como NFS-e não possui chave de 44 dígitos como NF-e,
        geramos uma chave composta por:
        NFSE-{municipio}-{numero}-{codigo_verificacao}

        Args:
            nota: Dicionário com dados da nota

        Returns:
            Chave de acesso única
        """
        chave_externa = str(nota.get("chave_acesso") or "").strip()
        if chave_externa:
            return self._normalizar_chave_nfse(chave_externa)

        municipio = nota.get("municipio_codigo", "0000000")
        numero = nota.get("numero", "0")
        codigo_verif = nota.get("codigo_verificacao", "")
        cnpj = nota.get("cnpj_prestador", "")

        # Compor chave única
        partes = [
            "NFSE",
            municipio,
            cnpj[:14] if cnpj else "00000000000000",
            str(numero).zfill(10),
        ]

        if codigo_verif:
            partes.append(codigo_verif)

        return self._normalizar_chave_nfse("-".join(partes))

    def _normalizar_chave_nfse(self, chave: str) -> str:
        valor = re.sub(r"\s+", "", str(chave or ""))
        if len(valor) <= 44:
            return valor

        digest = hashlib.sha1(valor.encode("utf-8")).hexdigest().upper()
        # 4 + 40 = 44 caracteres (compatível com coluna chave_acesso atual).
        return f"NFSE{digest[:40]}"

    def _normalizar_status(self, status: str) -> str:
        """
        Normaliza status da NFS-e para padrão Hi-Control.

        Args:
            status: Status original da API

        Returns:
            Status normalizado (minúsculo)
        """
        status_lower = status.lower().strip()

        mapeamento = {
            "autorizada": "autorizada",
            "normal": "autorizada",
            "ativa": "autorizada",
            "emitida": "autorizada",
            "cancelada": "cancelada",
            "substituida": "cancelada",
            "anulada": "cancelada",
            "extraviada": "cancelada",
        }

        return mapeamento.get(status_lower, "autorizada")

    async def _registrar_auditoria(
        self,
        db,
        empresa_id: str,
        usuario_id: Optional[str],
        municipio_codigo: str,
        sistema: str,
        quantidade: int,
        sucesso: bool,
        tempo_ms: int,
        erro: Optional[str] = None,
    ):
        """
        Registra consulta NFS-e no histórico para auditoria.

        Args:
            db: Cliente Supabase admin
            empresa_id: UUID da empresa
            usuario_id: UUID do usuário
            municipio_codigo: Código IBGE
            sistema: Nome do sistema usado
            quantidade: Quantidade de notas encontradas
            sucesso: Se a consulta teve sucesso
            tempo_ms: Tempo de resposta em milissegundos
            erro: Mensagem de erro (se houver)
        """
        logger.debug(
            "[NFS-e] Auditoria sem persistencia | empresa=%s usuario=%s municipio=%s sistema=%s qtd=%s sucesso=%s tempo_ms=%s erro=%s",
            empresa_id,
            usuario_id,
            municipio_codigo,
            sistema,
            quantidade,
            sucesso,
            tempo_ms,
            erro,
        )

    # ============================================
    # MÉTODOS PÚBLICOS AUXILIARES
    # ============================================

    async def salvar_credenciais(
        self,
        empresa_id: str,
        municipio_codigo: str,
        usuario: str,
        senha: str,
        cnpj: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Dict:
        """
        Salva/atualiza credenciais NFS-e de uma empresa.

        Args:
            empresa_id: UUID da empresa
            municipio_codigo: Código IBGE do município
            usuario: Usuário da API municipal
            senha: Senha da API municipal
            cnpj: CNPJ (opcional)
            token: Token de acesso (opcional)

        Returns:
            Dict com credencial salva
        """
        db = get_supabase_admin()

        credencial = {
            "empresa_id": empresa_id,
            "municipio_codigo": municipio_codigo,
            "usuario": usuario,
            "senha": senha,
            "cnpj": cnpj,
            "token": token,
            "ativo": True,
        }

        result = db.table("credenciais_nfse")\
            .upsert(credencial, on_conflict="empresa_id,municipio_codigo")\
            .execute()

        if result.data:
            logger.info(
                f"[NFS-e] Credenciais salvas para empresa {empresa_id} "
                f"município {municipio_codigo}"
            )
            return result.data[0]

        raise NFSeConfigException("Erro ao salvar credenciais NFS-e")

    async def listar_credenciais_empresa(self, empresa_id: str) -> List[Dict]:
        """
        Lista credenciais NFS-e configuradas para uma empresa.

        Args:
            empresa_id: UUID da empresa

        Returns:
            Lista de credenciais (sem senha)
        """
        db = get_supabase_admin()

        result = db.table("credenciais_nfse")\
            .select("id, municipio_codigo, usuario, cnpj, ativo, created_at, updated_at")\
            .eq("empresa_id", empresa_id)\
            .order("created_at", desc=True)\
            .execute()

        return result.data or []

    def listar_municipios_suportados(self) -> List[Dict]:
        """
        Retorna lista de municípios com API NFS-e implementada.

        Returns:
            Lista de municípios com informações do sistema
        """
        return self.MUNICIPIOS_INFO


# ============================================
# INSTÂNCIA SINGLETON
# ============================================

nfse_service = NFSeService()
