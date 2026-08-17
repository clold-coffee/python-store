from decimal import Decimal
from typing import List, Annotated, Optional
from unicodedata import category

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.openapi.utils import status_code_ranges
from pydantic import ValidationError
from sqlalchemy import true

from api.deps import DatabaseSession
from models import Product

from schemas.catagroy import CategoryRead, CategoryCreate, CreateBrand, BrandRead, CategoryUpdate, BrandUpdate, \
    CreateProduct, ProductRead, ProductUpdate, ProductDetail, ProductStatusUpdate, SkuRead, SkuCreate, SkuUpdate, \
    ImageInput, SortBy, SortOrder, ProductPage
from repository import catagory as CategoryRepository
from service import catalog as CategoryService

router = APIRouter(prefix='/catelog', tags=['商品目录'])


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CategoryService.CatalogNotFoundError):
        return HTTPException(status_code=404, detail="catalog resource not found")
    if isinstance(exc, CategoryService.CatalogConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CategoryService.CatalogValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="unexpected catalog error")


@router.get('/category', response_model=list[CategoryRead], status_code=200, summary="获取商品分类")
def list_category(db: DatabaseSession) -> List[CategoryRead]:
    return [CategoryRead.model_validate(item) for item in CategoryRepository.list_active_categories(db)]


@router.post('/category', response_model=CategoryRead, status_code=200, summary='新增商品分类')
def create_category_item(db: DatabaseSession, payload: CategoryCreate) -> CategoryRead:
    try:
        return CategoryRead.model_validate(CategoryService.create_category(db, payload))
    # 这里捕获的错误要和 create_category 抛出的错误一样，这是自定义的错误类型
    except CategoryService.CatalogConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch(
    '/category/{category_id}',
    response_model=CategoryUpdate,
    status_code=status.HTTP_200_OK,
    summary='更新商品分类'
)
def update_category_item(db: DatabaseSession, payload: CategoryUpdate, category_id: int) -> CategoryRead:
    try:
        return CategoryRead.model_validate(CategoryService.update_category(db, category_id, payload))
    except CategoryService.CatalogNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str('Category not found')
        )


@router.post(
    "/brand",
    response_model=BrandRead,
    status_code=200,
    summary='创建品牌'
)
def create_brand(db: DatabaseSession, paylod: CreateBrand) -> BrandRead:
    try:
        return BrandRead.model_validate(CategoryService.create_brand(db, paylod))
    except CategoryService.CatalogConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch(
    '/brand/{brand_id}',
    response_model=BrandRead,
    status_code=200,
    summary='更新品牌信息'
)
def update_brand(db: DatabaseSession, payload: BrandUpdate, category_id: int) -> BrandRead:
    try:
        return BrandRead.model_validate(CategoryService.update_brand(db, category_id, payload))
    except CategoryService.BrandNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str("Brand not found")
        )


@router.get(
    '/brand/list',
    response_model=list[BrandRead],
    status_code=200,
    summary='获取所有品牌'
)
def list_brand(db: DatabaseSession) -> List[BrandRead]:
    return [BrandRead.model_validate(item) for item in CategoryRepository.list_active_brands(db)]


@router.post(
    '/product',
    response_model=ProductRead,
    status_code=200,
    summary='创建产品'
)
def create_product(db: DatabaseSession, paylod: CreateProduct) -> ProductRead:
    try:
        return ProductRead.model_validate(CategoryService.create_product(db, paylod))
    except CategoryService.CatalogConflictError as e:
        raise translate_error(e) from e


@router.patch(
    '/product/{product_id}',
    response_model=ProductDetail,
    status_code=200,
    summary='更新产品'
)
def update_product(db: DatabaseSession, payload: ProductUpdate, product_id: int) -> ProductDetail:
    try:
        return CategoryService.to_detail(CategoryService.update_product(db, product_id, payload), False)
    except (
            CategoryService.CatalogConflictError,
            CategoryService.CatalogValidationError
    ) as e:
        raise translate_error(e) from e


@router.patch(
    '/product/{product_id}/status',
    response_model=ProductDetail,
    status_code=200,
    summary='更新产品状态'
)
def change_product_status(db: DatabaseSession, payload: ProductStatusUpdate, product_id: int) -> ProductDetail:
    try:
        product = CategoryService.change_product_status(db, product_id, payload.status)
        return CategoryService.to_detail(product)
    except(
            CategoryService.CatalogConflictError,
            CategoryService.CatalogValidationError
    ) as e:
        raise translate_error(e) from e


@router.post(
    "/product/{product_id}/skus",
    response_model=SkuRead,
    status_code=200,
    summary='添加sku'
)
def add_sku(db: DatabaseSession, paylod: SkuCreate, product_id: int) -> SkuRead:
    try:
        return SkuRead.model_validate(CategoryService.add_sku(db, product_id, paylod))
    except (
            CategoryService.CatalogConflictError,
            CategoryService.CatalogValidationError
    ) as e:
        raise translate_error(e) from e


@router.patch(
    "/product/{product_id}/sku/{sku_id}",
    response_model=SkuRead,
    status_code=200,
    summary='更新sku'
)
def update_sku(db: DatabaseSession, paylod: SkuUpdate, product_id: int, sku_id: int) -> SkuRead:
    try:
        return SkuRead.model_validate(CategoryService.update_sku(db, product_id, sku_id, paylod))
    except(
            CategoryService.CatalogConflictError,
            CategoryService.CatalogValidationError
    ) as e:
        raise translate_error(e) from e


@router.put(
    "/product/{product_id}",
    response_model=ProductRead,
    status_code=200,
    summary='更新产品图片'
)
def put_product_images(db: DatabaseSession, payload: list[ImageInput], product_id: int) -> ProductRead:
    try:
        return ProductRead.model_validate(CategoryService.replace_images(db, product_id, payload))
    except (
            CategoryService.CatalogConflictError,
            CategoryService.CatalogValidationError
    ) as e:
        raise translate_error(e) from e

@router.get("/products", response_model=ProductPage, summary="分页搜索在售商品")
def list_products(
    db: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
    keyword:Optional[Annotated[str, Query(max_length=80)]] = None,
    category_id:Optional[int] = None,
    brand_id: Optional[int]  = None,
    min_price: Optional[Annotated[Decimal, Query(ge=0)]] = None,
    max_price:Optional[ Annotated[Decimal, Query(ge=0)]] = None,
    sort_by: SortBy = "created_at",
    sort_order: SortOrder = "desc",
) -> ProductPage:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="min_price cannot exceed max_price")
    return CategoryService.get_public_page(
        db, page=page, page_size=page_size, keyword=keyword,
        category_id=category_id, brand_id=brand_id, min_price=min_price,
        max_price=max_price, sort_by=sort_by, sort_order=sort_order,
    )


@router.get("/product/{slug}", response_model=ProductDetail,summary='商品在售详情')
def get_product_detail(
    db: DatabaseSession,
    slug: str,
) -> ProductDetail:
     product = CategoryRepository.get_public_product_by_slug(db, slug)

     if product is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
     return CategoryService.to_detail(product)
