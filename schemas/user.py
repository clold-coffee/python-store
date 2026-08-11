
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator, Field, ConfigDict

from models.user import UserRole

class CreateUser(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=1, max_length=100)

    @field_validator('username')
    @classmethod
    def validate_username(cls, value:str) ->str:
        value = value.strip()
        if value == '':
            raise ValueError('username cannot be an empty string')
        return value



class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    hashed_password:str
    password: str
    is_active: bool
    role: UserRole
    role: UserRole
    created_at: datetime
    updated_at: datetime