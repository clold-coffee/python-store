from sqlalchemy import select, func, null
from sqlalchemy.orm import Session, selectinload

from models import User
from models.fulfillment import Shipment, ShipmentStatus, Refund, RefusedStatus
from models.order import OrderStatus, Order


# 本文件属于 Repository（数据访问）层。
# Repository 的职责是集中编写数据库查询，让路由层和业务层不必关心 SQL 细节。


# 【入门】根据订单 ID 查询对应的发货记录。
def get_shipment_by_order(db: Session, order_id: int) -> Shipment | None:
    # db.scalar(...) 取查询结果的第一列、第一条数据。
    # 如果没有找到记录，返回 None，因此返回类型写成 Shipment | None。
    return db.scalar(
        # select(Shipment) 相当于 SQL 中的 SELECT ... FROM shipments。
        select(Shipment)
        # 提前加载该发货单的全部物流事件。
        # 后续访问 shipment.events 时，不需要再逐条发送额外的数据库查询。
        .options(selectinload(Shipment.events))
        # 只保留 order_id 与传入参数相等的发货记录。
        .where(Shipment.order_id == order_id)
    )


# 【入门】根据发货记录本身的主键 ID 查询发货单。
# 注意：shipment_id 是发货记录 ID，与上一个函数的 order_id 含义不同。
def get_shipment_by_id(db: Session, shipment_id: int) -> Shipment | None:
    return db.scalar(
        select(Shipment)
        # 同样预先加载物流事件，得到完整的发货单数据。
        .options(selectinload(Shipment.events))
        .where(Shipment.id == shipment_id)
    )

def get_shipment_by_order(db: Session, order_id: int) -> Shipment | None:
    return db.scalar(
        select(Shipment).options(selectinload(Shipment.events)).where(Shipment.order_id == order_id)
    )


def get_refund_by_order(db: Session, order_id: int) -> Refund | None:
    return db.scalar(
        select(Refund)
        .where(Refund.order_id == order_id)
    )


# 【入门 → 进阶】分页查询管理员订单列表，并同时返回订单总数。
def list_orders(db: Session, status: OrderStatus | None, page: int, page_size: int) -> tuple[
    list[tuple[Order, str]], int]:
    # 如果传入 status，就生成一个状态筛选条件；否则使用空列表，表示不筛选状态。
    # 把条件统一放进列表后，下面的“总数查询”和“列表查询”可以复用它。
    condiction = [Order.status == status] if status else []

    # 先统计满足条件的全部订单数量。
    # 这里没有添加 offset 和 limit，所以 total 是所有页面的总数。
    # 当 scalar() 返回 None 时，“or 0”保证最终得到整数 0。
    total = db.scalar(select(func.count(Order.id)).where(*condiction)) or 0

    # statement 只是构建查询语句；直到下面执行 db.execute() 时才真正访问数据库。
    statement = (
        # 每行查询三个值：订单对象、用户邮箱、发货记录 ID。
        select(Order, User.email, Shipment.id)
        # 普通 join（内连接）：订单必须存在对应用户，才会出现在结果中。
        .join(User, User.id == Order.user_id)
        # outerjoin（左连接）：即使订单尚未发货，也保留该订单。
        # 未发货订单没有 Shipment.id，此时查询结果中的发货记录 ID 为 None。
        .outerjoin(Shipment, Shipment.order_id == Order.id)
        # 批量提前加载每张订单的商品明细，避免访问 Order.items 时产生 N+1 查询。
        .options(selectinload(Order.items))
        # 星号把条件列表展开：有条件时进行筛选，空列表时不添加筛选条件。
        .where(*condiction)
        # 先按创建时间倒序；时间相同时再按 ID 倒序，保证分页顺序稳定。
        .order_by(Order.created_at.desc(), Order.id.desc())
        # page 从 1 开始：第 1 页跳过 0 条，第 2 页跳过 page_size 条。
        .offset((page - 1) * page_size)
        # 限制当前页面最多返回 page_size 条记录。
        .limit(page_size)
    )

    # execute() 执行查询；unique() 去除 ORM 实体重复；tuples() 按元组形式返回每行。
    # 最终结果为：(当前页订单列表, 满足条件的订单总数)。
    return list(db.execute(statement).unique().tuples()), total


# 【进阶】分页查询退款申请，也可以按照退款状态筛选。
def list_refused(
        db: Session,
        page: int,
        page_size: int,
        status: RefusedStatus | None
) -> tuple[list[Refund], int]:
    # status 为 None 时查询全部退款；否则只查询指定状态。
    conditions = [Refund.status == status] if status else []

    # 分页接口通常需要两次查询：一次统计总数，一次获取当前页数据。
    total = db.scalar(select(func.count(Refund.id)).where(*conditions)) or 0
    statement = (
        select(Refund)
        .where(*conditions)
        # 最近审核的退款排在前面；审核时间相同时，用 ID 保持稳定排序。
        .order_by(Refund.reviewed_at.desc(), Refund.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    # scalars() 只提取每行中的 Refund 对象，而不是返回 Row 或元组。
    return list(db.scalars(statement)), total

def get_refund_by_order(db: Session, order_id: int) -> Refund | None:
    return db.scalar(
        select(Refund)
        .where(Refund.order_id == order_id)
    )