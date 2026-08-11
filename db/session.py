from typing import Generator

from sentry_sdk.session import Session
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker


# 数据库类型+驱动://用户名:密码@数据库地址:端口/数据库名
DATABASE_URL = "mysql+pymysql://root:123456@localhost:3306/online_store"

engine = create_engine(DATABASE_URL, echo=True)


def check_database() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * from user"))
        print(result.fetchone())


# 创建session，用于访问数据库
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False
)

# 为每个请求提供独立会话，并在请求结束后关闭。"
def get_db() -> Generator[Session, None, None]:
   with SessionLocal() as session:
       yield session