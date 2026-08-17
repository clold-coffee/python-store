
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

# DatabaseSession 表示：这个依赖会从 get_db 函数获取一个 SQLAlchemy 会话对象。
# 这样写可以让函数参数自动接收 db 会话。
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