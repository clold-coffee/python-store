from fastapi import APIRouter, status, HTTPException

import repository
from api.deps import CurrentUser, DatabaseSession, AdminUser
from schemas.payment import CouponRead, UserCouponRead, CouponCreate
from service import coupon as service

router = APIRouter(prefix="/coupon", tags=["优惠券相关接口"])



@router.post("/{coupon_id}/claim",
             response_model=UserCouponRead,
             status_code=status.HTTP_201_CREATED,
             summary="领取优惠券")
def claim_coupon(coupon_id: int, current_user: CurrentUser, db: DatabaseSession) -> UserCouponRead:
    try:
        return UserCouponRead.model_validate(service.claim(db, current_user.id, coupon_id))
    except service.CouponNotFoundError as exc:
        raise HTTPException(status_code=404, detail="coupon not found") from exc
    except service.CouponUnavailableError as exc:
        raise HTTPException(status_code=409, detail="coupon is unavailable") from exc



@router.get("", response_model=list[CouponRead], summary="查看当前可领取优惠券")
def list_coupons(db: DatabaseSession) -> list[CouponRead]:
    return [CouponRead.model_validate(item) for item in service.list_available(db)]

@router.get("/mine", response_model=list[UserCouponRead], summary="查看我的优惠券")
def list_my_coupons(db: DatabaseSession, current_user:CurrentUser) -> list[UserCouponRead]:
    return [ UserCouponRead.model_validate(item) for item in service.list_mine(db, current_user.id)]



@router.post("/create", response_model=CouponRead, status_code=status.HTTP_201_CREATED, summary="创建优惠券")
def create_coupon(payload: CouponCreate, db: DatabaseSession, _: AdminUser) -> CouponRead:
    try:
        return CouponRead.model_validate(service.create_coupon(db, payload))
    except service.CouponConflictError as exc:
        raise HTTPException(status_code=409, detail="coupon code conflict") from exc
