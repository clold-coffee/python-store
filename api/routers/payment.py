from queue import Queue
from typing import Annotated

from fastapi import APIRouter, status, Header, HTTPException

from api.deps import DatabaseSession, CurrentUser
from schemas.payment import PaymentRead, PaymentCreate, PaymentCallbackResult, MockPaymentCallback
import service.payment as service

router = APIRouter(prefix="/payments", tags=["支付相关接口"])


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (service.PaymentNotFoundError, service.PaymentOrderNotFoundError)):
        return HTTPException(status_code=404, detail="payment or order not found")
    if isinstance(exc, service.InvalidCallbackSignatureError):
        return HTTPException(status_code=401, detail="invalid callback signature")
    if isinstance(exc, service.StaleCallbackError):
        return HTTPException(status_code=400, detail="stale payment callback")
    if isinstance(exc, service.PaymentAmountError):
        return HTTPException(status_code=409, detail="payment amount mismatch")
    if isinstance(exc, service.PaymentExpiredError):
        return HTTPException(status_code=409, detail="payment window expired")
    if isinstance(exc, service.PaymentStateError):
        return HTTPException(status_code=409, detail="payment or order status does not allow this operation")
    return HTTPException(status_code=500, detail="unexpected payment error")


@router.post("",
             response_model=PaymentRead,
             status_code=status.HTTP_201_CREATED,
             summary="创建支付订单"
             )
def create_payment(
        payload: PaymentCreate,
        current_user: CurrentUser,
        db: DatabaseSession,
        idempotency_key: Annotated[str, Header(alias="Idempotency-key", min_length=8, max_length=64)]
) -> PaymentRead:
    try:
        return PaymentRead.model_validate(
            service.create_payment(
                db,
                current_user.id,
                payload.order_id,
                idempotency_key
            )
        )
    except (
            service.PaymentExpiredError,
            service.PaymentOrderNotFoundError,
            service.PaymentStateError
    ) as exc:
        raise translate_error(exc) from exc


@router.get("/{payment_id}",
            response_model=PaymentRead,
            status_code=status.HTTP_200_OK,
            summary="查看订单详情")
def get_payment(
        payment_id: int,
        current_user: CurrentUser,
        db: DatabaseSession,
) -> PaymentRead:
    try:
        return PaymentRead.model_validate(service.get_payment_details(db, payment_id, current_user.id))
    except (
            service.PaymentNotFoundError
    ) as exc:
        raise translate_error(exc) from exc


#
@router.post("/{payment_id}/mock-confirm", response_model=PaymentCallbackResult, summary="模拟第三方完成支付")
def mock_confirm(payment_id: int, current_user: CurrentUser, db: DatabaseSession) -> PaymentCallbackResult:
    try:
        return service.mock_confirm(db, current_user.id, payment_id)
    except (
        service.PaymentNotFoundError, service.PaymentStateError,
        service.PaymentExpiredError, service.PaymentAmountError,
    ) as exc:
        raise translate_error(exc) from exc



@router.post("/callbacks/mockpay",
             response_model=PaymentCallbackResult,
             summary='MockPay, 异步通知（无需用户）')
def mockpay_callback(
        payload:MockPaymentCallback,
        db: DatabaseSession,
        signature: Annotated[str, Header(alias="Signature", min_length=64, max_length=128)]
) -> PaymentCallbackResult:
    try:
        return  service.process_callback(db,payload, signature)
    except (
        service.PaymentNotFoundError,
        service.PaymentOrderNotFoundError,
        service.PaymentStateError,
        service.PaymentExpiredError,
        service.InvalidCallbackSignatureError,
        service.StaleCallbackError,
        service.PaymentAmountError,
    ) as exc:
        raise translate_error(exc) from exc