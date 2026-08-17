from __future__ import annotations



from core.config import get_settings
from core.security import create_access_token

from schemas.auth import Token

from schemas.user import User, CreateUser, LoginRequest
from api.deps import DatabaseSession

from fastapi import status, HTTPException, Depends, APIRouter

from service.auth import EmailAlreadyExistsError, register_user, authenticate_user
router = APIRouter(prefix="/user", tags=["用户相关"])


@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户",
)
def register(paylod: CreateUser, db: DatabaseSession) -> User:
    try:
        return User.model_validate(register_user(db, paylod))
    except EmailAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='邮箱已经注册'
        ) from e


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary='用户登陆'
)
def login(
        from_data: LoginRequest,
        db: DatabaseSession
) -> Token | None:
    user = authenticate_user(from_data.username, from_data.password, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='账号名或密码不正确'
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='用户被禁用'
        )

    setting = get_settings()
    token = create_access_token(subject=str(user.id))
    return Token(
        access_token=token,
        expires_in=setting.access_token_expire_minutes * 60,
    )
