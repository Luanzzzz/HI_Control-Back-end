from fastapi import APIRouter

router = APIRouter()

@router.get("/debug-status")
def debug_status():
    return {
        "status": "ok",
        "message": "FastAPI is running correctly (no dependencies loaded here)"
    }
