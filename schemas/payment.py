from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.payment import PaymentStatus, DiscountType, UserCouponStatus


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_number: str
    order_id: int
    provider: str
    amount: Decimal
    status: PaymentStatus
    provider_transaction_id: str | None
    created_at: datetime
    paid_at: datetime | None


class PaymentCreate(BaseModel):
    order_id: int

class MockPaymentCallback(BaseModel):
    event_id: str = Field(min_length=8, max_length=80)
    payment_number: str = Field(min_length=8, max_length=80)
    amount: Decimal = Field(ge=0, decimal_places=2)
    status: Literal["succeeded"]
    timestamp: int
    provider_transaction_id: str = Field(min_length=8, max_length=80)


class PaymentCallbackResult(BaseModel):
    accepted: bool = True
    duplicate: bool = False
    payment_status: PaymentStatus
    order_status: str


class CloseExpiredResult(BaseModel):
    closed_count: int


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str
    discount_type: DiscountType
    discount_value: Decimal
    minimum_amount: Decimal
    total_quantity: int
    claimed_quantity: int
    valid_from: datetime
    valid_until: datetime


class UserCouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: UserCouponStatus
    claimed_at: datetime
    used_at: datetime | None
    coupon: CouponRead



class CouponCreate(BaseModel):
    code: str
    name: str
    description: str | None = ""
    discount_type: DiscountType
    discount_value: Decimal
    minimum_amount: Decimal = Decimal("0.00")
    total_quantity: int
    valid_from: datetime
    valid_until: datetime
    is_active: bool = True

