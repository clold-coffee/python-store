
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import UniqueConstraint, String, ForeignKey, Enum as SqlEnum, DateTime, func, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ShipmentStatus(str, Enum):
    IN_TRANSIT = "in_transit"
    DELIVIERED = "delivered"


class RefusedStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("carrier_code", "tracking_number", name="uq_shipments_carrier_tracking"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shipment_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        unique=True,
        index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    carrier_code: Mapped[str] = mapped_column(String(30))
    carrier_name: Mapped[str] = mapped_column(String(80))
    tracking_number: Mapped[str] = mapped_column(String(80))
    status:Mapped[ShipmentStatus] = mapped_column(
        SqlEnum(ShipmentStatus, name="shipment_status", native_enum=False  , length=20),
        default=ShipmentStatus.IN_TRANSIT,
        server_default='IN_TRANSIT',
        index=True
    )
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    events: Mapped[list['ShipmentEvent']] = relationship(
        back_populates="shipment",
        cascade="all, delete, delete-orphan",
        order_by="desc(ShipmentEvent.created_at)",
    )

class ShipmentEvent(Base):
    __tablename__ = "shipment_events"
    __table_args__ = (
        UniqueConstraint("shipment_id", "event_code", name="uq_shipment_events_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"),
        index=True
    )
    event_code: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(120),default="", server_default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shipment: Mapped[Shipment] = relationship(back_populates="events")


class Refund(Base):
    __tablename__ = "refunds"

    id:Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    refund_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        unique=True,
        index=True
    )
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[RefusedStatus] = mapped_column(
        SqlEnum(RefusedStatus, name="refused_status", native_enum=False , length=20),
        default=RefusedStatus.PENDING,
        server_default='PENDING',
        index=True
    )
    admin_note: Mapped[str|None] = mapped_column(String(255),nullable=True)
    reviewed_by: Mapped[int|None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)