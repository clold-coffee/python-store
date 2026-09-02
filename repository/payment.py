import datetime

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from models.payment import Payment, Coupon, UserCoupon


def get_payment_by_request(db: Session, user_id: int, request_id: str) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.client_request_id == request_id
        )
    )


def get_payment_info(db: Session, payment_id: int, user_id: int) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.id == payment_id
        )
    )


def list_available_coupons(db: Session, now: datetime) -> list[Coupon]:
    statement = select(Coupon).where(
        Coupon.is_active.is_(True),
        Coupon.valid_from <= now,
        Coupon.valid_until > now,
        Coupon.claimed_quantity < Coupon.total_quantity,
    ).order_by(Coupon.minimum_amount, Coupon.discount_value.desc())
    return list(db.scalars(statement))


def list_user_coupons(db: Session, user_id: int) -> list[UserCoupon]:
    statement = (select(UserCoupon)
                 .options(joinedload(UserCoupon.coupon))
                 .where(UserCoupon.user_id == user_id)
                 .order_by(UserCoupon.claimed_at.desc())
                 )
    return list(db.scalars(statement).unique())



def create_coupon(db: Session, payload) -> Coupon:
    coupon = Coupon(
        code=payload.code,
        name=payload.name,
        description=payload.description or "",
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        minimum_amount=payload.minimum_amount,
        total_quantity=payload.total_quantity,
        claimed_quantity=0,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        is_active=payload.is_active,
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon