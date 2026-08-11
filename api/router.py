from api.routers.health import router as health_router
from api.routers.auth import router as auth_router

from fastapi import APIRouter

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
