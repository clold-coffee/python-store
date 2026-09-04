from cgitb import reset
from datetime import datetime, UTC
from typing import Any

import math
from sqlalchemy import select, null
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models.fulfillment import Shipment, ShipmentStatus, ShipmentEvent, RefusedStatus, Refund
from models.order import Order, OrderStatus
from models.payment import OrderStatusLog, Payment, PaymentStatus
from schemas.fulfillment import  ShipmentCreate, AdminOrderPage, AdminOrderListItem, ShipmentEventCreate, \
    AdminRefundPage, RefundReview, RefundCreate
from repository import (
fulfillment as repository
)

from service.order import OrderNotFoundError
from service.payment import restore_order_stock, PaymentNotFoundError


class FulfillmentOrderNotFoundError(Exception):
    pass


class ShipmentConflictError(Exception):
    pass


class FulfillmentStateError(Exception):
    pass


class CatalogNotFoundError(Exception):
    pass


class CatalogConflictError(Exception):
    pass


class CatalogValidationError(Exception):
    pass


class ShipmentNotFoundError(Exception):
    pass


class RefundNotFoundError(Exception):
    pass


class RefundStateError(Exception):
    pass


def _shipment_number() -> str:
    return f"S{datetime.now(UTC):%Y%m%d%H%M%S}"


def _refund_number() -> str:
    return f"R{datetime.now(UTC):%Y%m%d%H%M%S}"


def ship_order(
        db: Session,
        admin_id: int,
        order_id: int,
        payload: ShipmentCreate,
) -> Shipment:
    try:

        order = db.scalar(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
        )

        if order is None:
            raise OrderNotFoundError
        existing_order = repository.get_shipment_by_order(db, order_id)

        carrier_code = payload.carrier_code.upper()
        tracking_number = payload.tracking_number.upper()

        if existing_order is not None:
            if (
                    existing_order.carrier_code == carrier_code
                    and existing_order.tracking_number == tracking_number
            ):
                return existing_order
            # 这里为什么这么写？因为 除了上面属于重复提交的，其余情况全部视为异常
            raise ShipmentConflictError
        if order.status != OrderStatus.PAID:
            raise FulfillmentStateError

        now = datetime.now()
        shipment = Shipment(
            shipment_number=_shipment_number(),
            order_id=order_id,
            created_by=admin_id,
            carrier_code=payload.carrier_code.upper(),
            carrier_name=payload.carrier_name,
            tracking_number=payload.tracking_number.upper(),
            shipped_at=now,
            events=[
                ShipmentEvent(
                    event_code=f"shipment_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    status="in_transit",
                    destination="商家已发货，等待承运商揽收",
                    location="发货仓",
                    occurred_at=now,
                )
            ]
        )

        order.status = OrderStatus.SHIPPED
        db.add(shipment)
        db.add(
            OrderStatusLog(
                order_id=order_id,
                from_status=OrderStatus.PAID,
                to_status=OrderStatus.SHIPPED,
                operator_type='admin',
                reason=f'shipped via {shipment.carrier_name} {shipment.tracking_number}',
            )
        )
        db.commit()
        return repository.get_shipment_by_order(db, order_id)
    except (
            FulfillmentOrderNotFoundError,
            ShipmentConflictError,
    ):
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        existing_order = repository.get_shipment_by_order(db, order_id)
        if existing_order is not None:
            return existing_order
        raise ShipmentConflictError


def list_orders(
        db: Session,
        status: ShipmentStatus,
        page: int,
        page_size: int,
) -> AdminOrderPage:
    rows, total = repository.list_orders(db, status, page, page_size)

    items = [
        AdminOrderListItem(
            id=order.id,
            order_number=order.order_number,
            user_id=order.user_id,
            status=order.status,
            user_email=email,
            total_amount=order.total,
            item_count=sum(item.quantity for item in order.items),
            created_at=order.created_at,
            shipment_id=shipment_id
        ) for order, email, shipment_id in rows
    ]
    return AdminOrderPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


def add_shipment_event(
        db: Session,
        shipment_id: int,
        payload: ShipmentEventCreate,
) -> Shipment:
    try:
        shipment = db.scalar(
            select(Shipment).options(selectinload(Shipment.events))
            .where(Shipment.id == shipment_id)
            .with_for_update()
        )
        if shipment is None:
            raise ShipmentNotFoundError
        duplicate = next(
            (item for item in shipment.events if item.event_code == payload.event_code), None
        )

        if duplicate is not None:
            return duplicate

        event = ShipmentEvent(
            shipment_id=shipment_id,
            **payload.model_dump()
        )
        db.add(event)
        if payload.status == 'delivered':
            shipment.status = ShipmentStatus.DELIVIERED
            shipment.delivered_at = payload.occurred_at
        db.commit()
        return repository.get_shipment_by_order(db, shipment.order_id)
    except  ShipmentNotFoundError:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        shipment = db.scalar(
            select(Shipment).where(Shipment.id == shipment_id)
        )
        if shipment is None:
            raise ShipmentNotFoundError
        return repository.get_shipment_by_order(db, shipment.order_id)


def list_refused(
        db: Session,
        status: RefusedStatus | None,
        page: int,
        page_size: int,
) -> AdminRefundPage:
    rows, total = repository.list_refused(db, page, page_size, status)
    return AdminRefundPage(
        items=rows,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


def request_refund(
        db: Session,
        user_id: int,
        order_id: int,
        payload: RefundCreate
) -> Refund:
    exciting = repository.get_refund_by_order(db, order_id)
    if exciting is not None and exciting.user_id == user_id:
        db.rollback()
        return exciting
    try:
        order = db.scalar(
            select(Order)
            .where(
                Order.id == order_id,
                Order.user_id == user_id,
            )
            .with_for_update()
        )
        if order is None:
            raise OrderNotFoundError
        if order.status != OrderStatus.PAID:
            raise RefundStateError

        payment = db.scalar(
            select(Payment)
            .where(Payment.order_id == order.id, Payment.status == PaymentStatus.SUCCEEDED)
            .with_for_update()
        )
        if payment is None:
            raise PaymentNotFoundError

        refund = Refund(
            refund_number=_refund_number(),
            order_id=order_id,
            payment_id=payment.id,
            user_id=user_id,
            amount=payment.amount,
            reason=payload.reason,
        )

        order.status = OrderStatus.REFUNDING
        db.add(refund)
        db.add(OrderStatusLog(
            order_id=order.id,
            from_status=OrderStatus.PAID,
            to_status=OrderStatus.REFUNDING,
            operator_type="customer",
            reason=payload.reason,
        ))
        db.commit()
        db.refresh(refund)
        return refund
    except(OrderNotFoundError,
           PaymentNotFoundError,
           RefundNotFoundError,
           ):
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        duplicate = repository.get_refund_by_order(db, order_id)
        if duplicate is not None and duplicate.user_id == user_id:
            return duplicate
        raise


def approve_refund(
        db: Session,
        admin_id: int,
        refund_id: int,
        payload: RefundReview
) -> Refund:
    try:
        refund = db.scalar(
            select(Refund).where(Refund.id == refund_id).with_for_update()
        )
        if refund is None:
            raise RefundNotFoundError

        if refund.status == RefusedStatus.SUCCEEDED:
            db.rollback()
            return refund

        if refund.status != RefusedStatus.PENDING:
            raise RefundStateError

        order = db.scalar(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == refund.order_id)
            .with_for_update()
        )

        payment = db.scalar(
            select(Payment).where(Payment.id == refund.payment_id)
            .with_for_update()
        )
        if (
                order is None or payment is None
                or order.status != OrderStatus.REFUNDING
                or payment.status != PaymentStatus.SUCCEEDED
        ):
            raise RefundStateError

        now = datetime.now(UTC)
        restore_order_stock(db, order)
        refund.status = RefusedStatus.SUCCEEDED
        refund.admin_note = payload.note
        refund.reviewed_by = admin_id
        refund.reviewed_at = now
        refund.completed_at = now
        order.status = OrderStatus.REFUNDED
        db.add(OrderStatusLog(
            order_id=order.id,
            from_status=OrderStatus.REFUNDED,
            to_status=OrderStatus.REFUNDED,
            operator_type='admin',
            reason=payload.note or "refund approved",
        ))
        db.commit()
        db.refresh(refund)
        return refund
    except (RefundStateError, RefundNotFoundError):
        db.rollback()
        raise


def reject_refund(
        db: Session,
        admin_id: int,
        refund_id: int,
        payload: RefundReview
) -> Refund:
    try:
        refund = db.scalar(
            select(Refund).where(Refund.id == refund_id).with_for_update()
        )
        if refund is None:
            raise RefundNotFoundError

        if refund.status == RefusedStatus.REJECTED:
            db.rollback()
            return refund

        if refund.status != RefusedStatus.PENDING:
            raise RefundStateError


        order = db.scalar(select(Order).where(Order.id == refund.order_id).with_for_update())
        if (order is None or order.status != OrderStatus.REFUNDING):
            raise RefundStateError

        now = datetime.now(UTC)
        restore_order_stock(db, order)

        refund.status = RefusedStatus.REJECTED
        refund.admin_note = payload.note
        refund.reviewed_by = admin_id
        refund.reviewed_at = now
        refund.completed_at = now
        order.status = OrderStatus.PAID
        db.add(OrderStatusLog(
            order_id=order.id,
            from_status=OrderStatus.REFUNDED,
            to_status=OrderStatus.PAID,
            operator_type='admin',
            reason=payload.note or "refund rejected",
        ))
        db.commit()
        db.refresh(refund)
        return refund
    except (RefundStateError, RefundNotFoundError):
        db.rollback()
        raise

def confirm_receipt(
        db: Session,
        order_id: int,
        user_id: int,
) -> Order:
    # 1.查询订单是否存在，再确认物流订单是否存在。2.判断物流【订单状态】是否已经【确认收货】
    # 3.生成物流时间事务、订单日志
    # 4.提交事务
    # 5.如果有 IntegrityError 错误，那么数据库需要回滚，并查询最新数据状态
    try:
        order = db.scalar(
            select(Order).options(selectinload(Order.items)).where(
                Order.id == order_id, Order.user_id == user_id
            ).with_for_update()
        )
        if order is None:
            raise OrderNotFoundError
        if order.status == OrderStatus.COMPLETED:
            db.rollback()
            return order
        if order.status != OrderStatus.SHIPPED:
            raise FulfillmentStateError

        shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id).with_for_update())
        now = datetime.now(UTC)

        if shipment is not None and shipment.status != ShipmentStatus.DELIVIERED:
            shipment.status = ShipmentStatus.DELIVIERED
            shipment.delivered_at = now
            shipment_event = ShipmentEvent(
                shipment_id=shipment.id,
                event_code=f"shipment_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                status=ShipmentStatus.DELIVIERED,
                location="收货地址",
                occurred_at=now,
                description="用户确认收货",
            )
            db.add(shipment_event)

        order.status = OrderStatus.COMPLETED
        db.add(
            OrderStatusLog(
                order_id=order_id,
                from_status=OrderStatus.SHIPPED,
                to_status=OrderStatus.CANCELED,
                operator_type='customer',
                reason="customer confirmed receipt",
            )
        )
        db.commit()
        return db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
    except (FulfillmentOrderNotFoundError, FulfillmentStateError):
        db.rollback()
        raise

