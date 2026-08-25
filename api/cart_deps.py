"""确定一次请求应该使用哪一个购物车 Redis key。"""

from dataclasses import dataclass
from typing import Annotated
from fastapi import (
    Header,
    HTTPException,
    Depends,
    status
)

from api.deps import OptionalCurrentUser
from service.cart import user_cart_key, guest_cart_key


@dataclass(frozen=True)
class CartIdentity:
    """当前购物车的身份信息。

    ``frozen=True`` 表示对象创建后不可修改，避免请求处理中途误换购物车。
    """

    # 最终传给 Repository 的 Redis key。
    key: str
    # True 表示游客购物车，False 表示登录用户购物车。
    is_guest: bool


def get_cart_identity(
    current_user: OptionalCurrentUser,
    cart_token: Annotated[str, Header(alias="X-Cart-Token")] = None,
) -> CartIdentity:
    """优先按登录用户确定购物车；未登录时使用游客 Token。

    【重点】同一个 ``add_item`` 接口同时支持两类访问者：

    - 已登录：Redis key 来自用户 ID，不需要 X-Cart-Token；
    - 游客：没有用户 ID，必须由请求头提供 X-Cart-Token。

    FastAPI 会先执行本函数，再把返回的 ``CartIdentity`` 注入路由的 cart 参数。
    """
    # 登录状态优先。即使同时传了游客 Token，也使用用户购物车。
    if current_user is not None:
        return CartIdentity(key=user_cart_key(current_user.id), is_guest=False)

    # 未登录且没有游客 Token，无法确定购物车归属，直接终止请求。
    if cart_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Cart-Token is required for guest cart",
        )

    try:
        # 【重点：疑似问题】这里只把字符串赋给另一个变量，不会触发 ValueError，
        # 所以下面的 except 实际无法校验 Token 格式。若 Token 有格式要求，应在
        # try 中执行真正的转换或验证。
        token = cart_token
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid X-Cart-Token"
        ) from exc
    # guest_cart_key 给 Token 加统一前缀，避免与用户购物车 key 冲突。
    return CartIdentity(key=guest_cart_key(token), is_guest=True)


# 【进阶】Annotated 把“Python 类型”和“如何获得它”绑在一起。
# 路由写 cart: CurrentCart 时，FastAPI 实际会先调用 get_cart_identity。
CurrentCart = Annotated[CartIdentity, Depends(get_cart_identity)]
