# -*- coding: utf-8 -*-
"""
ticket-service Redis 缓存封装层（论文第4章"缓存设计"核心：Cache Aside 模式的落地处）

是什么：对 redis-py 的薄封装，额外提供 delete_by_pattern 用于"写后删缓存"。
为什么需要：GET /tickets 是工单系统的最高频读接口，套一层 60 秒缓存可显著降低 MySQL 压力，
           并把"缓存层"画成论文模块图里独立的一块。
在本项目怎么用：
- 读：GET /tickets 先查 key=tickets:list:{page}:{size}，命中直接返回；
- 写：创建工单 / 改状态后 delete_by_pattern("tickets:list:*") 失效整个列表缓存族；
- 降级：与 user-service 相同，Redis 故障时读返回 None → 直连 MySQL，写忽略 → 等 TTL 自然过期。

【面试预警：为什么删缓存而不是更新缓存？】
Cache Aside 经典结论：更新缓存存在"并发写导致缓存与库不一致"的窗口，
删除缓存则下次读必回源，天然收敛；配合 TTL 兜底，即使删失败也只会短暂读到旧数据。
"""
import json
import logging
import os

import redis

logger = logging.getLogger("ticket-service.cache")

# 连接参数走环境变量：docker-compose / K8s 无缝切换
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
CACHE_TTL_TICKETS = int(os.getenv("CACHE_TTL_TICKETS", "60"))  # 工单列表缓存 60 秒

_client = None


def _get_client() -> redis.Redis:
    """惰性创建单例客户端；连接池由 redis-py 内部维护。"""
    global _client
    if _client is None:
        # socket 超时 2s：Redis 故障时不拖垮请求线程（降级策略的前提）
        _client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
            health_check_interval=30,
        )
    return _client


def get_json(key: str):
    """读缓存并反序列化；任何 Redis 异常都返回 None（业务层据此自动回源 MySQL）。"""
    try:
        raw = _get_client().get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError:
        logger.warning("Redis 读取失败 key=%s，降级直连 MySQL", key)
        return None


def set_json(key: str, value, ttl: int) -> None:
    """序列化写入缓存；失败只记日志，不影响主流程。"""
    try:
        _get_client().set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except redis.RedisError:
        logger.warning("Redis 写入失败 key=%s，本次跳过缓存", key)


def delete_by_pattern(pattern: str) -> None:
    """按前缀模式删除缓存（Cache Aside 写路径的"删缓存"步骤，作用于 tickets:list:* 族）。"""
    try:
        client = _get_client()
        # 用 scan_iter 分批迭代而非 KEYS *：避免大 key 数时阻塞单线程 Redis（运维常识）
        for key in client.scan_iter(match=pattern, count=100):
            client.delete(key)
    except redis.RedisError:
        logger.warning("Redis 清理失败 pattern=%s，旧缓存将靠 TTL 兜底过期", pattern)
