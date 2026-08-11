# # 设置项目配置信息，通过环境变量获取

from typing import  Literal

from anyio.functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str='online store'
    app_env: Literal['development', 'production']='development'
    app_v1_prefix:str='/api/v1'
    database_url: str = ''

    access_token_expire_minutes: int = 30
    secret_key: str = "dev-only-change-this-to-a-long-random-20260811"
    jwt_algorithm: Literal["HS256"] = "HS256"

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

# 同一个进程中只创建一次
@lru_cache
def get_settings() -> Settings:
    return Settings()










