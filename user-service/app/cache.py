# -*- coding: utf-8 -*-
"""
user-service Redis 缓存封装层（论文第4章"缓存设计"，服务内部模块图里的 cache 子模块）

是什么：对 redis-py 官方客户端的一层薄封装，只暴露本项目需要的读/写两个方法。
为什么需要：把 Redis 连接参数、序列化、异常降级集中到一处，接口层不感知 Redis 细节；
           论文画"服务内部模块图"时，缓存层就是一块边界清晰可独立画的组件。
在本项目怎么用：user-service 缓存用户信息，key = user:{id}，TTL 1 小时。

【面试预警：Redis 挂了怎么办】
本模块所有方法都捕获 redis.RedisError 并"静默降级"：
- 读缓存失败 → 返回 None，业务层自动回源 MySQL（缓存只是加速，正确性由数据库兜底）；
- 写缓存失败 → 忽略并记 warning 日志，主流程不中断（最多损失一次缓存预热）。
即：Redis 在本架构中永远是"旁路"，任何缓存故障都不允许把接口拖成 500。
"""
import json
import logging
import os

import redis

logger = logging.getLogger("user-service.cache")

# 连接参数仍走环境变量：docker-compose 与 K8s 下只需改注入值，代码零改动
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
CACHE_TTL_USER = int(os.getenv("CACHE_TTL_USER", "3600"))  # 用户信息缓存 1 小时

_client = None


def _get_client() -> redis.Redis:
    """惰性创建单例客户端；连接池由 redis-py 内部维护，避免每个请求新建 TCP 连接。"""
    global _client
    if _client is None:
        # decode_responses=True：读出来直接是 str；socket 超时 2s：Redis 故障时不拖垮请求线程
        _client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
            health_check_interval=30,
        )
    return _client


def get_json(key: str):
    """读缓存并反序列化为 Python 对象；任何 Redis 异常都返回 None（降级直连数据库）。"""
    try:
        raw = _get_client().get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError:
        logger.warning("Redis 读取失败 key=%s，降级直连 MySQL", key)
        return None


def set_json(key: str, value, ttl: int) -> None:
    """把 Python 对象序列化写入缓存；失败只记日志，不影响主流程（Cache Aside 写路径的旁路语义）。"""
    try:
        _get_client().set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except redis.RedisError:
        logger.warning("Redis 写入失败 key=%s，本次跳过缓存", key)
