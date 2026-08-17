
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Any, Literal

from pydantic import BaseModel, Field, ConfigDict, HttpUrl

from models import ProductStatus


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    description: str = Field(default='', max_length=255)
    sort_order: int = Field(default=0, ge=0)

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] =None

class CategoryRead(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


# Brand相关
class CreateBrand(BaseModel):
    name:str
    slug:str
    description:str
    logo_url: str

class BrandRead(CreateBrand):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None



class SkuCreate(BaseModel):
    name: str
    sku_code: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    price: Optional[Decimal]
    market_price: Optional[Decimal] = None
    is_active: Optional[bool] = None
    stock: Optional[int] = 0

class SkuUpdate(BaseModel):
    name: Optional[str]  = Field(default=None, min_length=1, max_length=120)
    attributes: Optional[dict[str, Any] ] = None
    price: Optional[Decimal]  = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    market_price: Decimal  = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    stock:Optional[ int]  = Field(default=None, ge=0)
    is_active: Optional[bool ] = None

class SkuRead(SkuCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ImageInput(BaseModel):
    image_url:HttpUrl
    all_text: str
    sort_order: int



class ImageRead(ImageInput):
    model_config = ConfigDict(from_attributes=True)
    id: int

class CreateProduct(BaseModel):
    category_id: int
    brand_id: Optional[int] = None
    name: str
    subtitle: str
    description: str
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=180)



    cover_image_url: Optional[HttpUrl] = None
    skus: list[SkuCreate] = Field(min_length=1)
    images:list[ImageInput] = Field(min_length=1)
    status:Optional[ProductStatus] = ProductStatus.DRAFT


class ProductRead(CreateProduct):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skus: list[SkuRead]
    images: list[ImageRead]



class ProductUpdate(BaseModel):
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    subtitle: Optional[str] = None
    cover_image_url: Optional[HttpUrl] = None

class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductListItem(BaseModel):
    id: int
    name: str
    slug: str
    subtitle: str
    cover_image_url: Optional[HttpUrl] = None
    status: ProductStatus
    category: CategoryRead
    brand: Optional[BrandRead]
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    total_stock: int

class ProductDetail(ProductListItem):
    model_config = ConfigDict(from_attributes=True)

    description: str
    skus: list[SkuRead]
    images: list[ImageRead]
    created_at: datetime
    updated_at: datetime

class ProductPage(BaseModel):
    items: list[ProductListItem]
    total:int
    page:int
    page_size:int
    pages:int

SortBy = Literal['created_at', 'price']
SortOrder = Literal['asc', 'desc']


