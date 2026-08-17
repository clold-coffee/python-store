
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



