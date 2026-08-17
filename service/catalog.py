from __future__ import annotations

import math
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    Category,
    Brand,
    Product,
    ProductSku,
    ProductImage,
    ProductStatus
)
from repository.catagory import (
    get_category,
    get_brand,
    get_product,
    get_sku,
    list_public_products
)
from schemas.catagroy import (
    CategoryCreate,
    CategoryUpdate,
    CreateBrand,
    BrandUpdate,
    CreateProduct,
    ProductUpdate,
    ProductDetail,
    ProductListItem,
    SkuCreate,
    SkuUpdate,
    ImageInput, ProductPage
)


class BrandNotFoundError(Exception):
    pass


class CategoryNotFoundError(Exception):
    pass


class CatalogNotFoundError(Exception):
    pass


class CatalogValidationError(Exception):
    pass


# 什么意思？有什么用？
class CatalogConflictError(Exception):
    pass


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CatalogConflictError("slug or SKU code already exists") from exc


def create_category(db: Session, payload: CategoryCreate) -> Category:
    category = Category(**payload.model_dump())
    db.add(category)
    _commit(db)
    db.refresh(category)
    return category


# payload中不是有id吗？为什么还有单独写id参数
# 目的是为遵守RESTful规范，category_id明确指出修改数据，payload是修改内容
def update_category(db: Session, category_id: int, payload: CategoryUpdate) -> CategoryUpdate:
    # 根据ID查询内容是否在数据库
    category = get_category(db, category_id)
    if category is None:
        raise CatalogNotFoundError
    # 更新category 为什么用这种方式，不使用数据库sql语句？
    # 动态设置属性名 setattr(对象, 属性名, 属性值) ：setattr(category, "name", "数码产品") 即为 category.name = "数码产品"
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    _commit(db)
    db.refresh(category)
    return category


def create_brand(db: Session, payload: CreateBrand) -> Brand:
    brand = Brand(**payload.model_dump())
    db.add(brand)
    _commit(db)
    db.refresh(brand)
    return brand


def update_brand(db: Session, brand_id: int, payload: BrandUpdate) -> Brand:
    brand = get_brand(db, brand_id)
    if brand is None:
        raise BrandNotFoundError
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    _commit(db)
    db.refresh(brand)
    return brand


def _validate_relations(db: Session, category_id: int, brand_id: int | None) -> None:
    category = get_category(db, category_id)
    if category is None:
        raise CatalogValidationError("category does not exist")
    if brand_id is not None and get_brand(db, brand_id) is None:
        raise CatalogValidationError("brand does not exist")


# 创建对象中有包含关联表、其他子对象的参考方式
def create_product(db: Session, payload: CreateProduct) -> Product:
    _validate_relations(db, payload.category_id, payload.brand_id)
    #  ProductStatus.ON_SALE => 表示商品在售
    # not any(sku.is_active for sku in payload.skus) => 没有存在任何一个活跃的SKU
    if payload.status == ProductStatus.ON_SALE and not any(sku.is_active for sku in payload.skus):
        raise CatalogValidationError("on-sale product requires an active SKU")

    product = Product(
        category_id=payload.category_id,
        brand_id=payload.brand_id,
        name=payload.name,
        slug=payload.slug,
        subtitle=payload.subtitle,
        description=payload.description,
        cover_image_url=str(payload.cover_image_url) if payload.cover_image_url else None,
        status=payload.status,
        skus=[ProductSku(**sku.model_dump()) for sku in payload.skus],
        images=[
            ProductImage(
                image_url=str(image.image_url),
                all_text=image.all_text,
                sort_order=image.sort_order

            ) for image in payload.images
        ]
    )

    db.add(product)
    _commit(db)
    return get_product(db, product.id)


def update_product(db: Session, product_id: int, payload: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    if product is None:
        raise CatalogValidationError("product does not exist")
    values = payload.model_dump(exclude_unset=True)
    category_id = values.get('category_id', product.category_id)
    brand_id = values.get('brand_id', product.brand_id)
    _validate_relations(db, category_id, brand_id)

    # cover_image_url 转成字符串
    if "cover_image_url" in values and values["cover_image_url"] is not None:
        values["cover_image_url"] = str(values["cover_image_url"])

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    _commit(db)
    db.refresh(product)
    return product


def to_list_item(product: Product, public: bool = True) -> ProductListItem:
    skus = [sku for sku in product.skus if sku.is_active] if public else product.skus
    prices = [sku.price for sku in skus]
    if not prices:
        prices = [Decimal("0.00")]
    return ProductListItem(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        cover_image_url=str(product.cover_image_url) if product.cover_image_url else None,
        status=product.status,
        category=product.category,
        brand=product.brand,
        min_price=min(prices),
        max_price=max(prices),
        total_stock=sum(sku.stock for sku in product.skus),
    )


def to_detail(product: Product, public: bool = True) -> ProductDetail:
    item = to_list_item(product, public)
    skus = [] if public else product.skus
    return ProductDetail(
        **item.model_dump(),
        description=product.description,
        skus=skus,
        images=product.images,
        created_at=product.created_at,
        updated_at=product.updated_at
    )


def change_product_status(db: Session, product_id: int, status: ProductStatus) -> Product:
    product = get_product(db, product_id)
    if product is None:
        raise CatalogValidationError("product does not exist")
    if status == ProductStatus.ON_SALE and not any(sku.is_active for sku in product.skus):
        raise CatalogValidationError("on-sale product requires an active SKU")
    product.status = status
    _commit(db)
    return get_product(db, product.id)


def add_sku(db: Session, product_id: int, sku: SkuCreate) -> ProductSku:
    product = get_product(db, product_id)
    if product is None:
        raise CatalogValidationError("product does not exist")
    sku = ProductSku(product_id=product.id, **sku.model_dump())
    db.add(sku)
    _commit(db)
    db.refresh(sku)
    return sku


# 为什么不返回 SKuRead，或者 SkuUpdate 数据类型
# 因为更新的是sku可以是局部更新，但是要返回完整的 sku字段，所以用 ProductSku 数据类型
def update_sku(db: Session, product_id: int, sku_id: int, payload: SkuUpdate) -> ProductSku:
    product = get_product(db, product_id)
    sku = get_sku(db, sku_id)
    if product is None:
        raise CatalogValidationError("product does not exist")
    if sku is None:
        raise CatalogValidationError("sku does not exist")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sku, key, value)

    _commit(db)
    db.refresh(sku)
    return sku


def replace_images(db: Session, product_id: int, images: list[ImageInput]) -> ProductSku:
    product = get_product(db, product_id)
    if product is None:
        raise CatalogValidationError("product does not exist")
    product.images = [(ProductImage(**i.model_dump())) for i in images]
    _commit(db)
    return get_product(db, product.id)



def get_public_page(db: Session, **filters: object) -> ProductPage:
    products, total = list_public_products(db, **filters)  # type: ignore[arg-type]
    page = int(filters["page"])
    page_size = int(filters["page_size"])
    return ProductPage(
        items=[to_list_item(product) for product in products],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


