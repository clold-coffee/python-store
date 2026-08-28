from datetime import datetime
from decimal import Decimal

from typing import Optional, List
from venv import logger
import secrets

import math
from redis import Redis, RedisError
from sqlalchemy import update, select, desc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from models import ProductSku, ProductStatus
from models.order import Address, Order, OrderStatus, OrderItem
from schemas.order import AddressCreate, AddressUpdate, OrderPage, OrderListItem
from repository import order as order_repository
from service.cart import user_cart_key
from repository import cart as cart_repository

MAX_ADDRESS_COUNT = 20


class AddressNotFountError(Exception):
    pass


class AddressNotFoundError(Exception):
    pass


class AddressLimitError(Exception):
    pass


class AddressNotFount(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


class EmptyCheckoutError(Exception):
    pass

class OrderNotFoundError(Exception):
    pass

class OrderStateError(Exception):
    pass

class OrderStockError(Exception):
    """某个 SKU 的实时库存不足。"""

    def __init__(self, sku_name: str, stock: int) -> None:
        self.sku_name = sku_name
        # stock 是数据库锁定后读到的实时库存，而不是购物车加入时的旧库存。
        self.stock = stock


class OrderItemUnavailableError(Exception):
    """下单时，某个 SKU 已失效、下架或不存在。"""

    def __init__(self, sku_name: str) -> None:
        # 保存具体 SKU，方便 API 层生成对用户有意义的错误信息。
        self.sku_name = sku_name


def _clear_other_defaults(db: Session, user_id: int, except_id: Optional[int]) -> None:
    statement = update(Address).where(Address.user_id == user_id, Address.is_deleted.is_(False))
    if except_id is not None:
        statement = statement.where(Address.id != except_id)
    db.execute(statement.values(is_default=False))


def address_create(db: Session, paylod: AddressCreate, user_id: int) -> Address:
    existing = order_repository.list_addresses(db, user_id)

    if len(existing) >= MAX_ADDRESS_COUNT:
        raise AddressLimitError
    make_default = paylod.is_default or not existing
    if make_default:
        _clear_other_defaults(db, user_id, except_id=None)

    address = Address(
        user_id=user_id,
        **paylod.model_dump(exclude={"is_default"}),
        is_default=make_default
    )

    db.add(address)
    db.commit()
    db.refresh(address)
    return address


def address_update(db: Session, paylod: AddressUpdate, user_id: int, address_id: int) -> Address:
    address = order_repository.get_addresses(db, address_id, user_id)
    if address is None:
        raise AddressNotFount("地址已经被删除")
    # exclude_unset=True 只提取客户端本次明确传入的字段，避免把未传字段也更新掉。
    update_address = paylod.model_dump(exclude_unset=True)
    if update_address.get("is_default"):
        _clear_other_defaults(db, user_id, except_id=address.id)

    for key, value in update_address.items():
        setattr(address, key, value)
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


def delete_address(db: Session, address_id: int, user_id: int) -> None:
    address = order_repository.get_addresses(db, address_id, user_id)
    if address is None:
        raise AddressNotFount
    was_deleted = address.is_default
    address.is_default = False
    address.is_deleted = True

    db.flush()
    if was_deleted:
        # more地址被删除，地址列表的第一个为默认地址
        first_address = db.scalar(
            select(Address).where(
                Address.user_id == user_id,
                Address.id != address.id,
                Address.is_deleted.is_(False),
            ).order_by(desc(Address.updated_at)).limit(1)
        )
        if first_address:
            first_address.is_default = True
    db.commit()


def _order_number() -> str:
    """生成便于展示的订单号：UTC 时间 + 8 位随机十六进制字符。"""

    # UUID 仍然是数据库主键；订单号主要面向用户和客服场景。
    # 随机尾缀可降低同一秒内多个订单发生编号碰撞的概率。
    return f"M{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}"


def create_order(
        db: Session,
        redis: Redis,
        user_id: int,
        address_id: int,
        idempotency_key: str,
) -> Order | None:
    existing = order_repository.get_order_by_idempotence(db, user_id, idempotency_key)
    if existing is not None:
        return existing

    address = order_repository.get_addresses(db, address_id, user_id)
    if address is None:
        raise AddressNotFoundError

    cart_key = user_cart_key(user_id)
    sorted_cart = cart_repository.read_cart(redis, cart_key)
    selected = {
        sku_id: item for sku_id, item in sorted_cart.items() if item.selected
    }

    if not selected:
        raise EmptyCheckoutError
    sku_ids = sorted(selected, key=str)

    try:
        statement = (
            select(ProductSku)
            .options(joinedload(ProductSku.product))
            .where(ProductSku.id.in_(sku_ids))
            .order_by(ProductSku.id)
            .with_for_update()
        )
        sku_map = {
            sku.id: sku for sku in db.scalars(statement).unique()
        }
        order_items: List[OrderItem] = []
        total = Decimal("0.00")

        for sku_id in sku_ids:
            sku = sku_map.get(sku_id)
            quantity = selected[sku_id].quantity
            if sku is None or not sku.is_active or sku.product.status != ProductStatus.ON_SALE:
                raise OrderItemUnavailableError(sku.name if sku else str(sku_id))
            if sku.stock < quantity:
                raise OrderStockError(sku.name, sku.stock)

            subtotal = sku.price * quantity
            total += subtotal
            sku.stock -= quantity
            order_items.append(OrderItem(
                sku_id=sku_id,
                sku_code=sku.sku_code,
                product_name=sku.product.name,
                product_slug=sku.product.slug,
                sku_name=sku.name,
                attributes=dict(sku.attributes),
                cover_image_url=sku.product.cover_image_url,
                unit_price=sku.price,
                quantity=quantity,
                subtotal=subtotal,
            ))

            order = Order(
                order_number=_order_number(),
                user_id=user_id,
                status=OrderStatus.PENDING_PAYMENT,
                total=total,
                idempotency_key=idempotency_key,
                recipient_name=address.recipient_name,
                phone=address.phone,
                province=address.province,
                city=address.city,
                district=address.district,
                address_details=address.details,
                postal_code=address.postal_code,
                items=order_items
            )
        db.add(order)
        db.commit()
    except (OrderItemUnavailableError, OrderStockError):
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        duplicate = order_repository.get_order_by_idempotency(db, user_id, idempotency_key)
        if duplicate is not None:
            return duplicate
        raise

    try:
        cart_repository.remove_items(redis, cart_key, sku_id)
    except RedisError:
        logger.exception("Order created but selected cart items could not be removed")

    return order_repository.get_order(db, user_id, order.id)


def get_orders_pages(
        db: Session,
        user_id: int,
        page: int,
        page_size: int
) -> list[OrderListItem] | None:
    orders, total = order_repository.list_orders(db, user_id, page, page_size)

    items = []
    for order in orders:
        first = order.items[0]
        items.append(OrderListItem(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            total_amount=order.total,
            item_count=sum(item.quantity for item in order.items),
            first_product_name=first.product_name,
            first_image_cover_slug=first.cover_image_url,
            created_at=order.created_at,
        ))
    return OrderPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1
    )





def cancel_order(db: Session, user_id: int,order_id: int, reason:str) -> Order:
    try:
        statement = (
            select(Order)
                 # 一个订单对应多条明细，selectinload 会用第二条 IN 查询批量加载它们。
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id, Order.id == order_id)
               # 锁定订单，防止“支付”和“取消”等并发操作同时改变订单状态。
            .with_for_update()
        )
        order = db.scalar(statement)
        if order is None:
            raise OrderNotFoundError

        # 重复取消属于幂等操作：不重复加库存，直接返回已经取消的订单。
        if order.status == OrderStatus.CANCELED:
            # 结束当前持锁事务，再用仓储层加载完整订单。
            db.rollback()
            return order_repository.get_order(db, user_id, order.id)

        if order.status != OrderStatus.PENDING_PAYMENT:
            raise OrderStockError

        # 只处理仍有关联 SKU 的明细；按固定顺序锁 SKU，理由与下单时相同。
        sku_ids = sorted([item.sku_id for item in order.items], key=str)
        if sku_ids:
            sku_statement = ((select(ProductSku)
                             .where(ProductSku.id.in_(sku_ids)))
                             .order_by(ProductSku.id)
                             .with_for_update())

            sku_map = {sku.id: sku for sku in db.scalars(sku_statement)}
            for item in order.items:
                if item.sku_id  in sku_map:
                    sku_map[item.sku_id].stock += item.quantity

        # 状态变更和库存回补一起提交，避免只完成其中一部分。
        order.status = OrderStatus.CANCELED
        order.cancel_reason = reason
        order.cancelled_at = datetime.now()
        db.commit()

    except (OrderNotFoundError, OrderStateError):
        db.rollback()
        raise

        # 提交后重新读取，确保 items 已加载且返回数据完整。
    return order_repository.get_order(db, user_id, order_id)  # type: ignore[return-value]

