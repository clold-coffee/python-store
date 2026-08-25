from typing import Generator

# 【重点：疑似问题】这里导入的是 Sentry 的 Session，但 SessionLocal 实际创建的
# 是 SQLAlchemy Session。当前只影响类型提示，建议后续改为 sqlalchemy.orm.Session。
from sentry_sdk.session import Session
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker


# 数据库类型+驱动://用户名:密码@数据库地址:端口/数据库名
# DATABASE_URL = "mysql+pymysql://root:123456@localhost:3306/online_store"

from core.config import get_settings

database_url = get_settings().database_url
engine = create_engine(database_url, echo=True)


def check_database() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * from user"))
        print(result.fetchone())


# 创建session，用于访问数据库
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False
)

# 为每个请求提供独立会话，并在请求结束后关闭。
def get_db() -> Generator[Session, None, None]:
    """生成本次请求使用的数据库 Session。

    【重点】``yield`` 前的对象会被注入路由；请求结束后重新回到这里，退出
    ``with`` 并关闭 Session。这样 add_item 无论成功还是异常都不会泄漏连接。
    """
    with SessionLocal() as session:
        yield session
