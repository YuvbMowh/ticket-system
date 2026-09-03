# -*- coding: utf-8 -*-
"""
user-service 主入口（FastAPI，端口 8001）
架构作用：认证微服务。对外提供 注册/登录/当前用户 三个极简接口，
用 JWT 无状态令牌表达登录态，使 ticket-service 无需共享会话即可校验用户。

JWT 概念三段式：
- 是什么：服务端签名后交给客户端保存的自包含令牌，服务端不维护会话状态；
- 为什么需要：微服务场景"会话复制"代价高，无状态令牌让任意服务副本都能独立验签（利于水平扩展）；
- 在本项目怎么用：/login 签发 HS256 令牌（2 小时过期），ticket-service 收到请求后携带令牌
  调用本服务 /user/me 完成校验（即"认证委托"，详见 ticket-service）。
【面试预警】JWT 无状态 ⇒ 无法主动吊销，这是它与 Session 方案的核心取舍（答辩高频题）。
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from prometheus_fastapi_instrumentator import Instrumentator  # 自动指标暴露（论文第6章）

from . import cache, models

# ---------- 认证参数（环境变量注入：docker-compose / K8s 各自配置） ----------
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")    # 生产环境必须由 K8s Secret 注入
JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "7200"))  # access_token 2 小时


# ---------- 请求体模型（Pydantic 校验，不合法自动返回 422） ----------
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=72)  # bcrypt 输入上限 72 字节


class LoginIn(BaseModel):
    username: str
    password: str


# ---------- 生命周期：启动时幂等建库建表，保证 docker compose up 即可直接调接口 ----------
@asynccontextmanager
async def lifespan(_: FastAPI):
    models.init_db()
    yield


app = FastAPI(title="user-service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """
    健康检查端点（K8s livenessProbe / readinessProbe 共用）。
    架构作用：K8s 判断 Pod 是否存活/就绪的唯一依据（对应第5章探针配置）。

    设计说明：这里只做进程级存活检查（返回 200 即代表 uvicorn 可正常服务）。
    为什么不把 MySQL/Redis 连通性检查放进 /healthz：
    - liveness 探针语义是"进程是否卡死/需重启"，必须宽松，否则 DB 抖动会导致 Pod 被无限重启；
    - 依赖检查应放在 readiness（生产上通常拆一个 /readyz），DB 故障时只摘流量、不杀 Pod。
    【面试预警】liveness 要"宽松保命"，readiness 才适合"检查依赖决定是否引流"。
    """
    return {"status": "ok"}



# ---------- 认证工具函数 ----------
def _hash_password(raw: str) -> str:
    """bcrypt 加盐哈希：bcrypt 自动生成随机盐，同密码不同用户密文也不同。"""
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(user) -> str:
    """签发 JWT：payload 只放用户标识，绝不放密码等敏感信息。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),          # JWT 标准声明 sub=用户主键，下游据此识别身份
        "username": user.username,    # 冗余用户名：ticket-service 记"操作人"时免再查库
        "iat": now,
        "exp": now + timedelta(seconds=TOKEN_TTL_SECONDS),  # 过期时间受签名保护，客户端无法篡改
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def _parse_token(authorization: str | None) -> dict:
    """解析 Authorization 头并验签，失败统一抛 401。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer Token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token 无效")


# ---------- 业务接口（三个，绝不加多余业务） ----------
@app.post("/register", status_code=201)
def register(body: RegisterIn):
    """注册：用户名唯一 + bcrypt 存密文。"""
    username = body.username.strip()
    session = models.get_session()
    try:
        if session.query(models.User).filter_by(username=username).first():
            raise HTTPException(status_code=409, detail="用户名已存在")
        user = models.User(username=username, password_hash=_hash_password(body.password))
        session.add(user)
        session.commit()
        session.refresh(user)
        # 注册即预热用户缓存（本项目无修改用户资料接口 ⇒ 缓存不会变脏，TTL 仅兜底）
        cache.set_json(f"user:{user.id}", user.to_dict(), cache.CACHE_TTL_USER)
        return user.to_dict()
    finally:
        session.close()


@app.post("/login")
def login(body: LoginIn):
    """登录：校验密码成功即签发 JWT。"""
    session = models.get_session()
    try:
        user = session.query(models.User).filter_by(username=body.username.strip()).first()
        # 统一 401，不区分"用户不存在/密码错"，避免泄露账号是否存在（安全细节，答辩可提）
        if not user or not _verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {
            "access_token": _create_token(user),
            "token_type": "bearer",
            "expires_in": TOKEN_TTL_SECONDS,
        }
    finally:
        session.close()


@app.get("/user/me")
def me(authorization: str | None = Header(default=None)):
    """当前用户：先读 Redis 缓存，未命中再查 MySQL（Cache Aside 读路径）。"""
    payload = _parse_token(authorization)
    user_id = int(payload["sub"])

    # 1) 读缓存：命中直接返回，数据库零压力（本服务 Redis 价值的体现点）
    cached = cache.get_json(f"user:{user_id}")
    if cached is not None:
        return cached

    # 2) 未命中（或 Redis 故障已降级）→ 回源 MySQL
    session = models.get_session()
    try:
        user = session.get(models.User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在或已被删除")
        data = user.to_dict()
        cache.set_json(f"user:{user_id}", data, cache.CACHE_TTL_USER)  # 回填缓存供后续请求命中
        return data
    finally:
        session.close()


# ==================== Prometheus 指标暴露（论文第6章监控接入） ====================
# 是什么：prometheus-fastapi-instrumentator 自动为 FastAPI 生成指标并在 /metrics 暴露。
# 为什么：Prometheus 是"拉取(pull)模式"——按 job 定时抓取 /metrics 文本，应用只需被动暴露；
#         默认指标含 http_requests_total(method/status) 与 http_request_duration_seconds(直方图)，
#         prometheus-client 还自动附带 process_* 进程指标(CPU/内存)，足以支撑 QPS/P95/CPU/内存 面板。
# 怎么用：monitoring/servicemonitor-user-service.yaml 让 Prometheus 发现本服务并抓取。
# 安全说明：/metrics 不暴露敏感业务数据；生产建议用 NetworkPolicy 限制仅 Prometheus 可达。
Instrumentator(
    should_group_status_codes=False,   # 保留原始状态码(200/500...)，供 5xx 错误率告警按 "5.." 统计
    should_ignore_untemplated=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

