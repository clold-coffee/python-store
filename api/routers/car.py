"""购物车 HTTP 接口。

``add_item`` 的主调用链（建议先记住这一条，再阅读细节）：

    HTTP 请求
      -> FastAPI 校验 CartItemAdd
      -> FastAPI 注入 CurrentCart / DatabaseSession / RedisClient
      -> service.add_to_cart 执行业务校验
      -> repository.add_item 写入 Redis
      -> service.build_cart 组装响应
      -> FastAPI 按 CartRead 输出 JSON

阅读标记：``【重点】`` 是初学阶段需要掌握的内容，``【进阶】`` 可以在理解
主流程后再学习，``【重点：疑似问题】`` 表示代码当前可能存在逻辑或命名问题。
"""

# 【注意】该导入当前没有被使用；它与下面自定义的 translate_error 无关。
from fnmatch import translate
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Response, Header

# 请求体与响应体的数据模型。
from schemas.car import CartRead, CartItemAdd, CartItemUpdate, CartSelectionUpdate
# Service 层负责业务规则；路由层不直接操作数据库或 Redis。
from service import cart as service
# 下面三个类型别名都使用 FastAPI 的 Depends，在请求到来时自动提供参数值。
from api.cart_deps import CurrentCart
from api.deps import DatabaseSession, CurrentUser
from db.redis_client import RedisClient
# Repository 中定义了 Redis 并发更新异常，路由层需要把它翻译为 HTTP 错误。
from repository import cart as cart_repository

from core.config import get_settings

getSettings = get_settings()

# 所有本文件接口都会带有 /car 前缀，并在接口文档中归入“购物车”分组。
router = APIRouter(prefix="/car", tags=["购物车"])

def translate_error(exc: Exception) -> HTTPException:
    """把 Python 业务异常翻译成客户端能理解的 HTTP 异常。

    【重点】分层项目中，Service/Repository 不应依赖 HTTP 状态码；它们只抛出
    业务异常。Router 在最外层统一决定返回 404、409 还是 500。

    Args:
        exc: Service 或 Repository 抛出的原始异常。

    Returns:
        带有状态码和错误信息的 FastAPI ``HTTPException``。
    """
    # 404：目标购物车项不存在。
    if isinstance(exc, service.CartItemNotFoundError):
        return HTTPException(status_code=404, detail="cart item not found")
    # 409：SKU 已下架、被禁用或不存在，当前请求与商品状态冲突。
    if isinstance(exc, service.CartSkuUnavailableError):
        return HTTPException(status_code=409, detail="SKU is not available")
    # 409：想加入的数量超过允许值；stock 属性携带可用上限。
    if isinstance(exc, service.CartStockError):
        return HTTPException(status_code=409, detail=f"available stock is {exc.stock}")
    # 409：Redis 乐观锁连续失败，提示客户端稍后重试。
    if isinstance(exc, cart_repository.CartConcurrentUpdateError):
        return HTTPException(status_code=409, detail="cart was updated concurrently, please retry")
    # 未识别的异常不能把内部细节直接暴露给客户端。
    return HTTPException(status_code=500, detail="unexpected cart error")


@router.get("", summary="读取 Redis 中的购物车数据")
def read_cart(cart: CurrentCart, db: DatabaseSession, redis: RedisClient):
    """读取当前用户或游客的购物车。此函数也被加入成功后的响应流程复用。"""
    return service.build_cart(db, redis, cart.key)


@router.post(
    "/items",
    response_model=CartRead,
    status_code=status.HTTP_201_CREATED,
    summary="加入购物车",
)
def add_item(
    payload: CartItemAdd,
    cart: CurrentCart,
    db: DatabaseSession,
    redis: RedisClient,
) -> CartRead:
    """将指定数量的 SKU 加入当前购物车，并返回更新后的完整购物车。

    参数并不是手动创建的：

    - ``payload``：FastAPI 读取 JSON 请求体并用 ``CartItemAdd`` 校验；
    - ``cart``：依赖根据登录用户或 ``X-Cart-Token`` 生成 Redis key；
    - ``db``：本次请求使用的 SQLAlchemy Session；
    - ``redis``：全局 Redis 连接客户端。

    【重点】这个路由只做三件事：接收输入、调用业务层、转换异常。真正的
    “SKU 是否可售、数量是否允许、怎样并发写 Redis”分别在 Service 和
    Repository 中完成。
    """
    try:
        # 第一步：让 Service 校验商品，并让 Repository 更新 Redis。
        # payload 已通过 Pydantic 校验，所以 quantity 正常情况下在 1~99 之间。
        service.add_to_cart(db, redis, cart.key, payload.sku_id, payload.quantity)
    except (
        service.CartStockError,
        service.CartSkuUnavailableError,
        cart_repository.CartConcurrentUpdateError,
    ) as exc:
        # 第二步（失败分支）：将底层异常转换为统一的 HTTP 409 响应。
        # ``raise ... from exc`` 会保留原始异常链，方便服务端排查问题。
        raise translate_error(exc) from exc

    # 第二步（成功分支）：重新读取 Redis，并结合数据库中的价格、库存等信息，
    # 返回“更新后的完整购物车”，而不只是刚加入的那一项。
    return service.build_cart(db, redis, cart.key)


@router.patch(
    "/items/{sku_id}",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="修改数量或勾选状态",
)
def update_item(
        sku_id: int,
        payload: CartItemUpdate,
        cart: CurrentCart,
        db: DatabaseSession,
        redis: RedisClient,
) -> CartRead:
    try:
        service.update_cart_item(
            db,
            redis,
            cart.key,
            sku_id,
            payload.quantity,
            payload.selected
        )
    except (
        service.CartStockError,
        service.CartSkuUnavailableError,
        service.CartItemNotFoundError,
        cart_repository.CartConcurrentUpdateError,
    ) as exc:
        raise translate_error(exc) from exc
    return service.build_cart(db, redis, cart.key)


@router.delete(
    "/items/{sku_id}",
    response_model=CartRead,
    summary="删除购物车",
)
def delete_item(
        sku_id: int,
        cart: CurrentCart,
        db: DatabaseSession,
        redis: RedisClient,
) -> CartRead:
    if not cart_repository.remove_item(redis, cart.key, sku_id ):
        raise  HTTPException(status_code=404, detail="cart item not found")
    return service.build_cart(db, redis, cart.key)






@router.patch(
    "/selection",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="批量勾选"
)
def update_selection(
        payload: CartSelectionUpdate,
        cart: CurrentCart,
        db: DatabaseSession,
        redis: RedisClient,
) -> CartRead:
    try:
        cart_repository.update_selection(
            redis,
            cart.key,
            selected = payload.selected,
            sku_ids = payload.sku_ids,
            ttl=getSettings.cart_ttl_seconds
        )
    except cart_repository.CartConcurrentUpdateError as exc:
        raise translate_error(exc) from exc
    return service.build_cart(db, redis, cart.key)


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="清空购物车"
)
def clear_cart(
        cart: CurrentCart,
        redis: RedisClient,
) -> Response:
    cart_repository.clear_cart(redis, cart.key)
    return Response(
        status_code=status.HTTP_200_OK,
        content ="ok "
    )



@router.get(
    "/merge",
    response_model=CartRead,
    summary="登录后合并有课购物车"
)
def merge_guest_cart(
        current_user: CurrentUser,
        redis: RedisClient,
        db: DatabaseSession,
        cart_token: Annotated[str,   Header(alias="X-Cart-Token")]
) -> CartRead:
    try:
        guest_token = str(cart_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Cart-Token"
        ) from exc

    try:
        cart_repository.merge_carts(
            redis,
            service.guest_cart_key(guest_token),
            service.user_cart_key(current_user.id),
            max_quantity= getSettings.cart_max_quantity,
            ttl=getSettings.cart_ttl_seconds
        )
    except cart_repository.CartConcurrentUpdateError as exc:
        raise translate_error(exc) from exc
    return service.build_cart(db, redis, service.user_cart_key(current_user.id))