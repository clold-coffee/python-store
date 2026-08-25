from __future__ import annotations

from typing import Annotated

import jwt
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.security import decode_token

from db.session import get_db
from models import User
from fastapi import Depends, status, HTTPException

from models.user import UserRole
from repository.user import get_user_by_id

# oauth2_scheme 是一个 FastAPI 提供的“安全依赖”，它会读取请求头中的 Authorization: Bearer <token>
# 这里的 tokenUrl 是登录接口地址，表示客户端拿不到合法 token 时可去这个地址登录获取。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# 【重点】DatabaseSession 表示：这个依赖会从 get_db 获取一个 SQLAlchemy 会话。
# add_item 路由只需声明 db: DatabaseSession，FastAPI 就会自动创建并注入它。
DatabaseSession = Annotated[Session, Depends(get_db)]


class AccessToken:
    pass


# AccessToken 表示：这个依赖会自动读取 Authorization 头中的 Bearer Token。
AccessToken = Annotated[str, Depends(oauth2_scheme)]


def get_current_user(db: DatabaseSession, token: AccessToken) -> User:
    # 统一的“未授权”错误，后面验证失败时会直接抛出它。
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='token已过期 或 无token',
    )

    try:
        # 解析token，拿到请求体 payload
        payload = decode_token(token)


        if payload.get('type') != 'access':
            raise unauthorized

        subject = payload.get('sub')
        if subject is None:
            raise unauthorized

        user_id = payload.get('sub')
    except (jwt.InvalidTokenError, ValueError) as e:
        raise unauthorized from e

    # 根据解析出的user_id 去数据库查询用户
    user = get_user_by_id(db, user_id)
    if user is None:
        raise unauthorized

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='用户被禁用'
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='当前用户权限不是admin'
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


# 支持游客访问：有 Bearer Token 时解析用户，没有 Token 时返回 None。
# add_item 通过它判断应该使用登录用户购物车还是游客购物车。
def get_optional_current_user(
    db: DatabaseSession,
    token: Annotated[str, Depends(optional_oauth2_scheme)],
) -> User | None:
    """返回当前用户；请求未携带登录 Token 时允许继续并返回 None。"""
    if token is None:
        return None
    # 如果带了 Token，则复用严格的登录校验；无效 Token 仍然返回 401。
    return get_current_user(db, token)


# 【重点：疑似问题】依赖函数可能返回 None，但这里的基础类型只写了 User。
# 为了让类型提示与真实返回值一致，后续可考虑写成 Annotated[User | None, ...]。
OptionalCurrentUser = Annotated[User, Depends(get_optional_current_user)]
