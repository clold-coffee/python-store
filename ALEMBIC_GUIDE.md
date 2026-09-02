# Alembic 使用指南

Alembic 是 SQLAlchemy 的数据库迁移工具，用于记录和执行数据库表结构变更。

典型工作流程：

```text
修改 SQLAlchemy 模型
    ↓
生成迁移文件
    ↓
人工审查迁移文件
    ↓
执行迁移
    ↓
数据库结构更新
```

## 1. 确认 Python 运行环境

在项目根目录执行：

```bash
which python
python --version
python -m pip --version
```

`which python` 应该指向项目虚拟环境，例如：

```text
.../python-online-store/.venv/bin/python
```

激活项目虚拟环境：

```bash
source .venv/bin/activate
```

如果项目希望使用 Python 3.13，但 `.venv` 仍然是 Python 3.9，需要用 Python 3.13 重新创建虚拟环境。虚拟环境一旦创建，不会随系统 Python 自动升级。

## 2. 安装 Alembic

确保已激活项目虚拟环境，然后执行：

```bash
python -m pip install alembic
python -m alembic --version
```

建议将 Alembic 加入 `requirements.txt`，避免重建环境时遗漏。

## 3. 初始化 Alembic

每个项目只需执行一次：

```bash
python -m alembic init alembic
```

执行后会生成：

```text
alembic.ini
alembic/
├── env.py
├── script.py.mako
└── versions/
```

- `alembic.ini`：Alembic 主配置文件。
- `alembic/env.py`：连接数据库并加载 SQLAlchemy metadata。
- `alembic/versions/`：保存历史迁移文件。

如果项目中已经有 `alembic.ini` 和 `alembic/` 目录，不要再次执行 `init`。

## 4. 配置数据库连接
·
可以在 `alembic.ini` 中配置 SQLAlchemy URL：

```ini
sqlalchemy.url = mysql+pymysql://<username>:<password>@localhost:3306/online_store
```

实际项目不建议将真实密码提交到 Git。更安全的做法是在 `env.py` 中从环境变量或项目配置读取数据库 URL。

Alembic 只管理表结构，通常不负责创建 MySQL 数据库本身。`online_store` 数据库需要先存在。

## 5. 配置 SQLAlchemy metadata

Alembic 必须知道哪些 SQLAlchemy 模型参与数据库对比。

在 `alembic/env.py` 中导入共同的 `Base` 和所有模型模块：

```python
from db.base import Base

import models.user
import models.catalog

target_metadata = Base.metadata
```

导入模型模块的目的是让模型类注册到 `Base.metadata`。如果没有导入，Alembic 可能无法发现那些表。

## 6. 正确定义 SQLAlchemy 模型

数据库模型必须继承 SQLAlchemy 的 `Base`，不是 Pydantic 的 `BaseModel`：

```python
from db.base import Base


class Category(Base):
    __tablename__ = "category"
```

### Python 默认值与数据库默认值

```python
stock: Mapped[int] = mapped_column(
    Integer,
    default=0,
    server_default="0",
)
```

- `default=0`：SQLAlchemy/Python 插入数据时使用。
- `server_default="0"`：由数据库表结构提供默认值。

`server_default` 应使用 SQL 字符串或 SQL 表达式，不能直接传入 Python 整数。

MySQL 的 `Boolean` 实际上通常是 `TINYINT(1)`，建议使用：

```python
is_active: Mapped[bool] = mapped_column(
    Boolean,
    default=True,
    server_default="1",
)
```

- `"1"` 表示真。
- `"0"` 表示假。

不要使用 `server_default="true"`，否则某些 MySQL 版本可能生成无效默认值。

### 外键删除规则

`ondelete` 是 `ForeignKey` 的参数：

```python
product_id: Mapped[int] = mapped_column(
    ForeignKey("product.id", ondelete="CASCADE"),
    index=True,
)
```

不要将 `ondelete` 直接传给 `mapped_column`。

常用值：

- `CASCADE`：删除父记录时同时删除子记录。
- `SET NULL`：删除父记录时将子记录外键设为 `NULL`，字段必须允许为空。
- `RESTRICT`：存在子记录时禁止删除父记录。

## 7. 生成迁移文件

修改模型后执行：

```bash
python -m alembic revision --autogenerate -m "create catalog tables"
```

`--autogenerate` 会对比：

```text
Base.metadata 中的模型
    ↔
当前数据库结构
```

然后在 `alembic/versions/` 中生成新迁移文件。

这个命令只生成文件，不会立即修改数据库。

## 8. 人工审查迁移文件

Alembic 自动生成的代码不一定完全符合业务预期，执行前必须检查。

迁移文件的两个主要函数：

```python
def upgrade() -> None:
    # 升级数据库时执行
    ...


def downgrade() -> None:
    # 回退数据库时执行
    ...
```

重点检查：

- 是否只创建或修改了预期的表。
- 是否意外修改了已有的 `user` 等表。
- 字段类型、长度和 `nullable` 是否正确。
- 默认值是否符合 MySQL 语法。
- 唯一索引和普通索引是否正确。
- 外键指向的表名是否正确。
- `ondelete` 行为是否符合业务预期。
- `downgrade()` 是否能够合理撤销 `upgrade()`。

迁移文件是生成时的模型快照。生成迁移后再修改模型，不会自动更新已生成的迁移文件。

对未执行的新迁移文件进行人工修正是正常工作流程。

## 9. 预览将要执行的 SQL

可以在不执行数据库变更的情况下输出 SQL：

```bash
python -m alembic upgrade head --sql
```

此步适合检查 MySQL 最终将收到的 `CREATE TABLE` 和 `ALTER TABLE` 语句。

## 10. 执行迁移

将数据库升级到最新版本：

```bash
python -m alembic upgrade head
```

执行成功后：

- Alembic 会执行迁移文件中的 `upgrade()`。
- 数据库中会有一张 `alembic_version` 表。
- `alembic_version` 会记录当前已执行的迁移版本。

MySQL DDL 通常是非事务性的。如果迁移在中途失败，之前成功的 `CREATE TABLE` 或 `ALTER TABLE` 可能已经生效，不一定会自动回滚。重试前应先检查当前数据库结构。

## 11. 查看迁移状态

查看数据库当前版本：

```bash
python -m alembic current
```

查看最新迁移版本：

```bash
python -m alembic heads
```

查看迁移历史：

```bash
python -m alembic history
```

查看详细历史：

```bash
python -m alembic history --verbose
```

## 12. 回退迁移

回退一个版本：

```bash
python -m alembic downgrade -1
```

回退到指定 revision：

```bash
python -m alembic downgrade <revision_id>
```

回退到最初状态：

```bash
python -m alembic downgrade base
```

回退可能删除表、字段或数据。在存在重要数据时，应先备份并检查 `downgrade()` 内容。

## 13. 日常修改表结构的流程

首次初始化完成后，日常只需重复以下流程：

1. 修改 SQLAlchemy 模型。
2. 生成迁移：

   ```bash
   python -m alembic revision --autogenerate -m "add product inventory fields"
   ```

3. 人工审查 `alembic/versions/` 中的新文件。
4. 预览 SQL：

   ```bash
   python -m alembic upgrade head --sql
   ```

5. 执行迁移：

   ```bash
   python -m alembic upgrade head
   ```

6. 确认版本：

   ```bash
   python -m alembic current
   ```

## 14. 已有数据库的注意事项

当数据库中已经有手动创建的表，而项目刚开始使用 Alembic 时，`--autogenerate` 可能会检测出大量已有表的差异。

例如：

- 字段长度不一致。
- 数据库允许 `NULL`，但模型不允许。
- 数据库缺少模型中定义的索引。
- 枚举名称和枚举值的存储方式不一致。

不要盲目执行这些变更。应根据本次迁移目标人工保留或删除对应的迁移操作。

## 15. 常见错误

### `No module named alembic`

原因：Alembic 没有安装到当前 `python` 对应的虚拟环境。

```bash
which python
python -m pip install alembic
```

### `Additional arguments should be named <dialectname>_<argument>, got 'ondelete'`

原因：`ondelete` 错误地传给了 `mapped_column`。

错误：

```python
mapped_column(ForeignKey("product.id"), ondelete="CASCADE")
```

正确：

```python
mapped_column(ForeignKey("product.id", ondelete="CASCADE"))
```

### `Argument 'arg' ... got <class 'int'>`

原因：`server_default` 直接传入了 Python 整数。

错误：

```python
server_default=0
```

正确：

```python
server_default="0"
```

### `Invalid default value for 'is_active'`

原因：MySQL 布尔字段收到了字符串默认值 `'true'` 或 `'false'`。

建议：

```python
server_default="1"  # True
server_default="0"  # False
```

如果迁移文件已经生成，除了修改模型，还要检查并修正未执行的迁移文件。

### `MappedAnnotationError` 与 `Mapped[Decimal | None]`

原因之一是当前虚拟环境仍在使用 Python 3.9，但模型使用了 Python 3.10+ 的 `|` 联合类型语法。

首先检查：

```bash
python --version
python -c "import sys; print(sys.executable)"
```

如果项目要求 Python 3.13，应使用 Python 3.13 重建 `.venv`。

### 修改模型后迁移内容没变

原因：已生成的迁移文件是历史快照，不会随模型自动更新。

处理方式：

- 如果迁移尚未应用，可以人工审查并修正当前迁移文件。
- 如果迁移已经应用，应再创建一个新迁移，不要改写已经在其他环境执行过的历史。

## 16. 命令速查

```bash
# 安装
python -m pip install alembic

# 初始化（只执行一次）
python -m alembic init alembic

# 自动生成迁移
python -m alembic revision --autogenerate -m "migration message"

# 预览 SQL
python -m alembic upgrade head --sql

# 升级到最新版本
python -m alembic upgrade head

# 查看当前版本
python -m alembic current

# 查看历史
python -m alembic history

# 回退一个版本
python -m alembic downgrade -1
```
