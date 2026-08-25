# 检查前端是否能访问
# 检查数据库是否能访问


from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from redis import RedisError

from db.session import check_database
from sqlalchemy.exc import SQLAlchemyError
from db.redis_client import RedisClient

router = APIRouter(prefix="/health", tags=["检查系统连接"])


class HealthResponse(BaseModel):
    status: Literal['ok']
    # environment: str


class DataBaseHealthResponse(BaseModel):
    status: Literal['ok']
    database: Literal['connect']


# 检查能否访问服务
@router.get("")
def health() -> HealthResponse:
    return HealthResponse(
        status='ok'
    )


# 检查数据库连接是否正常
@router.get("/database")
def database() -> DataBaseHealthResponse:
    try:
        check_database()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        ) from exc

    return DataBaseHealthResponse(
        status='ok',
        database='connect'
    )


class RedisHealthResponse(BaseModel):
    status: Literal["ok"]
    redis: Literal["connected"]


# 检查Redis是否连接正常
@router.get("/redis")
def redis_health_check(redis: RedisClient) -> RedisHealthResponse:
    try:
        redis.ping()
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        )
    return RedisHealthResponse(
        status='ok',
        redis='connected'
    )
