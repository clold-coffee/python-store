
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from models.order import OrderStatus


class AddressCreate(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=80)
    phone:str = Field(min_length=1, max_length=30)
    province:str = Field(min_length=1, max_length=50)
    city:str = Field(min_length=1, max_length=50)
    district:str = Field(min_length=1, max_length=50)
    details:str = Field(min_length=1, max_length=255)
    postal_code: Optional[str] = Field(min_length=None, max_length=20)
    is_default: bool = Field(default=False)


class AddressUpdate(BaseModel):
    recipient_name: Optional[str] = Field(min_length=1, max_length=80)
    phone: Optional[str] = Field(min_length=1, max_length=30)
    province: Optional[str]  = Field(min_length=1, max_length=50)
    city: Optional[str]  = Field(min_length=1, max_length=50)
    district: Optional[str]  = Field(min_length=1, max_length=50)
    details: Optional[str]  = Field(min_length=1, max_length=255)
    postal_code: Optional[str] = Field(min_length=None, max_length=20)
    is_default: Optional[bool]  = Field(default=False)

class AddressRead(AddressCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

class OrderCreate(BaseModel):
    address_id: int

class OrderCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class OrderItemRead(BaseModel):
   model_config = ConfigDict(from_attributes=True)

   id: int
   sku_id: Optional[int] = Field(default=None)
   sku_code: str
   product_name: str
   product_slug: str
   sku_name: str
   attributes: dict[str, object]
   cover_image_url: Optional[str]
   unit_price: Decimal
   quantity: int
   subtotal: Decimal

class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_number: str
    status: OrderStatus
    total_amount:  Decimal = Field(validation_alias="total")
    recipient_name: str
    phone: str
    province: str
    city: str
    district: str
    address_detail: str = Field(validation_alias="address_details")
    postal_code: Optional[str] =None
    cancel_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    canceled_at: Optional[datetime] =None
    items: list[OrderItemRead]


class OrderListItem(BaseModel):
    id: int
    order_number: str
    status: OrderStatus
    total_amount: Decimal
    item_count: int
    first_product_name: str
    first_image_cover_slug: Optional[str]
    created_at: datetime

class OrderPage(BaseModel):
    items: list[OrderListItem]
    total: int
    page: int
    page_size: int
    pages: int