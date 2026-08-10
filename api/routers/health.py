# 检查前端是否能访问
# 检查数据库是否能访问


from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Literal
from db.session import check_database
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/health", tags=["检查系统连接"])


class HealthResponse(BaseModel):
    status: Literal['ok']
    # environment: str


class DataBaseHealthResponse(BaseModel):
    status: Literal['ok']
    database: Literal['connect']


@router.get("")
def health() -> HealthResponse:
    return HealthResponse(
        status='ok'
    )


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
