from api.routers.health import router as health_router
from api.routers.auth import router as auth_router
from api.routers.user import router as user_router
from api.routers.admi import router as admi_router
from api.routers.category import router as cat_router

from fastapi import APIRouter

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(admi_router)
api_router.include_router(cat_router)

