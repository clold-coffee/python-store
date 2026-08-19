from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sentry_sdk.session import Session
from sqlalchemy import select, exists, Select, func
from sqlalchemy.orm import selectinload

from models import ProductSku
from models.catalog import Category, Brand, Product, ProductStatus


# 根据ID查询 catagory
def get_category(db: Session, category_id: int) -> Category:
    return db.get(Category, category_id)


def list_active_categories(db: Session) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name))
    )


# brand相关
def list_active_brands(db: Session) -> list[Brand]:
    return list(
        db.scalars(
            select(Brand)
            .where(Brand.is_active.is_(True))
        )
    )


def get_brand(db: Session, brand_id: int) -> Brand:
    return db.get(Brand, brand_id)


def get_product(db: Session, product_id: int) -> Product | None:
    statement = (
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.skus),
            selectinload(Product.images),
        )
        .where(Product.id == product_id)
    )
    return db.scalar(statement)


def get_sku(db: Session, sku_id: int) -> ProductSku | None:
    return db.get(ProductSku, sku_id)


# 构建查询条件
def _build_search_conditions(
        keyword: str | None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
) -> list:
    active_sku = exists(
        select(ProductSku.id).where(
ProductSku.product_id == Product.id,
            ProductSku.is_active.is_(True)
        )
    )

    conditions = [Product.status == ProductStatus.ON_SALE, active_sku]
    if keyword:
        conditions.append(Product.name.ilike(f"%{keyword.strip()}%"))
    if category_id:
        conditions.append(Category.id == category_id)
    if brand_id:
        conditions.append(Brand.id == brand_id)
    if min_price is not None or max_price is not None:
        price_conditions = [
            ProductSku.product_id == Product.id,
            ProductSku.is_active.is_(True),
        ]
        if min_price is not None:
            price_conditions.append(ProductSku.price >= min_price)
        if max_price is not None:
            price_conditions.append(ProductSku.price <= max_price)

        conditions.append(
            exists(
                select(ProductSku.id)
                .where(*price_conditions)
            )
        )
    return conditions


# 构建 排序
def _build_select_statement(conditions: list, sort_by: str, sort_order: str):
    statement: Select(tuple[Product]) = select(Product).options(
        selectinload(Product.skus),
        selectinload(Product.category),
        selectinload(Product.brand),
    ).where(*conditions)

    if sort_by == 'price':
        prices = (
            select(
                ProductSku.product_id,
                func.min(ProductSku.price).label('min_price')
            )
            .where(ProductSku.is_active.is_(True))
            .group_by(ProductSku.product_id)
            .subquery()
        )
        statement = statement.join(
            prices,
            prices.c.product_id == Product.id
        )
        order_column = prices.c.min_price
    else:
        order_column = Product.created_at

    statement = statement.order_by(
        order_column.asc() if sort_order == 'asc' else order_column.desc(),
        Product.id
    )

    return statement


def list_public_products(
        db: Session,
        *,
        page: int = 1,
        page_size: int,
        keyword: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
) -> tuple[list[Product], int] | None:
    # 构建查询条件
    conditions = _build_search_conditions(
        keyword, category_id, brand_id, min_price, max_price
    )

    # 设置排序
    statement = _build_select_statement(conditions, sort_by, sort_order)

    # 计算总数和分页
    total = db.scalar(
        select(func.count(Product.id)).where(*conditions)
    ) or 0

    items = list(
        db.scalars(
            statement.offset((page - 1) * page_size)
            .limit(page_size)
        ).unique()
    )
    return items, total



def get_public_product_by_slug(db: Session, slug: str) -> Product | None:
    statement = (
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.skus),
            selectinload(Product.images),
        )
        .where(Product.slug == slug, Product.status == ProductStatus.ON_SALE)
    )
    return db.scalar(statement)

