from fastapi import APIRouter

from api.deps import AdminUser

router = APIRouter(prefix="/user", tags=["admi"])

@router.get("/admi/", tags=["admi"])
async def get_admin(current:AdminUser) -> dict[str, str]:

    return {'msg': 'welcome ' + current.username}
