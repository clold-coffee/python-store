from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DatabaseSession
from schemas.fulfillment import RefundRead, RefundCreate, ShipmentRead
from schemas.order import OrderRead
from service import fulfillment as service
from repository import fulfillment as fulfillment_repository
from repository import order as order_repository

router = APIRouter(
    prefix="/orders",
    tags=["履约与售后"]
)


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc,
                  (service.FulfillmentOrderNotFoundError, service.ShipmentNotFoundError, service.RefundNotFoundError)):
        return HTTPException(status_code=404, detail="order, shipment or refund not found")
    if isinstance(exc, service.ShipmentConflictError):
        return HTTPException(status_code=409, detail="shipment already exists with different tracking information")
    if isinstance(exc, (service.FulfillmentStateError, service.RefundStateError)):
        return HTTPException(status_code=409, detail="current state does not allow this operation")
    return HTTPException(status_code=500, detail="unexpected fulfillment error")


@router.post("/{order_id}/refunds", response_model=RefundRead, status_code=status.HTTP_201_CREATED,
             summary="申请发货前全额退款")
def request_refund(
        order_id: int,
        payload: RefundCreate,
        current_user: CurrentUser,
        db: DatabaseSession,
) -> RefundRead:
    try:
        return RefundRead.model_validate(
            service.request_refund(db, current_user.id, order_id, payload)
        )
    except (service.FulfillmentOrderNotFoundError, service.RefundStateError) as exc:
        raise translate_error(exc) from exc


@router.get("/{order_id}/shipment", summary="查看我的订单物流",
            response_model=ShipmentRead)
async def get_shipment_details(db: DatabaseSession, order_id: int, current_user: CurrentUser) -> ShipmentRead | None:
    order = order_repository.get_order(db, current_user.id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    else:
        shipment = fulfillment_repository.get_shipment_by_order(db, order_id)
        if shipment is None:
            raise HTTPException(status_code=404, detail="shipment not found")
        return ShipmentRead.model_validate(shipment)


@router.get("/{order_id}/refund", response_model=RefundRead, summary="查看退款单")
def get_refund_by_id(db: DatabaseSession, current: CurrentUser, order_id: int) -> RefundRead:
    order = order_repository.get_order(db, current.id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    else:
        refund = fulfillment_repository.get_refund_by_order(db, order_id)
        if refund is None:
            raise HTTPException(status_code=404, detail="shipment not found")
        return RefundRead.model_validate(refund)


# @router.post("/{order_id}/confirm-receipt", response_model=OrderRead, summary="确认收货")
# def confirm_receipt(order_id: uuid.UUID, current_user: CurrentUser, db: DatabaseSession) -> OrderRead:
#     try:
#         return OrderRead.model_validate(service.confirm_receipt(db, current_user.id, order_id))
#     except (service.FulfillmentOrderNotFoundError, service.FulfillmentStateError) as exc:
#         raise translate_error(exc) from exc

@router.post("/{order_id}/confirm-receipt",
             response_model=OrderRead,
             status_code=status.HTTP_201_CREATED,
             summary="确认收货")
def confirm_receipt(
        order_id: int,
        current_user: CurrentUser,
        db: DatabaseSession,
) -> OrderRead:
    try:
        return OrderRead.model_validate(service.confirm_receipt(db, order_id, current_user.id))
    except (service.FulfillmentOrderNotFoundError, service.FulfillmentStateError) as exc:
        raise translate_error(exc) from exc
