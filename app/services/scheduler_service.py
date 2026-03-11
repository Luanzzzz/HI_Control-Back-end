"""
Serviço de agendamento de tarefas periódicas.

Usa APScheduler para:
- Sincronização de emails a cada 30 minutos
- Sincronização de Google Drive a cada 1 hora
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Flag para controle de concorrência
_syncing_configs = set()


class SchedulerService:
    """Gerencia jobs periódicos de sincronização."""

    _instance = None
    _scheduler = None
    _started = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def start(self):
        """Inicia o scheduler."""
        if self._started:
            return

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler()

            # Job de sincronização de emails - a cada 30 minutos
            self._scheduler.add_job(
                self._sync_all_emails,
                "interval",
                minutes=30,
                id="email_sync",
                name="Sincronização de Emails",
                replace_existing=True,
                max_instances=1,
            )

            # Job de sincronização de Drive - a cada 1 hora
            self._scheduler.add_job(
                self._sync_all_drives,
                "interval",
                minutes=60,
                id="drive_sync",
                name="Sincronização de Google Drive",
                replace_existing=True,
                max_instances=1,
            )

            self._scheduler.start()
            self._started = True
            logger.info("Scheduler iniciado com sucesso")
            logger.info("  - Email sync: a cada 30 minutos")
            logger.info("  - Drive sync: a cada 60 minutos")

        except ImportError:
            logger.warning(
                "APScheduler não instalado. Sincronização automática desabilitada. "
                "Instale com: pip install apscheduler"
            )
        except Exception as e:
            logger.error(f"Erro ao iniciar scheduler: {e}")

    def stop(self):
        """Para o scheduler."""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Scheduler encerrado")

    async def _sync_all_emails(self):
        """Sincroniza todos os emails configurados e ativos."""
        from app.db.supabase_client import get_supabase_admin
        from app.services.email_import_service import email_import_service

        logger.info("Iniciando sincronização automática de emails...")

        try:
            db = get_supabase_admin()
            configs = (
                db.table("configuracoes_email")
                .select("id, user_id")
                .eq("ativo", True)
                .execute()
            )

            if not configs.data:
                return

            for config in configs.data:
                config_key = f"email_{config['id']}"
                if config_key in _syncing_configs:
                    logger.info(f"Email config {config['id']} já em sincronização, pulando")
                    continue

                _syncing_configs.add(config_key)
                try:
                    await email_import_service.sincronizar(
                        config_id=config["id"],
                        user_id=config["user_id"],
                    )
                except Exception as e:
                    logger.error(
                        f"Erro ao sincronizar email {config['id']}: {e}"
                    )
                finally:
                    _syncing_configs.discard(config_key)

        except Exception as e:
            logger.error(f"Erro na sincronização automática de emails: {e}")

    async def _sync_all_drives(self):
        """Sincroniza todas as configurações de Drive ativas."""
        from app.db.supabase_client import get_supabase_admin
        from app.services.google_drive_service import google_drive_service

        logger.info("Iniciando sincronização automática de Google Drive...")

        try:
            db = get_supabase_admin()
            configs = (
                db.table("configuracoes_drive")
                .select("id, user_id")
                .eq("ativo", True)
                .execute()
            )

            if not configs.data:
                return

            for config in configs.data:
                config_key = f"drive_{config['id']}"
                if config_key in _syncing_configs:
                    logger.info(f"Drive config {config['id']} já em sincronização, pulando")
                    continue

                _syncing_configs.add(config_key)
                try:
                    await google_drive_service.sincronizar(
                        config_id=config["id"],
                        user_id=config["user_id"],
                    )
                except Exception as e:
                    logger.error(
                        f"Erro ao sincronizar Drive {config['id']}: {e}"
                    )
                finally:
                    _syncing_configs.discard(config_key)

        except Exception as e:
            logger.error(f"Erro na sincronização automática de Drive: {e}")


# Singleton
scheduler_service = SchedulerService()
