"""购物车 Service：连接 HTTP 接口、MySQL 商品数据和 Redis 购物车数据。

``add_item`` 路由在这里经历两个阶段：

1. ``add_to_cart`` 校验 SKU 并调用 Repository 写 Redis；
2. ``build_cart`` 重新读取 Redis，与数据库信息合并后生成完整响应。

【重点】Service 负责“业务规则”，但不应该关心 HTTP 状态码或 Redis 命令细节。
"""

from __future__ import annotations

from decimal import Decimal

from redis import Redis
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.expression import select


from repository import cart as cart_repository
from models import ProductSku, Product, ProductStatus
from schemas.car import CartRead, StoredCartItem, CartItemRead


from core.config import get_settings

# 配置包含单 SKU 数量上限和购物车有效期。
settings = get_settings()


class CartStockError(Exception):
    """请求数量超过当前允许上限。"""

    def __init__(self, stock: int) -> None:
        # 路由会读取此属性，生成 "available stock is ..." 错误信息。
        self.stock = stock


class CartSkuUnavailableError(Exception):
    """SKU 不存在、被禁用或所属商品未上架。"""

    pass


class CartItemNotFoundError(Exception):
    """要操作的购物车项不存在（当前 add_item 暂未使用）。"""

    pass


def user_cart_key(user_id: int) -> str:
    """生成登录用户的 Redis key，例如 ``mall:cart:user:1001``。"""
    return f"mall:cart:user:{user_id}"


def guest_cart_key(token: int) -> str:
    """生成游客的 Redis key，使其与用户购物车处于不同命名空间。

    【注意】调用方实际传入 HTTP Header 字符串，而这里标注为 int；运行时仍可
    格式化，但类型提示并不一致。
    """
    return f"mall:cart:guest:{token}"




def build_cart(db: Session, redis: Redis, key: str) -> CartRead:
    """把 Redis 中的精简购物车组装成可返回给客户端的完整购物车。

    【重点】Redis 保存易变的用户行为（数量、选中状态），MySQL 保存商品事实
    （名称、价格、库存、上下架状态）。这里以 SKU ID 为桥梁合并两类数据。
    """
    # 第一步：从 Redis 得到 {sku_id: StoredCartItem}。
    stored = cart_repository.read_cart(redis, key)
    # 字典的 key 就是稍后要去 MySQL 批量查询的 SKU ID。
    sku_ids = list(stored)
    if not sku_ids:
        # 购物车不存在或为空时，不需要访问数据库。
        return CartRead(items=[], item_count=0, selected_count=0, selected_amount=Decimal("0.00"))

    # 第二步：用一条 SQL 查询全部 SKU，避免在循环里逐条查询（N+1 问题）。
    statement = (
        select(ProductSku)
        # 【进阶】joinedload 同时加载 sku.product，之后检查商品状态时无需再发 SQL。
        .options(joinedload(ProductSku.product))
        .where(ProductSku.id.in_(sku_ids))
    )
    # 转成 {sku_id: ProductSku}，让后续按 ID 查找接近 O(1)。
    sku_map = {sku.id: sku for sku in db.scalars(statement).unique()}

    # 第三步：逐项合并 Redis 数据与数据库数据。
    items = [_to_item(sku_id, stored_item, sku_map.get(sku_id)) for sku_id, stored_item in stored.items()]
    # 按首次加入时间排序；重复增加同一 SKU 不会改变它原来的位置。
    items.sort(key=lambda item: stored[item.sku_id].added_at)

    # 只有“已勾选 + 当前可买 + 能计算小计”的项才参与结算汇总。
    selected_items = [item for item in items if item.selected and item.available and item.subtotal is not None]
    return CartRead(
        # 完整购物车明细。
        items=items,
        # 购物车总件数：所有行的 quantity 相加，不是 SKU 行数。
        item_count=sum(item.quantity for item in items),
        # 已勾选且可购买商品的总件数。
        selected_count=sum(item.quantity for item in selected_items),
        # Decimal("0.00") 作为初始值，保证空列表也得到 Decimal，而不是 int 0。
        selected_amount=sum((item.subtotal for item in selected_items if item.subtotal), Decimal("0.00")),
    )



def _to_item(sku_id: int, stored: StoredCartItem, sku: ProductSku | None) -> CartItemRead:
    """将一条 Redis 记录和一条 SKU 数据合并为响应明细。"""
    # Redis 中可能残留已经从 MySQL 删除的 SKU；仍返回该项并标记不可购买，
    # 这样用户能看到异常，而不是购物车商品无声消失。
    if sku is None:
        return CartItemRead(
            sku_id=sku_id, quantity=stored.quantity, selected=stored.selected,
            available=False, issue="sku_not_found",
        )

    # ProductSku.product 已由 joinedload 提前加载。
    product: Product = sku.product
    issue = None

    # 按优先级确定不可购买原因；只保留第一个最主要的问题。
    if product.status != ProductStatus.ON_SALE:
        issue = "product_off_sale"
    elif not sku.is_active:
        issue = "sku_inactive"
    elif sku.stock < stored.quantity:
        issue = "insufficient_stock"

    # 即使暂时不可购买，也计算并展示当前价格小计。
    subtotal = sku.price * stored.quantity
    return CartItemRead(
        sku_id=sku.id,
        product_id=product.id,
        product_slug=product.slug,
        product_name=product.name,
        cover_image_url=product.cover_image_url,
        sku_name=sku.name,
        attributes=sku.attributes,
        quantity=stored.quantity,
        selected=stored.selected,
        price=sku.price,
        subtotal=subtotal,
        stock=sku.stock,
        available=issue is None,
        issue=issue,
    )


def _get_sellable_sku(db: Session, sku_id: int) -> ProductSku | None:
    """查询 SKU 及所属商品，并确认它当前允许销售。

    预期规则：SKU 必须存在、SKU 自身已启用、所属 Product 状态为 ON_SALE。
    """
    statement = (
        select(ProductSku)
        # 一并加载 Product，因为可售判断需要 product.status。
        .options(joinedload(ProductSku.product))
        .where(ProductSku.id == sku_id)
    )
    # scalar 返回第一行的 ProductSku；查不到时返回 None。
    sku = db.scalar(statement)
    if sku is None or not sku.is_active or sku.product.status != ProductStatus.ON_SALE:
        # 【重点：疑似问题】这里返回的是“异常类本身”，并没有 raise 异常，且与
        # 返回类型 ProductSku | None 不一致。结果是不可售 SKU 可能继续进入后续
        # 写入流程。按函数意图，这里通常应是 ``raise CartSkuUnavailableError``。
        raise CartSkuUnavailableError
    return sku


def add_to_cart(db: Session, redis: Redis, key: str, sku_id: int, quantity: int) -> None:
    """执行加入购物车的业务校验，再委托 Repository 原子更新 Redis。

    Args:
        db: 查询 SKU 和商品状态所用的数据库 Session。
        redis: 保存购物车所用的 Redis 客户端。
        key: 当前用户或游客的购物车 Redis key。
        sku_id: 要加入的 ProductSku.id。
        quantity: 本次希望增加的数量，不是最终总数量。

    Raises:
        CartSkuUnavailableError: SKU 不可销售（这是设计意图，见下方疑似问题）。
        CartStockError: 最终数量超过允许上限。
        CartConcurrentUpdateError: Redis 并发更新连续重试仍失败。
    """
    # 第一步：查询 SKU，并检查存在性、启用状态、商品上架状态。
    sku = _get_sellable_sku(db, sku_id)

    # 第二步：计算单个 SKU 允许出现在购物车中的最大总数量。
    # 【重点：疑似问题】当前使用 quantity（本次新增量）参与 min，完全没有使用
    # sku.stock。比如购物车已有 1 件、本次再加 1 件，则 limit=1，Repository
    # 计算新总数 2 后会误判超限；同时库存不足也不能在写入前被正确拦截。
    limit = min(settings.cart_max_quantity, sku.stock)

    # 【重点：疑似问题】CartItemAdd 已限制 quantity >= 1，且配置上限默认 99，
    # 所以正常接口调用下 limit < 1 基本不可达；这里也无法真正判断库存为 0。
    if limit < 1:
        raise CartStockError(sku.stock)

    try:
        # 第三步：Repository 会读取已有数量、相加、校验总上限并原子写回。
        cart_repository.add_item(
            redis,
            key,
            sku_id,
            quantity,
            max_quantity=limit,
            ttl=settings.cart_ttl_seconds,
        )
    except cart_repository.CartQuantityLimitError as exc:
        # 将数据访问层异常转换为业务层异常，避免 Router 理解 Repository 细节。
        raise CartStockError(exc.limit) from exc

#
# def update_cart_item(
#     db: Session,
#     redis: Redis,
#     key: str,
#     sku_id: uuid.UUID,
#     quantity: int | None,
#     selected: bool | None,
# ) -> None:
#     if quantity is not None:
#         sku = _get_sellable_sku(db, sku_id)
#         if quantity > min(sku.stock, settings.cart_max_quantity):
#             raise CartStockError(sku.stock)
#     item = repository.update_item(
#         redis, key, sku_id, quantity=quantity, selected=selected, ttl=settings.cart_ttl_seconds
#     )
#     if item is None:
#         raise CartItemNotFoundError

def update_cart_item(
        db: Session,
        redis: Redis,
        key: str,
        sku_id: int,
        quantity: int|None,
        selected:bool|None,
) -> None:
    if quantity is not None:
        sku = _get_sellable_sku(db, sku_id)
        if quantity > min(sku.stock,settings.cart_max_quantity):
            raise CartStockError(sku.stock)
    item = cart_repository.update_item(
        redis,
        key,
        sku_id,
        quantity=quantity,
        selected=selected,
        ttl=settings.cart_ttl_seconds,
    )
    if item is None:
        raise CartItemNotFoundError
