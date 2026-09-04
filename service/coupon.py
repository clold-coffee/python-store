"""优惠券业务服务。

建议按照下面的顺序阅读本文件，由简单查询逐步学到并发与事务：

1. ``list_available``：查看现在可以领取的优惠券。
2. ``list_mine``：查看用户自己的优惠券，并标记已经过期的记录。
3. ``claim``：领取优惠券，包含有效期、库存、重复领取和并发控制。
4. ``create_coupon``：创建优惠券，并处理优惠券编码冲突。

几个贯穿本文件的基础概念：

* ``db`` 是 SQLAlchemy 的数据库会话（Session），可以理解为一次数据库操作的
  “工作台”。``commit`` 会正式保存修改，``rollback`` 会撤销本次未完成的修改。
* ``Coupon`` 是优惠券模板，例如“满 100 减 20”；``UserCoupon`` 表示某个用户
  已经领取的优惠券。
* 函数返回值后的 ``-> UserCoupon``、``-> list[Coupon]`` 都是类型提示，帮助
  阅读者和编辑器了解函数会返回什么，不会改变程序运行方式。
"""

from datetime import datetime, UTC
from decimal import Decimal, ROUND_HALF_UP

from pymysql import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models.payment import UserCoupon, Coupon, UserCouponStatus, DiscountType
from repository import payment as repository
from schemas.payment import CouponCreate

CENT = Decimal("0.01")


class CouponNotFoundError(Exception):
    """根据 coupon_id 没有找到优惠券。"""

    pass


class CouponUnavailableError(Exception):
    """优惠券当前不可领取，例如未开始、已过期或已经领完。"""

    pass


class CouponConflictError(Exception):
    """创建优惠券时发生数据冲突，例如优惠券编码已经存在。"""

    pass


class CouponNotUsableError(Exception):
    pass


def _aware(value: datetime) -> datetime:
    """统一返回带 UTC 时区的时间，确保两个 ``datetime`` 可以安全比较。

    数据库可能返回“不带时区”的时间，而 ``datetime.now(UTC)`` 会得到“带时区”
    的时间，二者直接比较会触发 ``TypeError``：

    * 没有时区：用 ``replace(tzinfo=UTC)`` 把它解释为 UTC 时间；
    * 已有时区：用 ``astimezone(UTC)`` 把它换算成 UTC 时间。

    函数名前的下划线表示它是本文件内部使用的辅助函数。
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def claim(db: Session, user_id: int, coupon_id: int) -> UserCoupon:
    """让指定用户领取一张优惠券。

    领取流程：检查是否领过 → 锁定优惠券 → 校验状态、时间和库存 → 扣减库存
    → 创建用户优惠券 → 提交事务。

    同一用户重复发送相同请求时会返回之前领取的记录，而不会再扣一次库存。
    这种“同一请求执行多次，结果仍保持一致”的能力叫做幂等性。
    """
    # 第一层重复检查：查询“这个用户是否已经领过这张优惠券”。
    existing = db.scalar(
        select(UserCoupon)
        # joinedload 会在同一次查询中加载关联的 Coupon，后面读取时不用再次查库。
        .options(joinedload(UserCoupon.coupon))
        .where(
            UserCoupon.user_id == user_id,
            UserCoupon.coupon_id == coupon_id
        )
    )

    if existing is not None:
        # 已经领取过就直接返回旧记录，避免重复扣减优惠券库存。
        return existing

    # 统一使用带 UTC 时区的当前时间，避免比较有效期时出现时区类型错误。
    now = datetime.now(UTC)
    try:

        # 根据 coupon_id 查询优惠券模板。
        coupon = db.scalar(
            select(Coupon)
            .where(Coupon.id == coupon_id)
            # FOR UPDATE 会锁住这条数据，防止多个用户同时读取并扣减相同库存。
            .with_for_update()
        )
        if coupon is None:
            raise CouponNotFoundError
        # 下面任意一个条件成立，都表示优惠券当前不可领取。
        if (
                # 管理员已经关闭了这张优惠券。
                not coupon.is_active
                # 开始时间还在未来，即活动尚未开始。
                or _aware(coupon.valid_from) > now
                # 结束时间已到；等于结束时间时也视为过期。
                or _aware(coupon.valid_until) <= now
                # 已领取数量达到发行总量，说明库存已经用完。
                or coupon.claimed_quantity >= coupon.total_quantity
        ):
            raise CouponUnavailableError
        # 校验全部通过后，先把已领取数量加一。
        coupon.claimed_quantity += 1
        # 创建“用户—优惠券”的关联记录，表示该用户拥有了这张券。
        user_coupon = UserCoupon(
            user_id=user_id,
            coupon_id=coupon_id,
            coupon=coupon,
        )
        # add 先把新对象放入待保存区；commit 才会真正写入数据库。
        db.add(user_coupon)
        db.commit()
        # refresh 重新读取数据库生成的 id、领取时间等字段。
        db.refresh(user_coupon)
        return user_coupon
    except (
            CouponNotFoundError,
            CouponUnavailableError,
    ):
        # 业务校验失败时撤销当前事务，再把原异常继续交给接口层处理。
        db.rollback()
        raise

    except IntegrityError:
        # 并发请求可能同时通过最前面的重复检查，最终由数据库唯一约束拦截。
        db.rollback()
        # 回滚后重新查询，判断冲突是否由“同一用户重复领取同一张券”造成。
        duplicate = db.scalar(
            select(UserCoupon)
            .options(joinedload(UserCoupon.coupon))
            .where(
                UserCoupon.user_id == user_id,
                UserCoupon.coupon_id == coupon_id,
            )
        )
        if duplicate is not None:
            # 注意：duplicate 是数据对象，不是 Exception；直接 raise 它会产生
            # TypeError。这里保留原有代码，仅说明它当前的实际行为。
            raise duplicate
        # 查不到重复记录，说明是其他数据库完整性问题，继续抛出原异常。
        raise


def list_available(db: Session) -> list[Coupon]:
    """查询当前仍可领取的优惠券列表。

    具体筛选条件放在 repository 层，包括：已启用、活动已开始、尚未过期，
    并且剩余库存大于零。
    """
    # 把当前 UTC 时间传给仓储层，让数据库直接完成有效期筛选。
    return repository.list_available_coupons(db, datetime.now(UTC))


def list_mine(db: Session, user_id: int) -> list[UserCoupon]:
    """查询用户领取过的优惠券，并同步其中的过期状态。

    数据库中的状态可能仍是 ``AVAILABLE``，但优惠券模板的截止时间已经到达。
    本函数在返回列表前把这种记录更新成 ``EXPIRED``。
    """
    now = datetime.now(UTC)
    coupons = repository.list_user_coupons(db, user_id)
    # changed 用来记录循环中是否真的修改过数据，避免无变化时也提交事务。
    changed = False
    for item in coupons:
        # 只处理“可使用但有效期已结束”的券；已使用/已过期的券不用重复修改。
        if item.status == UserCouponStatus.AVAILABLE and _aware(item.coupon.valid_until) <= now:
            item.status = UserCouponStatus.EXPIRED
            changed = True
    if changed:
        # SQLAlchemy 会跟踪对象属性变化，commit 时自动生成对应的 UPDATE。
        db.commit()
    return coupons


def create_coupon(db: Session, payload: CouponCreate) -> Coupon:
    """根据接口传入的数据创建优惠券模板。

    实际的对象构造和保存由 repository 层完成；服务层负责把数据库完整性错误
    转换成更容易被接口层识别的 ``CouponConflictError``。
    """
    try:
        return repository.create_coupon(db, payload)
    except IntegrityError:
        # 保存失败后必须回滚，否则这个 Session 不能继续执行后续数据库操作。
        db.rollback()
        raise CouponConflictError


def release(db: Session, user_coupon_id: int | None) -> None:
    if user_coupon_id is None:
        return
    item = db.get(UserCoupon, user_coupon_id)
    if item is not None and item.status == UserCouponStatus.USED:
        if _aware(item.coupon.valid_until) > datetime.now(UTC):
            item.status = UserCouponStatus.AVAILABLE
        else:
            item.status = UserCouponStatus.EXPIRED
        item.used_at = None


def reserve_for_order(
        db: Session,
        user_id: int,
        user_coupon_id: int,
        original_amount: Decimal,
) -> tuple[UserCoupon, Decimal]:
    statement = (
        select(UserCoupon)
        .options(joinedload(UserCoupon.coupon))
        .where(UserCoupon.id == user_coupon_id, UserCoupon.user_id == user_id)
        .with_for_update()
    )
    item = db.scalar(statement)
    now = datetime.now(UTC)
    if item is None:
        raise CouponNotFoundError
    coupon = item.coupon
    if (
            item.status != UserCouponStatus.AVAILABLE
            or not coupon.is_active
            or _aware(coupon.valid_from) > now
            or _aware(coupon.valid_until) <= now
            or original_amount < coupon.minimum_amount
    ):
        raise CouponNotUsableError

    if coupon.discount_type == DiscountType.FIXED:
        discount = coupon.discount_value
    else:
        discount = original_amount * coupon.discount_value / Decimal("100")
    discount = min(original_amount, discount).quantize(CENT, rounding=ROUND_HALF_UP)
    item.status = UserCouponStatus.USED
    item.used_at = now
    return item, discount
