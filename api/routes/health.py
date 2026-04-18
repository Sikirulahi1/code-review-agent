from fastapi import APIRouter, HTTPException

from db import verify_database_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    try:
        await verify_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "api": "ok",
                "database": "down",
            },
        ) from exc

    return {
        "status": "ok",
        "api": "ok",
        "database": "ok",
    }
