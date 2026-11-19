from __future__ import annotations

import builtins
import json
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("eoms.cache")


class LockBusyError(Exception):
    """分布式锁已被占用。"""


class MemoryBackend:
    """开发/测试降级实现：带 TTL 的有界字典，避免内存无限增长。"""

    _MAX_KEYS = 20000
    _SWEEP_EVERY = 256

    def __init__(self) -> None:
        self._data: OrderedDict[str, tuple[float | None, str]] = OrderedDict()
        self._lock = threading.RLock()
        self._ops = 0

    def _purge(self, force: bool = False) -> None:
        self._ops += 1
        if not force and self._ops % self._SWEEP_EVERY != 0:
            return
        now = time.time()
        expired = [key for key, (expire_at, _) in self._data.items() if expire_at is not None and expire_at <= now]
        for key in expired:
            self._data.pop(key, None)
        while len(self._data) > self._MAX_KEYS:
            self._data.popitem(last=False)

    def get(self, key: str) -> str | None:
        with self._lock:
            self._purge()
            item = self._data.get(key)
            if not item:
                return None
            expire_at, value = item
            if expire_at is not None and expire_at <= time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        with self._lock:
            self._purge()
            expire_at = time.time() + ttl if ttl else None
            self._data[key] = (expire_at, value)
            self._data.move_to_end(key)

    def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        with self._lock:
            if self.get(key) is not None:
                return False
            self.set(key, value, ttl)
            return True

    def delete(self, *keys: str) -> int:
        with self._lock:
            count = 0
            for key in keys:
                if self._data.pop(key, None) is not None:
                    count += 1
            return count

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._data if key.startswith(prefix)]
            for key in keys:
                self._data.pop(key, None)
            return len(keys)

    def incr(self, key: str, ttl: int | None = None) -> int:
        with self._lock:
            current = int(self.get(key) or 0) + 1
            remaining = None
            item = self._data.get(key)
            if item and item[0]:
                remaining = max(int(item[0] - time.time()), 1)
            self.set(key, str(current), remaining or ttl)
            return current

    def sadd(self, key: str, *values: str) -> int:
        with self._lock:
            current = set(json.loads(self.get(key) or "[]"))
            before = len(current)
            current.update(values)
            if current != set() and current != set(json.loads(self.get(key) or "[]")):
                self.set(key, json.dumps(sorted(current)), 7 * 86400)
            return len(current) - before

    def srem(self, key: str, *values: str) -> int:
        with self._lock:
            current = set(json.loads(self.get(key) or "[]"))
            before = len(current)
            current.difference_update(values)
            self.set(key, json.dumps(sorted(current)), 7 * 86400)
            return before - len(current)

    def smembers(self, key: str) -> builtins.set[str]:
        return set(json.loads(self.get(key) or "[]"))


class RedisBackend:
    def __init__(self, url: str, timeout: float) -> None:
        import redis

        self._client = redis.Redis.from_url(
            url,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            health_check_interval=30,
            decode_responses=True,
            retry_on_timeout=False,
        )
        self._client.ping()

    @property
    def client(self):
        return self._client

    def get(self, key: str) -> str | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._client.set(key, value, ex=ttl)

    def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        return bool(self._client.set(key, value, nx=True, ex=ttl))

    def delete(self, *keys: str) -> int:
        return int(self._client.delete(*keys))

    def delete_prefix(self, prefix: str) -> int:
        count = 0
        batch: list[str] = []
        for key in self._client.scan_iter(match=f"{prefix}*", count=500):
            batch.append(key)
            if len(batch) >= 500:
                count += int(self._client.delete(*batch))
                batch.clear()
        if batch:
            count += int(self._client.delete(*batch))
        return count

    def incr(self, key: str, ttl: int | None = None) -> int:
        value = int(self._client.incr(key))
        if value == 1 and ttl:
            self._client.expire(key, ttl)
        return value

    def sadd(self, key: str, *values: str) -> int:
        added = int(self._client.sadd(key, *values))
        self._client.expire(key, 7 * 86400)
        return added

    def srem(self, key: str, *values: str) -> int:
        return int(self._client.srem(key, *values))

    def smembers(self, key: str) -> builtins.set[str]:
        return {
            item if isinstance(item, str) else item.decode("utf-8", "ignore")
            for item in self._client.smembers(key)
        }


_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = capacity end
if ts == nil then ts = now end
local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + delta * rate)
local allowed = 0
if tokens >= 1 then
  allowed = 1
  tokens = tokens - 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / rate) + 60)
return {allowed, math.floor(tokens)}
"""


class Cache:
    def __init__(self) -> None:
        self._backend: MemoryBackend | RedisBackend
        self._mode = "memory"
        if settings.redis_enabled:
            try:
                self._backend = RedisBackend(settings.redis_url, settings.redis_timeout)
                self._mode = "redis"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 不可用，降级为进程内缓存（仅建议开发环境）: %s", exc)
                self._backend = MemoryBackend()
        else:
            self._backend = MemoryBackend()
        self._mem_lock = threading.Lock()
        logger.info("缓存模式: %s", self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_redis(self) -> bool:
        return self._mode == "redis"

    # ---------------- 基础 ----------------
    def get(self, key: str) -> str | None:
        try:
            return self._backend.get(self._key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存读取失败 %s: %s", key, exc)
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        try:
            self._backend.set(self._key(key), value, ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存写入失败 %s: %s", key, exc)

    def get_json(self, key: str) -> Any:
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.set(key, json.dumps(value, ensure_ascii=False, default=str), ttl)

    def delete(self, *keys: str) -> int:
        try:
            return self._backend.delete(*[self._key(key) for key in keys])
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存删除失败: %s", exc)
            return 0

    def delete_prefix(self, prefix: str) -> int:
        try:
            return self._backend.delete_prefix(self._key(prefix))
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存前缀删除失败: %s", exc)
            return 0

    def incr(self, key: str, ttl: int | None = None) -> int:
        try:
            return self._backend.incr(self._key(key), ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存自增失败: %s", exc)
            return 0

    def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        try:
            return self._backend.set_nx(self._key(key), value, ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存 NX 失败: %s", exc)
            return False

    def sadd(self, key: str, *values: str) -> int:
        try:
            return self._backend.sadd(self._key(key), *values)
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存集合写入失败: %s", exc)
            return 0

    def srem(self, key: str, *values: str) -> int:
        try:
            return self._backend.srem(self._key(key), *values)
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存集合删除失败: %s", exc)
            return 0

    def smembers(self, key: str) -> builtins.set[str]:
        try:
            return self._backend.smembers(self._key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("缓存集合读取失败: %s", exc)
            return set()

    def _key(self, key: str) -> str:
        return f"eoms:{key}"

    # ---------------- 令牌桶限流 ----------------
    def allow(self, bucket: str, limit_per_minute: int, cost: int = 1) -> tuple[bool, int]:
        capacity = max(limit_per_minute, 1)
        rate = capacity / 60.0
        now = time.time()
        key = self._key(f"bucket:{bucket}")
        if isinstance(self._backend, RedisBackend):
            try:
                allowed, remaining = self._backend.client.eval(
                    _TOKEN_BUCKET_LUA, 1, key, rate, capacity, now
                )
                return bool(int(allowed)), int(remaining)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 限流失败，降级内存限流: %s", exc)
        with self._mem_lock:
            data = self._backend.get(key) if isinstance(self._backend, MemoryBackend) else None
            tokens, last = (capacity, now) if not data else (float(data.split(":")[0]), float(data.split(":")[1]))
            tokens = min(capacity, tokens + max(0.0, now - last) * rate)
            allowed = tokens >= cost
            if allowed:
                tokens -= cost
            self._backend.set(key, f"{tokens}:{now}", int(capacity / rate) + 60)
            return allowed, int(tokens)

    # ---------------- 分布式锁 ----------------
    @contextmanager
    def lock(self, name: str, ttl: int | None = None) -> Iterator[None]:
        ttl = ttl or settings.workflow_lock_seconds
        token = uuid.uuid4().hex
        key = self._key(f"lock:{name}")
        acquired = self.set_nx(f"lock:{name}", token, ttl)
        if not acquired:
            raise LockBusyError(f"操作正在处理中：{name}")
        try:
            yield
        finally:
            if isinstance(self._backend, RedisBackend):
                try:
                    self._backend.client.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        key,
                        token,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("释放分布式锁失败 %s: %s", name, exc)
            else:
                if self._backend.get(key) == token:
                    self._backend.delete(key)

    # ---------------- 健康检查 ----------------
    def health(self) -> dict[str, Any]:
        if isinstance(self._backend, RedisBackend):
            try:
                self._backend.client.ping()
                return {"backend": "redis", "ok": True}
            except Exception as exc:  # noqa: BLE001
                return {"backend": "redis", "ok": False, "error": str(exc)}
        return {"backend": "memory", "ok": True}


cache = Cache()
