
from fastapi import APIRouter, status,Response,HTTPException

from api.deps import CurrentUser
from schemas.order import AddressRead, AddressCreate, AddressUpdate
from repository import order as order_repository
from api.deps import DatabaseSession
from service import order as order_service

router = APIRouter(prefix="/address", tags=["收货地址"])


@router.post("/add",
             response_model=AddressRead,
             status_code=status.HTTP_201_CREATED,
             summary="添加收获地址"
             )
async def add_address(payload: AddressCreate, db: DatabaseSession, user: CurrentUser) -> AddressRead:
    try:
        return AddressRead.model_validate(order_service.address_create(db, payload, user.id))
    except order_service.AddressLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": str(e)}
        )


@router.get("",
            response_model=list[AddressRead],
            summary="获取地址列表"
            )
def get_addresses(db: DatabaseSession, user: CurrentUser) -> list[AddressRead]:
    address_list = order_repository.list_addresses(db, user.id)
    return [AddressRead.model_validate(item) for item in address_list]


@router.patch("/{address_id}",
              response_model=AddressRead,
              status_code=status.HTTP_200_OK,
              summary="修改地址"
              )
def update_address(payload: AddressUpdate, address_id: int, db: DatabaseSession, user: CurrentUser) -> AddressRead:
    try:
        return AddressRead.model_validate(order_service.address_update(db, payload, user.id, address_id))
    except (
            order_service.AddressLimitError,
            order_service.AddressNotFount,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": str(e)}
        )


@router.delete("/{address_id}",
               status_code=status.HTTP_200_OK,
               summary="删除地址")
def delete_address(address_id: int, db: DatabaseSession, user: CurrentUser) -> Response:
    try:
        order_service.delete_address(db,  address_id,user.id,)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": str(e) or '地址不存在'}
        )

    return Response(status_code=status.HTTP_200_OK, content="ok")

