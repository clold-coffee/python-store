from __future__ import annotations



from sqlalchemy.orm import Session
from sqlalchemy import select

from models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return db.scalar(statement)

def get_user_by_id(db: Session, id: int) -> User | None:
    statement = select(User).where(User.id == id)
    return db.scalar(statement)

def get_user_by_username(db: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return db.scalar(statement)