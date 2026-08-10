# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
#
# from app.api.router import api_router
# from app.core.config import get_settings
#
#
# def create_app() -> FastAPI:
#     """应用工厂：集中创建和配置 FastAPI 实例。"""
#     settings = get_settings()
#
#     application = FastAPI(
#         title=settings.app_name,
#         version="0.1.0",
#         description="线上商城实战教程 API",
#     )
#
#     # 设置允许访问的来源
#     application.add_middleware(
#         CORSMiddleware,
#         allow_origins=[settings.frontend_origin],
#         allow_credentials=True,
#         allow_methods=["*"],
#         allow_headers=["*"],
#     )
#
#     application.include_router(api_router, prefix=settings.api_v1_prefix)
#     return application
#
#
# app = create_app()






from fastapi import FastAPI
from api.router import api_router
from core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI()
    settings = get_settings()
    print(settings)


    # 加载路由
    app.include_router(api_router)
    return app

app = create_app()



