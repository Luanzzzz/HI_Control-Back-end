#!/usr/bin/env python3
"""
Bot de Busca Automática de Notas Fiscais - Hi-Control

Seguindo padrões MCP:
- Tool Pattern: Adapters como ferramentas bem definidas
- Resource Pattern: Supabase como recurso centralizado
- Error Handling: Robusto e informativo
- Logging: Estruturado e detalhado

Funcionalidades:
- Busca NFS-e via Base Nacional (ABRASF)
- Usa credenciais das empresas cadastradas
- Roda automaticamente via APScheduler
- Salva no Supabase (zero duplicidade)
"""

import logging
import sys
from datetime import datetime, timedelta, date
from typing import Dict, List
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Imports locais
from bot.config import config
from bot.adapters.base_nacional import BaseNacionalAdapter, NFSeAuthException, NFSeSearchException
from bot.utils.supabase_client import SupabaseResource
from bot.utils.certificado import CertificadoLoader

# Google Drive integration
try:
    from app.services.google_drive_service import google_drive_service
except ImportError:
    google_drive_service = None

# Configurar logging seguindo padrões MCP
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    datefmt=config.LOG_DATE_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class BotBuscadorNotas:
    """
    Bot principal de busca automática de notas fiscais.
    
    Seguindo padrões MCP:
    - Orquestra uso de tools (adapters)
    - Acessa resources (Supabase)
    - Error handling robusto
    """
    
    def __init__(self):
        """Inicializa o bot."""
        try:
            config.validate()
            logger.info("🤖 Bot Buscador de Notas - Inicializado")
        except ValueError as e:
            logger.error(f"❌ Erro de configuração: {e}")
            raise
    
    def executar_busca(self):
        """
        Execução principal do bot.
        
        Seguindo padrões MCP: operação idempotente e segura.
        """
        logger.info("=" * 80)
        logger.info("🚀 INICIANDO BUSCA DE NOTAS")
        logger.info(f"📅 Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        logger.info("=" * 80)
        
        try:
            # 1. Buscar empresas ativas (Resource Pattern)
            empresas = SupabaseResource.buscar_empresas_ativas()
            
            if not empresas:
                logger.warning("⚠️ Nenhuma empresa ativa encontrada")
                return
            
            logger.info(f"📊 {len(empresas)} empresas para processar\n")
            
            # Contadores
            total_notas = 0
            total_erros = 0
            
            # 2. Processar cada empresa
            for i, empresa in enumerate(empresas, 1):
                logger.info(f"\n{'=' * 60}")
                logger.info(f"📦 [{i}/{len(empresas)}] {empresa.get('razao_social', 'N/A')}")
                logger.info(f"   CNPJ: {empresa.get('cnpj', 'N/A')}")
                logger.info(f"{'=' * 60}")
                
                try:
                    notas = self._buscar_notas_empresa(empresa)
                    total_notas += len(notas)
                    
                except Exception as e:
                    logger.error(
                        f"❌ Erro ao processar empresa {empresa.get('cnpj', '?')}: {e}",
                        exc_info=True
                    )
                    total_erros += 1
            
            # 3. Relatório final
            logger.info("\n" + "=" * 80)
            logger.info("✅ BUSCA FINALIZADA")
            logger.info(f"📊 Total de notas importadas: {total_notas}")
            logger.info(f"❌ Empresas com erro: {total_erros}")
            logger.info("=" * 80 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Erro fatal no bot: {e}", exc_info=True)
    
    def _buscar_notas_empresa(self, empresa: Dict) -> List[Dict]:
        """
        Busca notas de uma empresa específica.
        
        Args:
            empresa: Dicionário com dados da empresa
            
        Returns:
            Lista de notas encontradas
        """
        notas_total = []
        empresa_id = empresa.get("id")
        cnpj = empresa.get("cnpj", "")
        municipio_codigo = empresa.get("municipio_codigo", "")
        
        if not empresa_id:
            logger.warning("⚠️ Empresa sem ID válido")
            return []
        
        # Período de busca
        data_fim = datetime.now().date()
        data_inicio = data_fim - timedelta(days=config.DIAS_RETROATIVOS)
        
        logger.info(
            f"📅 Período: {data_inicio.strftime('%d/%m/%Y')} até "
            f"{data_fim.strftime('%d/%m/%Y')}"
        )
        
        try:
            # 1. Buscar credenciais NFS-e (Resource Pattern) com fallback
            logger.info(f"[FLOW] Empresa: {empresa.get('razao_social')}")
            logger.info(f"[FLOW] CNPJ: {cnpj}")
            logger.info(f"[FLOW] Município: {municipio_codigo or 'NÃO INFORMADO'}")

            if municipio_codigo:
                logger.info(f"[FLOW] Buscando credencial por município...")
                credenciais = SupabaseResource.buscar_credenciais_nfse(
                    empresa_id,
                    municipio_codigo
                )
            else:
                logger.warning(f"[FLOW] Município vazio - usando fallback")
                credenciais = SupabaseResource.buscar_credenciais_nfse_por_empresa(
                    empresa_id
                )

            if not credenciais:
                logger.error(f"[FLOW] ❌ FALHA: Nenhuma credencial encontrada")
                logger.info(f"[FLOW] 💡 SOLUÇÃO: Cadastrar credenciais em Configurações > Credenciais NFS-e")
                return []

            logger.info(f"[FLOW] ✅ Credencial OK")
            
            # 2. Preparar credenciais para adapter
            adapter_credentials = {
                "usuario": credenciais.get("usuario"),
                "senha": credenciais.get("senha"),
                "cnpj": cnpj,
            }
            
            # 3. Buscar via Base Nacional (Tool Pattern)
            logger.info("🔍 Consultando Base Nacional...")
            
            adapter = BaseNacionalAdapter(
                credentials=adapter_credentials,
                homologacao=config.BASE_NACIONAL_HOMOLOGACAO
            )
            
            # Autenticar e buscar notas (async)
            import asyncio
            
            async def buscar_async():
                try:
                    await adapter.autenticar()
                except NFSeAuthException as e:
                    logger.error(f"❌ Erro de autenticação: {e}")
                    return []
                
                try:
                    return await adapter.buscar_notas(
                        cnpj=cnpj,
                        data_inicio=data_inicio,
                        data_fim=data_fim,
                        limite=100
                    )
                except NFSeSearchException as e:
                    logger.error(f"❌ Erro na busca: {e}")
                    return []
            
            notas = asyncio.run(buscar_async())
            notas_total = notas
            
            if notas_total:
                logger.info(f"✅ {len(notas_total)} NFS-e encontradas")
            
            # 4. Salvar no banco (Resource Pattern)
            if notas_total:
                logger.info("💾 Salvando notas no banco...")
                salvos = SupabaseResource.salvar_lote_notas(notas_total, empresa_id)
                logger.info(f"✅ {salvos}/{len(notas_total)} notas salvas")

                # 5. Salvar XMLs no Google Drive (se configurado)
                if google_drive_service:
                    self._salvar_notas_no_drive(
                        notas_total, empresa_id, empresa
                    )

            return notas_total
            
        except Exception as e:
            logger.error(
                f"❌ Erro ao buscar notas para empresa {cnpj}: {e}",
                exc_info=True
            )
            return []


    def _salvar_notas_no_drive(
        self, notas: List[Dict], empresa_id: str, empresa: Dict
    ):
        """
        Salva XMLs das notas no Google Drive (se configurado).

        Executa em loop async separado pois o metodo do Drive eh async.
        """
        import asyncio

        empresa_nome = empresa.get("razao_social", "Empresa")

        async def _upload_todas():
            salvos = 0
            for nota in notas:
                xml_content = nota.get("xml_content", "")
                if not xml_content:
                    continue

                try:
                    xml_bytes = (
                        xml_content.encode("utf-8")
                        if isinstance(xml_content, str)
                        else xml_content
                    )

                    file_id = await google_drive_service.salvar_xml_no_drive(
                        empresa_id=empresa_id,
                        empresa_nome=empresa_nome,
                        xml_content=xml_bytes,
                        nota_info={
                            "tipo": nota.get("tipo", "NFS-e"),
                            "numero": nota.get("numero", ""),
                            "data_emissao": nota.get("data_emissao", ""),
                            "chave_acesso": nota.get("chave_acesso", ""),
                        },
                    )

                    if file_id:
                        salvos += 1

                except Exception as e:
                    logger.warning(
                        f"⚠️ Erro ao salvar nota {nota.get('numero', '?')} "
                        f"no Drive: {e}"
                    )

            if salvos > 0:
                logger.info(
                    f"☁️ {salvos} XMLs salvos no Google Drive "
                    f"para empresa {empresa_nome}"
                )

        try:
            asyncio.run(_upload_todas())
        except Exception as e:
            logger.warning(
                f"⚠️ Erro geral ao salvar no Drive: {e}"
            )


def main():
    """
    Função principal - configura scheduler.
    
    Seguindo padrões MCP: inicialização segura e error handling.
    """
    try:
        bot = BotBuscadorNotas()
        
        # Executar uma vez imediatamente se configurado
        if config.EXECUTAR_IMEDIATAMENTE:
            logger.info("🔥 Executando busca inicial...")
            bot.executar_busca()
        
        # Configurar scheduler
        scheduler = BlockingScheduler()
        
        scheduler.add_job(
            bot.executar_busca,
            trigger=IntervalTrigger(minutes=config.INTERVALO_EXECUCAO_MINUTOS),
            id='buscar_notas',
            name='Buscar notas fiscais',
            replace_existing=True,
            max_instances=1  # Evitar execuções simultâneas
        )
        
        logger.info(
            f"⏰ Agendamento configurado: a cada {config.INTERVALO_EXECUCAO_MINUTOS} minutos"
        )
        logger.info("🤖 Bot rodando... (Ctrl+C para parar)")
        
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("🛑 Bot interrompido pelo usuário")
            scheduler.shutdown()
            
    except Exception as e:
        logger.error(f"❌ Erro fatal ao iniciar bot: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
