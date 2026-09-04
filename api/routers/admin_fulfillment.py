from typing import Annotated

from fastapi import APIRouter, status, HTTPException
from fastapi.params import Query
from sqlalchemy import alias

from api.deps import DatabaseSession, AdminUser
from models.fulfillment import ShipmentStatus, RefusedStatus
from models.order import OrderStatus
from schemas.fulfillment import ShipmentRead, ShipmentCreate, AdminOrderPage, ShipmentEventCreate, RefundRead, \
    AdminRefundPage, RefundReview, RefundCreate
from service import fulfillment as service
from repository import fulfillment as repository

router = APIRouter(prefix="/admin", tags=["管理员权限_相关订单操作"])


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (
            service.FulfillmentOrderNotFoundError,
            service.ShipmentNotFoundError,
            service.RefundNotFoundError)):
        return HTTPException(status_code=404, detail="order, shipment or refund not found")
    if isinstance(exc, service.ShipmentConflictError):
        return HTTPException(status_code=409, detail="shipment conflict")
    if isinstance(exc, (service.FulfillmentStateError, service.RefundStateError)):
        return HTTPException(status_code=409, detail="current state does not allow this operation")
    return HTTPException(status_code=500, detail="unexpected fulfillment error")


@router.post(
    "/orders/{order_id}/ship",
    status_code=status.HTTP_201_CREATED,
    response_model=ShipmentRead,
    summary="生成发货订单"
)
async def create_shipment(
        order_id: int,
        payload: ShipmentCreate,
        db: DatabaseSession,
        admin: AdminUser
) -> ShipmentRead:
    try:
        return ShipmentRead.model_validate(service.ship_order(db, admin.id, order_id, payload))
    except (
            service.FulfillmentOrderNotFoundError,
            service.FulfillmentStateError,
            service.ShipmentConflictError
    ) as exc:
        raise translate_error(exc) from exc


@router.get("/orders/{id}",
            response_model=ShipmentRead,
            summary="查看发货订单详情")
async def get_order_details(
        id: int,
        db: DatabaseSession,
        _: AdminUser
) -> ShipmentRead | None:
    order = repository.get_shipment_by_order(db, id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return ShipmentRead.model_validate(order)


@router.get("/orders/{id}/shipment", summary="查看物流信息",
            response_model=ShipmentRead)
async def get_shipment_details(db: DatabaseSession, id: int, _: AdminUser) -> ShipmentRead | None:
    shipment = repository.get_shipment_by_id(db, id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")
    return ShipmentRead.model_validate(shipment)


# `/api/v1/admin/orders`
@router.get("/orders",
            response_model=AdminOrderPage,
            summary="查询订单分页")
async def get_shipments_list(
        db: DatabaseSession,
        _: AdminUser,
        order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1)] = 10
) -> AdminOrderPage:
    return service.list_orders(db, order_status, page, page_size)


@router.post("/shipments/{shipment_id}/events",
             response_model=ShipmentRead,
             summary="追加物流轨迹")
def add_tracking_event(
        shipment_id: int,
        payload: ShipmentEventCreate,
        _: AdminUser,
        db: DatabaseSession,
) -> ShipmentRead:
    try:
        return ShipmentRead.model_validate(service.add_shipment_event(db, shipment_id, payload))
    except service.ShipmentNotFoundError as exc:
        raise translate_error(exc) from exc


@router.post("/refunds", response_model=AdminRefundPage, summary="查询退款单")
def list_refunds(
        _: AdminUser,
        db: DatabaseSession,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1)] = 10,
        status: Annotated[RefusedStatus | None, Query(alias="status")] = None,
) -> AdminRefundPage:
    return service.list_refused(db, status, page, page_size)


@router.post("/refunds/{refund_id}/approve",
             response_model=RefundRead,
             summary="批准并模拟完成退款"
             )
def approve_refund(
        admin: AdminUser,
        db: DatabaseSession,
        payload: RefundReview,
        refund_id: int,
) -> RefundRead:
    try:
        return RefundRead.model_validate(service.approve_refund(db, admin.id, refund_id, payload))
    except (
            service.RefundNotFoundError,
            service.RefundStateError) as exc:
        raise translate_error(exc) from exc


@router.post("/refunds/{refund_id}/refund",
             response_model=RefundRead,
             summary="拒绝退款")
def refund_order(
        admin: AdminUser,
        db: DatabaseSession,
        payload: RefundReview,
        refund_id: int,
) -> RefundRead:
    try:
      return  RefundRead.model_validate(service.reject_refund(db, admin.id, refund_id, payload))
    except (service.RefundStateError,service.RefundNotFoundError) as exc:
        raise translate_error(exc) from exc
