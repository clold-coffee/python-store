
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    Enum as SqlEnum,
    String,
    Numeric,
    Integer,
    DateTime,
    Boolean,
    func,
    UniqueConstraint,
    Index,
    ForeignKey,
    Any, JSON
)

from db.base import Base
from models.order import OrderStatus


class DiscountType(str, enum.Enum):
    Fixed = 'fixed'
    PERCENT = 'percent'


class UserCouponStatus(str, enum.Enum):
    AVAILABLE = 'available'
    USED = 'used'
    EXPIRED = 'expired'


class PaymentStatus(str, enum.Enum):
    PENDING = 'pending'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CLOSED = 'closed'
    REFUNDED = 'refunded'


class Coupon(Base):
    __tablename__ = 'coupons'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255), default='', server_default='')
    discount_type: Mapped[str] = mapped_column(
        SqlEnum(DiscountType, name="discount_type", native_enum=False, length=20)
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    minimum_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal('0'))
    total_quantity: Mapped[int] = mapped_column(Integer)
    claimed_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserCoupon(Base):
    __tablename__ = 'user_coupons'
    __table_args__ = (
        UniqueConstraint('user_id', 'coupon_id', name='uq_user_coupons_user_coupon'),
        Index('ix_user_coupons_user_status', 'user_id', 'status'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete='CASCADE'), index=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey('coupons.id', ondelete='RESTRICT'), index=True)
    status: Mapped[UserCouponStatus] = mapped_column(
        SqlEnum(UserCouponStatus, name="user_coupons_status", native_enum=False, length=20),
        default=UserCouponStatus.AVAILABLE,
        server_default='AVAILABLE',
    )
    claimed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    coupon: Mapped[Coupon] = relationship()


class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = (
        UniqueConstraint('user_id', 'client_request_id', name='uq_user_payments_user_request'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey('orders.id', ondelete='RESTRICT'), index=True, unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'), index=True)
    provider: Mapped[str] = mapped_column(String(30), default='mockpay', server_default='mockpay')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[PaymentStatus] = mapped_column(
        SqlEnum(PaymentStatus, name="payment_status", native_enum=False, length=20),
        default=PaymentStatus.PENDING,
        server_default='PENDING',
        index=True
    )
    client_request_id: Mapped[str] = mapped_column(String(64))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class PaymentCallback(Base):
    __tablename__ = 'payment_callbacks'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey('payments.id', ondelete='CASCADE'), index=True, unique=True
    )
    signature: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OrderStatusLog(Base):
    __tablename__ = 'order_status_logs'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), index=True)
    from_status: Mapped[OrderStatus|None] = mapped_column(
        SqlEnum(OrderStatus, name="order_log_from_status", native_enum=False, length=30),
        nullable=True,
    )
    to_status: Mapped[OrderStatus|None] = mapped_column(
        SqlEnum(OrderStatus, name="order_log_to_status", native_enum=False, length=30),
    )
    operator_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(255), default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
