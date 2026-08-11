# 定义数据库和python中的字段映射关系
from dataclasses import Field
from datetime import datetime
from enum import Enum

from db.base import Base


from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey,func, Enum as sqlEnum

from sqlalchemy.orm import Mapped, mapped_column



class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"

class User(Base):
    __tablename__ = 'user'
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        sqlEnum(UserRole, name="user_role", native_enum= False, length = 20),
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER,
    )
    password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true",)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),  default=func.now(),server_default=func.now())

