

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pygments.styles import native
from sqlalchemy import Integer, String, Boolean, DateTime, func, ForeignKey, Enum as sqlEnum, JSON, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ProductStatus(str, enum.Enum):
    """SPU（商品）的生命周期状态。加入购物车只允许 ON_SALE。"""

    DRAFT = "draft"
    ON_SALE = "on_sale"
    OFF_SALE = "off_sale"

class Category(Base):
    __tablename__ = "category"
    id:Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name:Mapped[str] = mapped_column(String(80))
    slug:Mapped[str] = mapped_column(String(80),unique=True,index=True)
    description:Mapped[str] = mapped_column(String(255),default='')
    sort_order:Mapped[int] = mapped_column(Integer,default=0, server_default='0')
    is_active:Mapped[bool] = mapped_column(Boolean,default=True, server_default='0')
    created_at:Mapped[datetime] = mapped_column(DateTime,default=func.now(), server_default=func.now())
    updated_at:Mapped[datetime] = mapped_column(DateTime,default=func.now(),server_default=func.now(), onupdate=func.now())
    products: Mapped[list['Product']] = relationship(back_populates="category")


class Brand(Base):
    __tablename__ = "brands"

    id:Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    name:Mapped[str] = mapped_column(String(255),unique=True,index=True)
    slug:Mapped[str] = mapped_column(String(255))
    description:Mapped[str] = mapped_column(String(255),default='',server_default="")

    logo_url:Mapped[str] = mapped_column(String(255),nullable=True)

    is_active:Mapped[bool] = mapped_column(Boolean,default=True, server_default='1')
    created_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=func.now())


    products: Mapped[list['Product']] = relationship(back_populates="brand")


class Product(Base):
    """SPU：描述一组共享名称、介绍和上下架状态的商品。"""

    __tablename__ = "product"

    id:Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    category_id:Mapped[int] = mapped_column(ForeignKey("category.id",ondelete="RESTRICT"), index=True)
    brand_id:Mapped[int] = mapped_column(ForeignKey("brands.id",ondelete="SET NULL"),index=True, nullable=True)
    name:Mapped[str] = mapped_column(String(255))
    slug:Mapped[str] = mapped_column(String(255),unique=True,index=True)
    subtitle:Mapped[str] = mapped_column(String(255),default='',server_default="")
    description:Mapped[str] = mapped_column(String(255),default='',server_default="")
    cover_image_url:Mapped[str] = mapped_column(String(255),nullable=True)
    # 【重点】add_to_cart 会检查这个状态；不是 ON_SALE 就不应允许加入购物车。
    status:Mapped[ProductStatus] = mapped_column(
        sqlEnum(ProductStatus, name="product_status", native_enum=False, length=20),
        default=ProductStatus.DRAFT,
        server_default="DRAFT",
        index=True
    )
    created_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=func.now())

    # 关系：商品属于哪个分类，属于哪个品牌
    category:Mapped[Category] = relationship(Category, back_populates="products")
    brand:Mapped[Brand] = relationship( back_populates="products")

    # 关系：一个商品有多个sku
    skus:Mapped[list['ProductSku']] = relationship(back_populates="product", cascade="all, delete-orphan")

    # 关系： 一个商品有多张图片
    images:Mapped[list['ProductImage']] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductSku(Base):
    """SKU：真正可以定价、统计库存并加入购物车的最小销售单元。

    例如“某款手机”是 SPU，“黑色 + 256GB”是一个具体 SKU。
    """

    __tablename__ = "product_skus"

    # CartItemAdd.sku_id 最终会查询这个主键。
    id:Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    # ondelete 值有哪些？有什么用
    product_id: Mapped[int]= mapped_column(ForeignKey("product.id",ondelete="CASCADE"), index=True)
    sku_code:Mapped[str] = mapped_column(String(255),unique=True,index=True)
    name:Mapped[str] = mapped_column(String(255),default='',server_default="")
    # SKU 自身的启用开关；即使所属商品已上架，禁用的 SKU 也不可购买。
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # 什么意思？
    attributes:Mapped[dict[str,Any]] = mapped_column(JSON,default=dict)
    # build_cart 用当前价格乘以购物车数量，计算响应中的 subtotal。
    price:Mapped[Decimal] = mapped_column(Numeric(12,2))
    market_price:Mapped[Optional[Decimal]] = mapped_column(Numeric(12,2))
    # 【重点】理论上 add_to_cart 应同时受真实库存和购物车数量上限约束。
    stock:Mapped[int] = mapped_column(Integer,default=0,server_default='0')
    created_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=func.now())

    # _get_sellable_sku 使用 joinedload 提前加载所属 Product，以检查上架状态。
    product:Mapped[Product] = relationship(Product, back_populates="skus")


class ProductImage(Base):
    __tablename__ = "product_images"

    id:Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id",ondelete="CASCADE"),index=True)
    image_url:Mapped[str] = mapped_column(String(500))
    all_text:Mapped[str] = mapped_column(String(255),default='',server_default="")
    sort_order:Mapped[int] = mapped_column(Integer,default=0, server_default='0')

    product:Mapped[Product] = relationship(Product, back_populates="images")
