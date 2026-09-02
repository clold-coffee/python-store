# # 设置项目配置信息，通过环境变量获取

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'online store'
    app_env: Literal['development', 'production'] = 'development'
    app_v1_prefix: str = '/api/v1'
    database_url: str = 'mysql+pymysql://root:123456@localhost:3306/online_store'

    access_token_expire_minutes: int = 30 * 24 * 60
    secret_key: str = "dev-only-change-this-to-a-long-random-20260811"
    jwt_algorithm: Literal["HS256"] = "HS256"

    # Redis 连接地址：协议://主机:端口/数据库编号。
    redis_client_url: str = 'redis://localhost:6379/0'

    # 【重点】每次成功修改购物车后重置过期时间。这里是 1 天（秒数）。
    cart_ttl_seconds: int = 60 * 60 * 24 * 1
    # 单个 SKU 在购物车中允许保存的最大数量。
    cart_max_quantity: int = 99

    order_payment_timeout_minutes: int = 30

    mock_payment_secret: str = "dev-mockpay-signing-secret-change-me"
    payment_callback_tolerance_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )


# 同一个进程中只创建一次
@lru_cache
def get_settings() -> Settings:
    """读取环境变量/.env 并返回缓存后的配置对象。"""
    return Settings()
