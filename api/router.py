from api.routers.health import router as health_router
from api.routers.auth import router as auth_router
from api.routers.user import router as user_router
from api.routers.admi import router as admi_router
from api.routers.category import router as cat_router
from api.routers.car import router as car_router
from api.routers.address import router as address_router
from api.routers.order import router as order_router
from api.routers.payment import router as payment_router
from api.routers.coupon import router as coupon_router

from fastapi import APIRouter

api_router = APIRouter()

api_router.include_router(coupon_router)

api_router.include_router(payment_router)
api_router.include_router(order_router)

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(admi_router)
api_router.include_router(cat_router)

api_router.include_router(car_router)
api_router.include_router(address_router)



