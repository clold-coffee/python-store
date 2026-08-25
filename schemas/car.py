
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator


class CartItemAdd(BaseModel):
    """``POST /car/items`` 的 JSON 请求体。

    请求示例：``{"sku_id": 25, "quantity": 2}``。

    【重点】FastAPI 会在进入路由函数之前完成校验。类型不正确、quantity 小于
    1 或大于 99 时，框架会直接返回 422，``add_item`` 路由不会被执行。
    """

    # 要加入购物车的最小销售单元 ID，对应 ProductSku.id。
    sku_id: int
    # 未传数量时默认加入 1 件；ge/le 分别表示大于等于/小于等于。
    quantity: int = Field(default=1, ge=1, le=99)

class CartItemUpdate(BaseModel):
    quantity: Optional[int] = Field(default=1, ge=1, le=99)
    selected:Optional[bool] = True

    # 这段代码是什么意思？
    @model_validator(mode='after')
    def require_change(self) -> "CartItemUpdate":
        if self.quantity is None and self.selected is None:
            raise ValueError("CartItemUpdate.quantity is required.")
        return self

class StoredCartItem(BaseModel):
    """实际写入 Redis 的精简购物车项。

    Redis 不重复保存商品名称、价格和库存，因为这些信息可能变化；读取购物车
    时，Service 会根据 SKU ID 到数据库获取最新信息。
    """

    # 当前 SKU 在购物车中的总件数，不是本次请求新增的件数。
    quantity: int
    # 是否被勾选用于结算；首次加入时默认为 True。
    selected: bool = True
    # 首次加入购物车的时间，用于展示排序；后续增加数量时会保留原时间。
    added_at: datetime

class CartItemRead(BaseModel):
    """返回给客户端的一条完整购物车明细。

    它把 Redis 中的数量/选中状态与数据库中的商品、价格、库存信息合并起来。
    Optional 字段允许 SKU 被删除或商品异常时仍能返回这条购物车记录。
    """

    sku_id: int
    product_id: Optional[int] = None
    product_slug: Optional[str] = None
    # 【重点：疑似问题】Service 还会传入 ``product_name``，但本模型没有定义该
    # 字段，因此商品名称可能不会出现在最终响应中。
    cover_image_url: Optional[str] = None
    sku_name: Optional[str] = None
    # 【重点：疑似问题】Service 传入的名称是 ``attributes``（复数），这里却是
    # ``attribute``（单数）。Pydantic 默认可能忽略多余的 attributes，导致属性丢失。
    attribute: dict[str, object] = Field(default_factory=dict)
    quantity: int
    selected: bool
    price: Optional[Decimal] = None
    subtotal: Optional[Decimal] = None
    # 【重点：疑似问题】这里写成了 ``sock``，Service 传入的是 ``stock``。
    # 这会让响应中的库存字段使用默认值 0，而不是数据库中的真实库存。
    sock: int = 0
    available: bool = True
    issue:Optional[str] = None

class CartRead(BaseModel):
    """``add_item`` 成功后返回的完整购物车汇总。"""

    # 每个 SKU 的完整展示信息。
    items: List[CartItemRead]
    # 所有购物车项的 quantity 总和。
    item_count: int
    # 已勾选且当前可购买的商品总件数。
    selected_count: int
    # 已勾选且可购买商品的小计总和。
    selected_amount: Decimal



class CartSelectionUpdate(BaseModel):
    selected: bool
    sku_ids: Optional[list[int] ] = None