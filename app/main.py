"""
Aplicacao principal FastAPI - Hi-Control Backend.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.supabase_client import supabase_client

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def _is_serverless_runtime() -> bool:
    return os.getenv("VERCEL") == "1" or bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown centralizado em lifespan."""
    logger.info("Iniciando Hi-Control API")
    logger.info("Ambiente: %s", settings.ENVIRONMENT)
    logger.info("Supabase URL: %s", settings.SUPABASE_URL)

    is_serverless = _is_serverless_runtime()

    if is_serverless:
        logger.info("Runtime serverless detectado: pulando scheduler/worker de background")
    else:
        # Teste de conectividade somente fora de serverless.
        try:
            supabase_client.table("planos").select("id").limit(1).execute()
            logger.info("Conexao com Supabase estabelecida")
        except Exception as e:  # noqa: BLE001
            logger.error("Erro ao conectar com Supabase: %s", e)

        # Scheduler existente (email/drive)
        try:
            from app.services.scheduler_service import scheduler_service

            scheduler_service.start()
        except Exception as e:  # noqa: BLE001
            logger.warning("Scheduler nao iniciado: %s", e)

        # Worker de captura SEFAZ em thread separada
        try:
            from app.worker.sync_worker import start_worker

            start_worker()
        except Exception as e:  # noqa: BLE001
            logger.warning("Worker de captura SEFAZ nao iniciado: %s", e)

    # Logar rotas registradas para verificacao operacional
    for route in app.router.routes:
        path = getattr(route, "path", "")
        name = getattr(route, "name", "")
        methods = ",".join(sorted(getattr(route, "methods", []) or []))
        logger.info("router include | path=%s | methods=%s | name=%s", path, methods, name)

    try:
        yield
    finally:
        if not is_serverless:
            try:
                from app.worker.sync_worker import stop_worker

                stop_worker()
            except Exception:  # noqa: BLE001
                pass

            try:
                from app.services.scheduler_service import scheduler_service

                scheduler_service.stop()
            except Exception:  # noqa: BLE001
                pass

        logger.info("Encerrando Hi-Control API")


# Criar instancia FastAPI
# CRITICAL: redirect_slashes=False prevents 307 redirects that break CORS preflight
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API de gestao contabil integrada Hi-Control com Supabase",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    redirect_slashes=False,
    lifespan=lifespan,
)


# Middleware para logar requisicoes (debug CORS)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests for debugging CORS issues. Skips OPTIONS to avoid noise."""
    if request.method == "OPTIONS":
        return await call_next(request)

    logger.info("-> %s %s | Origin: %s", request.method, request.url.path, request.headers.get("origin", "N/A"))
    response = await call_next(request)
    logger.info("<- %s %s | Status: %s", request.method, request.url.path, response.status_code)
    return response


# Configurar CORS - MUST come AFTER other middlewares to be OUTERMOST
# allow_origin_regex matches Vercel production AND preview URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Incluir routers
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "message": "Hi-Control API",
        "version": "1.0.0",
        "status": "online",
        "docs": f"{settings.API_V1_PREFIX}/docs",
    }


@app.get("/health")
async def health_check():
    """Health check da aplicacao."""
    try:
        # Verificar conexao com Supabase
        supabase_client.table("planos").select("id").limit(1).execute()

        return {
            "status": "healthy",
            "database": "connected",
            "environment": settings.ENVIRONMENT,
            "version": "1.0.0",
        }
    except Exception as e:  # noqa: BLE001
        logger.error("Health check falhou: %s", e)
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
