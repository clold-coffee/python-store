"""购物车的数据访问层（Repository）。

建议按下面的顺序阅读，难度会逐步提高：

1. 先看 :func:`_decode` / :func:`_encode`，理解模型与 JSON 的相互转换；
2. 再看 :func:`read_cart`，理解它如何从 Redis 取出一整个购物车；
3. 然后看 :func:`add_item` 的数量累加逻辑；
4. 最后学习 ``WATCH / MULTI / EXEC``，理解并发下如何避免覆盖更新。

当前购物车在 Redis 中使用 Hash（哈希表）保存，结构可以想象成：

    Redis key: mall:cart:user:1001
    field:     "25"                         # 商品 SKU 编号
    value:     {"quantity":2, ...}          # JSON 格式的购物车项

本文件只负责“读写 Redis 并转换数据”。商品是否可售、库存上限等业务规则由
``service/cart.py`` 决定；商品名称、价格等信息也由 Service 从数据库查询。
这样 Repository 不需要理解 HTTP 或完整的商品业务。
"""


# ======================== 当前生效代码 ========================
from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError
from redis import Redis

from schemas.car import StoredCartItem
from redis.exceptions import WatchError


class CartQuantityLimitError(Exception):
    """相加后的购物车数量超过 max_quantity。"""

    def __init__(self, limit: int) -> None:
        # 保存允许上限，Service 会把它转换为 CartStockError。
        self.limit = limit


class CartConcurrentUpdateError(Exception):
    """Redis 乐观锁连续冲突 5 次，当前更新未能完成。"""
    pass


def _decode(value: str | bytes | None) -> StoredCartItem | None:
    """把 Redis 中的一条 JSON 数据转换为 ``StoredCartItem``。

    入门理解：Redis 取出的内容是字符串（或字节串），业务代码更适合使用
    带有 ``quantity``、``selected``、``added_at`` 属性的 Python 对象。
    Pydantic 的 ``model_validate_json`` 会同时完成 JSON 解析和字段校验。

    Args:
        value: Redis 中保存的 JSON 字符串/字节串；键不存在时可能是 ``None``。

    Returns:
        数据合法时返回 ``StoredCartItem``；没有数据或数据损坏时返回 ``None``。

    进阶理解：函数名以下划线开头，表示它是本模块内部使用的辅助函数，
    并不希望其他模块把它当作公开接口直接调用。
    """
    # Redis 中没有这个 field，无须继续解析。
    if value is None:
        return None

    try:
        # 示例：'{"quantity": 2, "selected": true, ...}'
        # 会被转换成 StoredCartItem(quantity=2, selected=True, ...)。
        return StoredCartItem.model_validate_json(value)
    except (ValidationError, TypeError):
        # JSON 格式错误、缺少必填字段或字段类型不正确时都会校验失败。
        # 读取购物车时忽略单条坏数据，避免一个损坏项让整个购物车不可用。
        return None


def read_cart(redis: Redis, key: str) -> dict[int, StoredCartItem]:
    """从 Redis 读取指定购物车，并整理成以 SKU ID 为键的字典。

    Args:
        redis: 已建立连接的 Redis 客户端。
        key: 购物车在 Redis 中的键，例如 ``mall:cart:user:1001``。

    Returns:
        ``{sku_id: 购物车项}`` 形式的字典。例如：
        ``{25: StoredCartItem(quantity=2, ...)}``。
        Redis key 不存在或没有有效数据时，返回空字典。

    数据转换过程：
        Redis Hash -> 遍历 field/value -> field 转成整数 SKU ID
        -> value 经 ``_decode`` 转成模型 -> 放入结果字典。
    """
    # 先准备空结果；没有读取到有效购物车项时会原样返回它。
    result: dict[int, StoredCartItem] = {}

    # hgetall(key) 一次取出 Hash 中的全部 field/value。
    # 因为 Redis 客户端启用了 decode_responses，通常二者都是字符串。
    for field, value in redis.hgetall(key).items():
        try:
            # Redis Hash 的 field 是字符串，而数据库中的 SKU 主键是整数。
            # 转成 int 后，后续才能用它查询 ProductSku.id。
            sku_id = int(field)
        except ValueError:
            # field 不是合法整数，说明它不是本系统认可的 SKU ID，跳过该项。
            continue

        # 将 JSON value 转换并校验为 StoredCartItem。
        item = _decode(value)
        if item is not None:
            result[sku_id] = item

    return result


def _encode(item: StoredCartItem) -> str:
    """把 Pydantic 模型序列化为可写入 Redis 的 JSON 字符串。

    ``_decode`` 与 ``_encode`` 是一对相反操作：
    JSON -> StoredCartItem，以及 StoredCartItem -> JSON。
    ``datetime`` 也会自动变成 ISO 8601 格式的字符串。
    """
    return item.model_dump_json()


def add_item(
        redis: Redis,
        key: str,
        sku_id: int,
        quantity: int,
        *,
        max_quantity: int,
        ttl: int,
) -> StoredCartItem:
    """把指定数量累加到 Redis 购物车，并返回更新后的购物车项。

    Args:
        redis: Redis 客户端。
        key: 购物车 Redis key，例如 ``mall:cart:user:1001``。
        sku_id: Redis Hash 的 field，也就是商品 SKU ID。
        quantity: 本次新增数量。
        max_quantity: 新的总数量上限，由 Service 计算后传入。
        ttl: 购物车过期秒数，成功写入后会重新计时。

    Returns:
        Redis 中最终保存的 ``StoredCartItem``。

    Raises:
        CartQuantityLimitError: 已有数量加本次数量后超过 max_quantity。
        CartConcurrentUpdateError: 连续 5 次遇到其他请求抢先修改同一购物车。

    【重点】这里必须防止“丢失更新”。假设购物车原来有 1 件，两个请求同时
    各加 1 件；若都直接读取 1 并写入 2，最终会少一件。WATCH 乐观锁会让后
    提交的请求发现数据已变化，重新读取最新数量再计算。

    【进阶】参数列表中的 ``*`` 表示后面的 max_quantity 和 ttl 必须用关键字
    传参，可以避免两个整数因位置写反而产生隐蔽错误。
    """
    # Redis Hash 的 field 统一保存为字符串，例如整数 25 变成 "25"。
    field = str(sku_id)

    # 并发冲突时最多完整重试 5 次；变量名 _ 表示循环次数本身不会被使用。
    for _ in range(5):
        # pipeline 既用于发送事务命令，也会在离开 with 时清理 WATCH 状态。
        with redis.pipeline() as pipe:
            try:
                # 【进阶：步骤 1】监视整个购物车 key。
                # 从现在开始到 execute 前，只要其他请求修改 key，事务就会失败。
                pipe.watch(key)

                # 【步骤 2】读取该 SKU 已有数据。首次加入时 current 为 None。
                current = _decode(pipe.hget(key, field))

                # 【重点】购物车中保存“最终总数量”，所以要用已有数量 + 新增数量。
                new_quantity = (current.quantity if current else 0) + quantity
                if new_quantity > max_quantity:
                    # 这是主动业务校验失败，不应该进入并发重试。
                    raise CartQuantityLimitError(max_quantity)

                # 构造即将写回 Redis 的完整数据。
                item = StoredCartItem(
                    quantity=new_quantity,
                    # 已存在时保留用户之前的勾选状态；首次加入默认勾选。
                    selected=current.selected if current else True,
                    # 已存在时保留首次加入时间；首次加入才记录当前时间。
                    added_at=current.added_at if current else datetime.now(),
                )

                # 【进阶：步骤 3】MULTI 标记事务开始；后续命令先进入队列。
                pipe.multi()
                # HSET 只覆盖当前 SKU field，不会清空购物车中其他 SKU。
                pipe.hset(key, field, _encode(item))
                # 每次成功加入都延长整个购物车的有效期。
                pipe.expire(key, ttl)
                # 【进阶：步骤 4】EXEC 原子提交 HSET + EXPIRE。
                # 若 WATCH 的 key 被别人改过，这里抛出 WatchError，什么也不写。
                pipe.execute()
                return item
            except WatchError:
                # 其他请求抢先修改了购物车：回到循环开头，重新读、重新算、再提交。
                continue

    # 5 次都发生并发冲突时停止重试，让上层返回 HTTP 409，客户端可稍后重试。
    raise CartConcurrentUpdateError


def update_item(
        redis: Redis,
        key: str,
        sku_id: int,
        *,
        quantity: int | None,
        selected: bool | None,
        ttl: int
) -> StoredCartItem | None:
    field = str(sku_id)
    for _ in range(5):
        with redis.pipeline() as pipe:
            try:
                pipe.watch(key)
                current = _decode(pipe.hget(key, field))
                if current is None:
                    return None;
                item = current.model_copy(
                    update={
                        "quantity": quantity if quantity is not None else current.quantity,
                        "selected": selected if selected is not None else current.selected,
                    }
                )
                pipe.multi()
                pipe.hset(key, field, _encode(item))
                pipe.expire(key, ttl)
                pipe.execute()
                return item
            except WatchError:
                continue
    raise CartConcurrentUpdateError


def remove_item(redis: Redis, key: str, sku_id: int) -> bool:
    return bool(redis.hdel(key, str(sku_id)))


def update_selection(
        redis: Redis,
        key: str,
        *,
        selected: bool,
        sku_ids: [list[int]] | None,
        ttl: int
) -> None:
    target = {str(item) for item in sku_ids} if sku_ids is not None else None
    for _ in range(5):
        with redis.pipeline() as pipe:
            try:
                pipe.watch(key)
                raw = pipe.hgetall(key)
                mapping: dict[str, int] = {}
                for field, value in raw.items():
                    if target is None or str(field) in target:
                        item = _decode(value)
                        if item:
                            mapping[str(field)] = _encode(item.model_copy(update={"selected": selected}))
                pipe.multi()
                if mapping:
                    pipe.hset(key, mapping=mapping)
                    pipe.expire(key, ttl)
                pipe.execute()
                return
            except WatchError:
                continue
    raise CartConcurrentUpdateError


def clear_cart(redis: Redis, key: str) -> None:
    redis.delete(key)


def merge_carts(
        redis: Redis,
        guest_key: str,
        user_key: str,
        *,
        max_quantity: int ,
        ttl: int
) -> None:
    if guest_key == user_key:
        return
    for _ in range(5):
        with redis.pipeline() as pipe:
            try:
                pipe.watch(guest_key,user_key)
                guest = read_cart(pipe, guest_key)
                user = read_cart(pipe, user_key)
                merged = dict(user)
                for sku_id,guest_item in guest.items():
                    current = merged.get(int(sku_id))
                    merged[sku_id] = guest_item.model_copy(
                        update={
                            "quantity": min(
                                (current.quantity if current else  0 )+ guest_item.quantity,
                                max_quantity,
                            ),
                            "selected": (current.selected if current else False) or guest_item.selected,
                            'added_at':  min(current.added_at, guest_item.added_at) if current else guest_item.added_at,
                        }
                    )
                mapping = {
                    str(sku_id): _encode(item) for sku_id, item in merged.items()
                }
                pipe.multi()
                if mapping:
                    pipe.hset(user_key, mapping=mapping)
                    pipe.expire(user_key, ttl)
                pipe.execute()
                return
            except WatchError:
                continue
    raise CartConcurrentUpdateError



def remove_items(redis: Redis, key: str, sku_ids: list[str]) -> int:
    if not sku_ids:
        return 0
    return str(redis.hdel(key, *(str(sku_id) for sku_id in sku_ids)))
