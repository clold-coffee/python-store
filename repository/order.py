from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from models.order import Address, Order


def list_addresses(db: Session, user_id: int) -> list[Address]:
    statement = select(Address).where(
        Address.user_id == user_id,
        Address.is_deleted.is_(False),
    ).order_by(Address.is_default.desc(), Address.created_at.desc())
    return list(db.scalars(statement))


def get_addresses(db: Session, address_id: int, user_id: int) -> Address | None:
    #  Address.is_deleted.is_(False) ------- 只查询 is_deleted 字段为 False 的地址，也就是没有被删除的地址。
    statement = select(Address).where(
        address_id == Address.id,
        Address.user_id == user_id,
        Address.is_deleted.is_(False)
    )
    return db.scalar(statement)


def get_order_by_idempotency(db: Session, user_id: int, key: str) -> Order | None:
    statement = select(Order).options(selectinload(Order.items)).where(
        Order.user_id == user_id,
        Order.idempotency_key == key,
    )
    return db.scalar(statement)


def get_order_by_idempotence(db: Session, user_id: int, key: str) -> Order | None:
    statement = (select(Order)
                 .options(selectinload(Order.items))
                 .where(Order.user_id == user_id,
                        Order.idempotency_key == key)
                 )
    return db.scalar(statement)


def get_order(db: Session, user_id: int, order_id: int) -> Order | None:
    statement = select(Order).options(selectinload(Order.items)).where(
        Order.id == order_id,
        Order.user_id == user_id,
    )
    return db.scalar(statement)


def list_orders(db: Session, user_id: int,page:int,page_size: int) -> tuple[list[Order], int]:
    """分页查询指定用户的订单，并返回订单列表和订单总数。"""
    # 统一保存查询条件，确保总数统计与分页列表使用相同的过滤范围。
    conditions = [Order.user_id == user_id]
    # 总数不受分页参数影响，供调用方计算总页数；没有记录时返回 0。
    total = db.scalar(select(func.count(Order.id)).where(*conditions)) or 0

    statement = (
        (select(Order)
         # 添加加载规则，批量预加载订单明细，避免遍历订单时逐条查询 items（N+1 查询）。
         .options(selectinload(Order.items))
         .where(Order.user_id == user_id)
        # 按创建时间倒序展示；id 作为第二排序条件，保证同一时间的结果顺序稳定。
        .order_by(Order.created_at.desc(), Order.id.desc()))
        # page 从 1 开始：先跳过前面页的数据，再限制本页返回数量。
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(statement).unique()),total
