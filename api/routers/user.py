from fastapi import APIRouter


from api.deps import CurrentUser
from schemas.user import User



router = APIRouter(prefix="/user", tags=["user"])

@router.get('/me', response_model=User, summary='获取用户信息')
def me(current:CurrentUser) -> User:
    return User.model_validate(current)
