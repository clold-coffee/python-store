"""支付业务服务。

建议按下面的顺序阅读本文件，这样可以由浅入深地理解支付流程：

1. ``create_payment``：用户为订单创建一条支付记录。
2. ``mock_confirm``：本地开发时，模拟支付平台发来“支付成功”通知。
3. ``sign_callback``：为通知生成签名，防止内容被篡改。
4. ``process_callback``：校验通知，并同时更新支付单和订单状态。

这里的 ``db`` 是数据库会话（Session）。可以先把它理解成“本次数据库操作的
工作台”：通过它查询、添加和修改数据，最后用 ``commit`` 保存，失败时用
``rollback`` 撤销本次尚未保存的操作。
"""

import hashlib
import hmac
import secrets
import time
from datetime import UTC,datetime

from pymysql import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from models import ProductSku
from models.order import Order, OrderStatus
from models.payment import Payment, PaymentCallback, PaymentStatus, OrderStatusLog
from repository import payment as payment_repository
from schemas.payment import PaymentCallbackResult, MockPaymentCallback
from service import coupon as coupon_service


class StaleCallbackError(Exception):
    """回调时间戳过旧，可能是网络延迟或重放攻击。"""

    pass


class InvalidCallbackSignatureError(Exception):
    """回调签名不正确，说明来源不可信或内容被修改。"""

    pass


class PaymentAmountError(Exception):
    """回调中的付款金额与支付单金额不一致。"""

    pass


class PaymentNotFoundError(Exception):
    """没有找到指定的支付记录。"""

    pass


class PaymentOrderNotFoundError(Exception):
    """没有找到支付记录所对应的订单。"""

    pass


class PaymentStateError(Exception):
    """支付单或订单当前状态不允许继续执行支付操作。"""

    pass


class PaymentExpiredError(Exception):
    """订单已超过支付截止时间。"""

    pass


def _aware(value: datetime) -> datetime:
    """把时间转换成便于比较的形式。

    函数名前的下划线表示：它是本模块内部使用的辅助函数，不是对外接口。
    ``tzinfo`` 用来判断时间是否携带时区；携带时区时统一转换为 UTC。
    """
    print("_aware--", value.replace())
    return value.replace() if value.tzinfo is None else value.astimezone(UTC)


def _payment_number() -> str:
    """生成支付流水号，例如 ``P20260902153045A1B2C3D4E5``。

    前半部分是 UTC 时间，方便识别创建时间；后半部分是随机十六进制字符，
    用来降低同一秒内生成重复编号的概率。
    """
    return f"P{datetime.now(UTC):%Y%m%d%H%M%S}{secrets.token_hex(5).upper()}"


def _callback_message(payload: MockPaymentCallback) -> str:
    """按固定顺序拼接回调字段，得到等待签名的原始文本。

    签名方和验签方必须使用完全相同的字段顺序与格式；即使只多一个空格，
    最后计算出的签名也会不同。金额固定保留两位小数也是出于这个原因。
    """
    print("_callback_message--", payload)
    # ``join`` 会用英文句点连接元组中的每一段字符串。
    return ".".join((
        payload.event_id,
        payload.payment_number,
        f"{payload.amount:.2f}",
        payload.status,
        str(payload.timestamp),
        payload.provider_transaction_id,
    ))


def create_payment(
        db: Session,
        user_id: int,
        order_id: int,
        client_request_id: str,
) -> Payment:
    """为当前用户的订单创建支付记录。

    ``client_request_id`` 是客户端请求的唯一标识。相同请求即使因为网络问题
    被重复发送，也应该返回同一条支付记录，这种能力叫“幂等性”。

    返回：新建或之前已经创建好的 ``Payment`` 对象。
    可能抛出：订单不存在、订单状态不允许支付、订单已过期等业务异常。
    """
    # 第一层幂等检查：大多数重复请求可以在加锁前直接返回，速度更快。
    existing_request = payment_repository.get_payment_by_request(db, user_id, client_request_id)
    if existing_request is not None:
        return existing_request

    try:
        # 只查找“订单编号和用户编号都匹配”的订单，避免用户操作别人的订单。
        order = db.scalar(
            select(Order).where(
                Order.id == order_id,
                Order.user_id == user_id
            )
            # ``FOR UPDATE`` 给这一行加数据库锁，防止并发请求同时修改订单。
            .with_for_update()
        )

        if order is None:
            raise PaymentOrderNotFoundError
        # 等待数据库锁期间，另一个请求可能已创建支付单，所以加锁后再检查一次。
        exiting_order = payment_repository.get_payment_by_request(db, user_id, client_request_id)
        if exiting_order is not None:
            return exiting_order

        # 只有“待支付”的订单才允许创建支付单，已付款/已取消订单均不允许。
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise PaymentStateError


        # 截止时间早于或等于当前时间，说明该订单已经不能继续支付。
        if _aware(order.payment_expires_at) <= datetime.now():
            raise PaymentExpiredError

        # 用订单信息组装一条新的支付记录；金额以服务端订单总额为准。
        payment = Payment(
            payment_number=_payment_number(),
            order_id=order_id,
            user_id=user_id,
            amount=order.total,
            client_request_id=client_request_id,
        )
        # add 先把对象放进待保存区，commit 才真正提交数据库事务。
        db.add(payment)
        db.commit()
        # refresh 从数据库重新读取数据，以取得自动生成的 id 等字段。
        db.refresh(payment)
        return payment
    except (
            PaymentExpiredError,
            PaymentStateError,
            PaymentOrderNotFoundError,
    ):
        # 业务校验失败时撤销事务，再把原异常交给上层转换成接口响应。
        db.rollback()
        raise
    except IntegrityError:
        # 即使两个请求同时通过前面的检查，数据库唯一约束仍会挡住重复数据。
        db.rollback()
        # 发生唯一约束冲突后重新查询：若确实已有记录，就把它当作幂等结果返回。
        duplicate = payment_repository.get_payment_by_request(db, user_id, client_request_id)
        if duplicate is None:
            duplicate = payment_repository.get_payment_by_request(db, user_id, order_id)
        if duplicate is not None:
            return duplicate
        raise

def get_payment_details(db: Session, payment_id: int, user_id:int) -> Payment |None:
    """查询属于当前用户的支付详情。

    ``Payment | None`` 是类型提示，表示理论上可能返回支付对象或空值；本函数
    遇到空值会抛出 ``PaymentNotFoundError``，因此正常返回时一定是支付对象。
    """
    payment_item = payment_repository.get_payment_info(db,  payment_id,user_id)
    if payment_item is  None:
        raise PaymentNotFoundError

    return payment_item




def process_callback(
        db: Session,
        payload: MockPaymentCallback,
        signature:str
) -> PaymentCallbackResult:
    """处理支付平台回调，并把支付单和订单更新为成功状态。

    核心流程是：验签 → 防重复 → 检查时效 → 锁定数据 → 校验金额和状态
    → 更新状态 → 保存回调记录。支付单、订单、状态日志和回调记录在同一个
    事务中提交，避免只更新了一半而造成数据不一致。
    """
    # 先用同一份 payload 重新计算签名，再进行恒定时间比较。
    # compare_digest 比普通的 ``==`` 更适合比较安全签名，可降低时序攻击风险。
    if not hmac.compare_digest(sign_callback(payload), signature):
        raise InvalidCallbackSignatureError

    # event_id 是支付平台为每次通知生成的唯一编号，用它识别重复回调。
    existing_event = db.scalar(
        select(PaymentCallback)
        .where(PaymentCallback.event_id == payload.event_id)
    )

    if existing_event is not None:
        # 这次事件以前已处理过：不再更新数据，直接返回当时关联记录的状态。
        payment = db.get(Payment, existing_event.payment_id)
        order = db.get(Order, payment.order_id)
        return PaymentCallbackResult(
            duplicate=True,
            payment_status= payment.status,
            order_status= order.status.value
        )
    # 当前 Unix 时间与回调时间相差过大时拒绝处理，防止旧请求被反复利用。
    if abs(int(time.time()) - payload.timestamp) > get_settings().payment_callback_tolerance_seconds:
        raise StaleCallbackError

    try:
        # 根据支付流水号锁住支付记录，确保同一时刻只有一个回调能修改它。
        payment = db.scalar(
            select(Payment)
            .where(Payment.payment_number == payload.payment_number)
            .with_for_update()
        )

        if payment is None:
            raise PaymentNotFoundError
        # 支付成功时还要同步修改订单，因此订单记录也需要加锁。
        order = db.scalar(
            select(Order)
            .where(Order.id == payment.order_id )
            .with_for_update()
        )

        if order is None:
            raise PaymentOrderNotFoundError

        # 不能相信外部回调中的金额，必须和数据库保存的应付金额核对。
        if payment.amount != payload.amount:
            raise PaymentAmountError

        # 已成功的支付无需再改状态，但本次新的回调事件仍会记录下来。
        duplicate = payment.status == PaymentStatus.SUCCEEDED
        if not duplicate:
            # 两张表都必须处于正确的起始状态，才能完成“待支付 → 已支付”。
            if payment.status != PaymentStatus.PENDING or order.status != OrderStatus.PENDING_PAYMENT:
                raise PaymentStateError
            now = datetime.now()
            if _aware(order.payment_expires_at) <= now:
                raise PaymentExpiredError
            # 同步更新支付单与订单，记录第三方流水号和实际付款时间。
            payment.status = PaymentStatus.SUCCEEDED
            payment.provider_transaction_id = payload.provider_transaction_id
            payment.paid_at = now
            order.status = OrderStatus.PAID
            order.paid_at = now

            # 状态日志用于审计：以后可以追溯订单何时、为何变成已支付。
            db.add(OrderStatusLog(
                order_id=order.id,
                from_status= OrderStatus.PENDING_PAYMENT,
                to_status= OrderStatus.PAID,
                operator_type='payment_callback',
                reason=f'mockpay transaction {payload.provider_transaction_id}'
            ))

        # 保存原始回调，既用于防重复，也方便出现问题时排查。
        db.add(PaymentCallback(
            event_id=payload.event_id,
            payment_id= payment.id,
            signature=signature,
            payload = payload.model_dump(mode='json')
        ))

        # 上述修改一次性提交；任何一步失败，都会进入 except 并回滚。
        db.commit()
        return PaymentCallbackResult(
            duplicate=duplicate,
            payment_status= payment.status,
            order_status= order.status.value
        )
    except (
        PaymentNotFoundError,
        PaymentOrderNotFoundError,
        PaymentStateError,
        PaymentExpiredError,
        PaymentAmountError
    ):
        # 对可预期的业务错误统一回滚，同时保留原异常类型给接口层处理。
        db.rollback()
        raise
    except IntegrityError :
        # 并发回调可能同时通过“是否存在”检查，但数据库只能插入一个 event_id。
        db.rollback()
        # 冲突后能查到记录，说明另一个请求已经成功处理，按重复回调返回即可。
        callback  = db.scalar(
            select(PaymentCallback)
            .where(PaymentCallback.event_id == payload.event_id)
        )
        if callback is  None:
            raise
        payment = db.get(Payment, callback.payment_id)
        order = db.get(Order, payment.order_id)
        return PaymentCallbackResult(
            duplicate=True,
            payment_status= payment.status,
            order_status= order.status.value
        )


def sign_callback(payload: MockPaymentCallback) -> str:
    """使用共享密钥和 HMAC-SHA256 为回调内容生成十六进制签名。

    可以把 HMAC 理解成“只有知道密钥的人才能生成的内容指纹”：接收方用相同
    密钥重新计算，如果结果一致，就能确认内容没有被篡改。
    """
    # HMAC 接收字节数据，所以字符串形式的密钥和消息都要先 encode。
    secret = get_settings().mock_payment_secret.encode()
    return hmac.new(
        secret,
        _callback_message(payload).encode(),
        hashlib.sha256
    ).hexdigest()


def mock_confirm(db:Session, user_id:int, payment_id: int) -> PaymentCallbackResult:
    """在本地模拟支付平台发送一条“支付成功”回调。

    真实项目通常由第三方支付平台调用回调接口；这个函数只为开发或演示提供
    方便，最终仍复用 ``process_callback``，确保模拟流程和真实流程保持一致。
    """
    # 查询时同时传入 user_id，确保用户只能模拟确认自己的支付单。
    payment = payment_repository.get_payment_info(db, payment_id, user_id)
    if payment is None:
        raise PaymentNotFoundError
    order = db.get(Order, payment.order_id)
    # 已成功的支付直接返回，避免重复执行后续状态更新。
    if payment.status == OrderStatus.SUCCEEDED:
        return PaymentCallbackResult(
            duplicate=True,
            payment_status= payment.status,
            order_status= order.status.value
        )

    # 构造一份假的第三方回调数据；时间戳让事件编号和交易编号尽量保持唯一。
    paylod = MockPaymentCallback(
        event_id=f'evt_{time.time()}',
        payment_number = payment.payment_number,
        amount=payment.amount,
        status="succeeded",
        timestamp=int((time.time())),
        provider_transaction_id=f'mock_tx_{time.time()}',
    )

    print("payload", paylod)

    # 先为模拟数据签名，再交给正式回调函数验签和处理。
    return process_callback(db, paylod, sign_callback(paylod))

def restore_order_stock(db: Session, order: Order) -> None:
    sku_ids = sorted((item.sku_id for item in order.items if item.sku_id), key=str)
    if not sku_ids:
        return
    statement = select(ProductSku).where(ProductSku.id.in_(sku_ids)).order_by(ProductSku.id).with_for_update()
    sku_map = {sku.id: sku for sku in db.scalars(statement)}
    for item in order.items:
        if item.sku_id in sku_map:
            sku_map[item.sku_id].stock += item.quantity



def close_expired_orders(db: Session, limit: int = 100) -> int:
    now = datetime.now(UTC)
    statement = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.status == OrderStatus.PENDING_PAYMENT, Order.payment_expires_at <= now)
        .order_by(Order.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    orders = list(db.scalars(statement).unique())
    for order in orders:
        restore_order_stock(db, order)
        coupon_service.release(db, order.user_coupon_id)
        payment = db.scalar(select(Payment).where(Payment.order_id == order.id).with_for_update())
        if payment is not None and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CLOSED
        order.status = OrderStatus.CANCELLED
        order.cancel_reason = "支付超时自动关闭"
        order.cancelled_at = now
        db.add(OrderStatusLog(
            order_id=order.id,
            from_status=OrderStatus.PENDING_PAYMENT,
            to_status=OrderStatus.CANCELLED,
            operator_type="system_job",
            reason="payment timeout",
        ))
    db.commit()
    return len(orders)
