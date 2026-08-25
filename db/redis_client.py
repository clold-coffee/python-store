
"""创建并向 FastAPI 路由提供 Redis 客户端。"""

from redis import Redis

from core.config import get_settings
from fastapi import Depends
from typing import Annotated

# 从配置对象读取 Redis 地址。get_settings 使用缓存，同一进程不会重复解析配置。
settings = get_settings()

# 创建连接客户端。Redis 通常会在第一次执行命令时才真正建立网络连接。
redis_client = Redis.from_url(
    settings.redis_client_url,
    # 【重点】开启后，hget/hgetall 返回 str，而不是 bytes。
    # repository/cart.py 的 field 转整数和 JSON 解析因此更直观。
    decode_responses=True,
)


def get_redis_client() -> Redis:
    """返回可复用的 Redis 客户端，供 FastAPI 依赖注入。"""
    return redis_client


# 路由写 redis: RedisClient 时，FastAPI 会调用 get_redis_client 获取客户端。
RedisClient = Annotated[Redis, Depends(get_redis_client)]
