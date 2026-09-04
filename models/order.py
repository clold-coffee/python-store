from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import (
    ForeignKey, String, DateTime, func, UniqueConstraint, Index,
    Enum as SqlEnum, Numeric,
    JSON,
    Boolean, Integer
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.config import get_settings
from db.base import Base


PAYMENT_EXPIRY_MINUTES = get_settings().order_payment_timeout_minutes


def default_payment_expires_at() -> datetime:
    """新订单默认在 30 分钟后过期。"""
    return datetime.now() + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)


class OrderStatus(str, Enum):
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    CANCELED = 'canceled'
    SHIPPED = 'shipped'
    COMPLETED = 'completed'
    SUCCEEDED = 'succeeded'
    REFUNDED = "refunded"
    REFUNDING="refunding"


class Address(Base):
    __tablename__ = 'addresses'

    id: Mapped[int] = mapped_column(Integer, primary_key=True,autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete="CASCADE"), index=True)
    recipient_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30))
    province: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50))
    district: Mapped[str] = mapped_column(String(50))
    details: Mapped[str] = mapped_column(String(255))
    postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 解释 __table_args__ 代码
class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        UniqueConstraint('user_id', 'idempotency_key', name='uq_orders_user_idempotency'),
        Index("ix_orders_user_created", "user_id", 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True,autoincrement=True)
    order_number: Mapped[int] = mapped_column(String(32), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete="RESTRICT", ),
        index=True)
    status: Mapped[OrderStatus] = mapped_column(
        SqlEnum(OrderStatus, name='order_status', native_enum=False, length=30),
        default=OrderStatus.PENDING_PAYMENT,
        server_default="PENDING_PAYMENT",
        index=True
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    recipient_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30))
    province: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50))
    district: Mapped[str] = mapped_column(String(50))
    address_details: Mapped[str] = mapped_column(String(255))
    postal_code: Mapped[str] = mapped_column(String(20), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    canceled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    payment_expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=default_payment_expires_at,
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    items: Mapped[list['OrderItem']] = relationship(
        back_populates='order',
        cascade='all, delete, delete-orphan',
        order_by='desc(OrderItem.id)',
    )


class OrderItem(Base):
    __tablename__ = 'order_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey('orders.id', ondelete="CASCADE"),
        index=True)
    sku_id:Mapped[int] = mapped_column(
        ForeignKey('product_skus.id', ondelete="SET NULL"),
        index=True, nullable=True)
    sku_code: Mapped[str] = mapped_column(String(255))
    product_name: Mapped[str] = mapped_column(String(255))
    product_slug: Mapped[str] = mapped_column(String(255))
    sku_name: Mapped[str] = mapped_column(String(255))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON)
    cover_image_url: Mapped[str] = mapped_column(String(255), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped[Order] = relationship(back_populates='items')
