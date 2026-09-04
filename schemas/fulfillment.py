from datetime import datetime, UTC
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.fulfillment import ShipmentStatus, ShipmentEvent, RefusedStatus
from models.order import OrderStatus


# 本文件存放“数据模型（Schema）”。
# 可以先把 Schema 理解成接口数据的说明书：
# 1. 客户端提交数据时，Pydantic 会按照说明书检查数据是否合法；
# 2. 接口返回数据时，Pydantic 会按照说明书整理最终的 JSON 结构。


# 【入门】单条物流轨迹的返回结构，例如“快件已到达杭州转运中心”。
class ShipmentEventRead(BaseModel):
    # 开启 from_attributes 后，既可以读取字典，也可以读取 SQLAlchemy 对象的属性。
    # 例如：ShipmentEventRead.model_validate(shipment_event_orm_object)。
    model_config = ConfigDict(from_attributes=True)
    # 本次物流事件的唯一业务编号。
    event_code: str
    # 物流节点状态，例如 in_transit（运输中）。
    status: str
    # 对当前物流进度的文字描述。
    destination: str
    # 事件发生地点。
    location: str
    # 事件实际发生的时间。
    occurred_at: datetime


# 【入门 → 进阶】一张发货单的完整返回结构。
class ShipmentRead(BaseModel):
    # ShipmentRead 通常接收 SQLAlchemy 查询得到的 Shipment 对象，
    # 因此也需要开启 from_attributes。
    model_config = ConfigDict(from_attributes=True)
    # 发货记录在数据库中的主键。
    id: int
    # 展示给用户或管理员的发货单号。
    shipment_number: str
    # 这张发货单所属的订单 ID。
    order_id: int
    # 承运商代码，例如 SF、YTO。
    carrier_code: str
    # 承运商名称，例如“顺丰速运”。
    carrier_name: str
    # 快递公司提供的物流单号。
    tracking_number: str
    # 当前发货状态；只允许使用 ShipmentStatus 枚举中定义的值。
    status: ShipmentStatus
    # 商家发货时间。
    shipped_at: datetime
    # “datetime | None”表示该字段可以是时间，也可以是空值。
    # 包裹尚未签收时没有送达时间，所以这里允许为 None。
    delivered_at: datetime|None
    # 嵌套结构：一张发货单可以包含多条物流轨迹。
    events: list[ShipmentEventRead]


# 【进阶】管理员创建发货单时，客户端需要提交的数据。
class ShipmentCreate(BaseModel):
    # Field 用来增加校验规则。
    # pattern 中的正则表示：只能使用英文字母、数字、下划线和短横线。
    carrier_code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    # 承运商名称长度必须在 2～80 个字符之间。
    carrier_name: str = Field(min_length=2, max_length=80)
    # 物流单号长度必须在 6～80 个字符之间，并限制可使用的字符。
    tracking_number: str = Field(min_length=6, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")



# 【入门】管理员订单列表中的“一行”数据。
class AdminOrderListItem(BaseModel):
    # 订单数据库主键。
    id: int
    # 展示给用户的订单编号。
    order_number: str
    # 下单用户的数据库主键。
    user_id: int
    # 下单用户的邮箱。
    user_email: str
    # 发货记录 ID；未发货的订单还没有该 ID，因此允许为 None。
    shipment_id: int|None
    # 订单当前状态，取值由 OrderStatus 枚举统一约束。
    status: OrderStatus
    # Decimal 适合保存金额，可避免浮点数计算产生的精度误差。
    total_amount: Decimal
    # 订单内商品的总件数。
    item_count: int
    # 订单创建时间。
    created_at: datetime


# 【进阶】管理员订单列表的分页返回结构。
class AdminOrderPage(BaseModel):
    # 当前页的订单数据。
    items: list[AdminOrderListItem]
    # 满足查询条件的订单总数，不只是当前页的数量。
    total: int
    # 当前是第几页，通常从 1 开始。
    page: int
    # 每页最多返回多少条数据。
    page_size: int
    # 总页数，通常根据 total 和 page_size 向上取整得到。
    pages: int


# 【进阶 → 实战】管理员新增一条物流轨迹时提交的数据。
class ShipmentEventCreate(BaseModel):
    # 事件编号只能包含英文字母、数字和短横线，长度为 6～80 个字符。
    event_code: str = Field(min_length=6, max_length=80, pattern=r"^[A-Za-z0-9-]+$")
    # Literal 把可选值限定为以下三种；提交其他字符串时会校验失败。
    status: Literal['in_transit','out_for_delivery','delivered']
    # 物流进度描述，长度为 2～255 个字符。
    destination: str = Field(min_length=2, max_length=255)
    # location 没有传值时默认使用空字符串，但最长不能超过 255 个字符。
    location: str = Field(default="", max_length=255)
    # default_factory 会在每次创建对象时执行函数，生成当时的 UTC 时间。
    # 这里不能直接写 datetime.now(UTC)，否则默认时间可能在模块加载时就固定下来。
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))



class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    refund_number: str
    order_id: int
    payment_id: int
    user_id: int
    amount: Decimal
    reason: str
    status: RefusedStatus
    admin_note: str | None
    requested_at: datetime
    reviewed_at: datetime | None
    completed_at: datetime | None

class AdminRefundPage(BaseModel):
    items: list[RefundRead]
    total: int
    page: int
    page_size: int
    pages: int



class RefundReview(BaseModel):
    note: str = Field(default="", max_length=255)


class RefundCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=255)