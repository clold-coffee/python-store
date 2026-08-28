from typing import Annotated

from fastapi import APIRouter, Header, status, HTTPException, Query

from service import order as service
from api.deps import CurrentUser, DatabaseSession
from db.redis_client import RedisClient
from schemas.order import OrderRead, OrderCreate, OrderPage, OrderCancel
from repository import order as order_repository

router = APIRouter(
    prefix="/order",
    tags=["订单接口"], )


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.AddressNotFoundError):
        return HTTPException(status_code=404, detail="address not found")
    if isinstance(exc, service.EmptyCheckoutError):
        return HTTPException(status_code=409, detail="no selected cart items")
    if isinstance(exc, service.OrderItemUnavailableError):
        return HTTPException(status_code=409, detail=f"item unavailable: {exc.sku_name}")
    if isinstance(exc, service.OrderStockError):
        return HTTPException(status_code=409, detail=f"insufficient stock for {exc.sku_name}: {exc.stock}")
    if isinstance(exc, service.OrderNotFoundError):
        return HTTPException(status_code=404, detail="order not found")
    if isinstance(exc, service.OrderStateError):
        return HTTPException(status_code=409, detail="order status does not allow this operation")
    return HTTPException(status_code=500, detail="unexpected order error")


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED, summary="从已勾选购物车创建订单")
def create_order(
        payload: OrderCreate,
        current_user: CurrentUser,
        db: DatabaseSession,
        redis: RedisClient,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=64)],
) -> OrderRead:
    try:
        order = service.create_order(db, redis, current_user.id, payload.address_id, idempotency_key)
    except (
            service.AddressNotFoundError,
            service.EmptyCheckoutError,
            service.OrderItemUnavailableError,
            service.OrderStockError,
    ) as exc:
        raise translate_error(exc) from exc
    return OrderRead.model_validate(order)


@router.get("/list",
            response_model=OrderPage,
            status_code=status.HTTP_200_OK,
            summary="获取订单列表")
def get_orders(
        current_user: CurrentUser,
        db: DatabaseSession,
        page: Annotated[int, Query(ge=1)] =1,
        page_size: Annotated[int, Query(ge=10)] =10,
) -> OrderPage:
        order_list = service.get_orders_pages(db, current_user.id,page,page_size)
        return order_list

@router.get("/{order_id}",
            response_model=OrderRead,
            status_code=status.HTTP_200_OK,
            summary="查询订单详情")
def get_order_detail(
        order_id: int,
        current_user: CurrentUser,
        db: DatabaseSession,
) -> OrderRead :
        order_item =  order_repository.get_order(db, current_user.id, order_id)
        if  order_item is None:
            raise HTTPException(status_code=404, detail="order not found")
        return OrderRead.model_validate(order_item)



@router.post("/{order_id}/cancel",
            response_model=OrderRead,
            status_code=status.HTTP_202_ACCEPTED,
            summary="取消订单并恢复库存")
def cancel_order(db: DatabaseSession, order_id: int, current_user: CurrentUser,payload:OrderCancel) -> OrderRead:
    try:
      return  OrderRead.model_validate(service.cancel_order(db, current_user.id, order_id,payload.reason))
    except (
        service.OrderNotFoundError,
        service.OrderStockError
    ) as exc:
        raise translate_error(exc) from exc