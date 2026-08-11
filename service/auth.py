from __future__ import annotations

from asyncio import exceptions
from sqlite3 import IntegrityError

from sentry_sdk.session import Session

from core.security import hash_password, verify_password
from repository.user import get_user_by_email
from schemas.auth import Token
from schemas.user import CreateUser
from models.user import User
from sqlalchemy.exc import IntegrityError


class EmailAlreadyExistsError(Exception):
    pass

# 注册用户
def register_user(db: Session, payload:CreateUser) -> User | None:
    normalize_email = str(payload.email).strip().lower()
    if get_user_by_email (db, normalize_email) is not None:
       raise EmailAlreadyExistsError

    user = User(
        email=normalize_email,
        username=payload.username,
        password=payload.password,
        hashed_password=hash_password(payload.password)
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback();
        raise EmailAlreadyExistsError from exc

    db.refresh(user)
    return user



# 验证用户是否在数据库, 这里逻辑认为  用户名内容  = 邮箱名
def authenticate_user(email:str, password:str, db:Session) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user

