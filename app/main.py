"""
Aplicação principal FastAPI - Hi-Control Backend
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.supabase_client import supabase_client

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Criar instância FastAPI
# CRITICAL: redirect_slashes=False prevents 307 redirects that break CORS preflight
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API de gestão contábil integrada Hi-Control com Supabase",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    redirect_slashes=False
)

# Middleware para logar requisições (debug CORS)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests for debugging CORS issues. Skips OPTIONS to avoid noise."""
    if request.method == "OPTIONS":
        return await call_next(request)
        
    logger.info(f"➡️ {request.method} {request.url.path} | Origin: {request.headers.get('origin', 'N/A')}")
    response = await call_next(request)
    logger.info(f"⬅️ {request.method} {request.url.path} | Status: {response.status_code}")
    return response


# Configurar CORS - MUST come AFTER other middlewares to be OUTERMOST
# ✅ SEGURANÇA: CORS restrito a domínios específicos (sem wildcard)
# Usa settings.CORS_ORIGINS para permitir configuração via variáveis de ambiente
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # ✅ allow_origin_regex REMOVIDO - usar apenas lista explícita de origens
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# Incluir routers
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
async def startup_event():
    """Executado ao iniciar a aplicação"""
    logger.info("🚀 Iniciando Hi-Control API")
    logger.info(f"Ambiente: {settings.ENVIRONMENT}")
    logger.info(f"Supabase URL: {settings.SUPABASE_URL}")

    # Testar conexão com Supabase
    try:
        response = supabase_client.table('planos').select("id").limit(1).execute()
        logger.info("✅ Conexão com Supabase estabelecida")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar com Supabase: {e}")

    # Iniciar scheduler de sincronização automática
    try:
        from app.services.scheduler_service import scheduler_service
        scheduler_service.start()
    except Exception as e:
        logger.warning(f"Scheduler não iniciado: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Executado ao desligar a aplicação"""
    # Parar scheduler
    try:
        from app.services.scheduler_service import scheduler_service
        scheduler_service.stop()
    except Exception:
        pass
    logger.info("👋 Encerrando Hi-Control API")


@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "Hi-Control API",
        "version": "1.0.0",
        "status": "online",
        "docs": f"{settings.API_V1_PREFIX}/docs"
    }


@app.get("/health")
async def health_check():
    """Health check da aplicação"""
    try:
        # Verificar conexão com Supabase
        supabase_client.table('planos').select("id").limit(1).execute()

        return {
            "status": "healthy",
            "database": "connected",
            "environment": settings.ENVIRONMENT,
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
