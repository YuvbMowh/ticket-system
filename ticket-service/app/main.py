# -*- coding: utf-8 -*-
"""
ticket-service 主入口（FastAPI，端口 8002）
架构作用：工单业务微服务。提供 创建/分页查询/状态流转 三个接口，
认证通过"调用 user-service /user/me"委托完成，演示微服务间典型的"认证委托 + 内部 API"通信。

【面试预警：微服务间 token 传递的 3 种方案】
1. Header 透传（本项目采用）：调用方原样转发 Authorization，被调方再验签/再校验；
   优点：实现简单、服务边界清晰；缺点：每跳多一次网络调用。
2. 共享 JWT 密钥本地验签：ticket-service 直接验签、不回调，省一次调用；
   缺点：密钥管控半径变大，令牌吊销仍需协商（通常再引入 Redis 黑名单）。
3. API 网关统一鉴权：Token 只在网关验一次，集群内部信任网络；
   缺点：网关是唯一信任点，需配套网络策略（如 NetworkPolicy）。
本项目选方案 1：两个服务交互直观、答辩易讲清"服务间调用如何传身份"。
"""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import cache, models

# ---------- 配置 ----------
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001")  # 认证服务地址
AUTH_TIMEOUT = float(os.getenv("AUTH_TIMEOUT", "3.0"))                     # 认证调用超时(秒)


# ---------- 请求体模型（Pydantic 校验，不合法自动 422） ----------
class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    priority: str = "normal"


class StatusUpdate(BaseModel):
    status: str


# ---------- 生命周期：启动时幂等建库建表 ----------
@asynccontextmanager
async def lifespan(_: FastAPI):
    models.init_db()
    yield


app = FastAPI(title="ticket-service", version="0.1.0", lifespan=lifespan)


# ---------- 认证委托：调用 user-service /user/me ----------
def _call_auth(authorization: str) -> dict:
    """架构作用：把 token 校验外包给认证服务，工单服务自身不保存也不验证 JWT。"""
    try:
        with httpx.Client(timeout=AUTH_TIMEOUT) as client:
            resp = client.get(f"{USER_SERVICE_URL}/user/me", headers={"Authorization": authorization})
    except httpx.HTTPError:
        # 下游故障语义化：503(服务不可用) 与自身 Bug 的 500 区分开，监控告警语义更清晰
        raise HTTPException(status_code=503, detail="认证服务暂不可用，请稍后重试")
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail=resp.json().get("detail", "登录已失效"))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="认证服务响应异常")
    return resp.json()  # {id, username, created_at}


def require_login(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI 依赖：需登录的接口声明 current_user: dict = Depends(require_login) 即可。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少登录凭证")
    return _call_auth(authorization)


# ---------- 业务路由（三个，绝不加多余业务） ----------
@app.post("/tickets", status_code=201)
def create_ticket(body: TicketCreate, current_user: dict = Depends(require_login)):
    """创建工单：新单状态恒为 pending，操作人取自认证服务返回值。"""
    if body.priority not in models.PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority 必须为 {models.PRIORITIES} 之一")
    session = models.get_session()
    try:
        ticket = models.Ticket(
            title=body.title.strip(),
            content=body.content.strip(),
            priority=body.priority,
            created_by=current_user["username"],  # 信任上游身份标识，本服务不重复校验
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        # Cache Aside 写路径：先写库、后删缓存（删而非更新，避免并发写把缓存改成旧值）
        cache.delete_by_pattern("tickets:list:*")
        return ticket.to_dict()
    finally:
        session.close()


@app.get("/tickets")
def list_tickets(page: int = 1, size: int = 10, current_user: dict = Depends(require_login)):
    """分页查询工单：命中 Redis 缓存直接返回；60 秒过期后回源 MySQL（第4章缓存核心场景）。"""
    if page < 1 or size < 1 or size > 100:
        raise HTTPException(status_code=400, detail="page>=1 且 1<=size<=100")
    cache_key = f"tickets:list:{page}:{size}"   # key 设计：tickets:list:{page}:{size}
    cached = cache.get_json(cache_key)          # Redis 故障时内部返回 None → 自动走数据库
    if cached is not None:
        return cached
    session = models.get_session()
    try:
        total = session.query(models.Ticket).count()
        rows = (
            session.query(models.Ticket)
            .order_by(models.Ticket.id.desc())   # 新单在前
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        data = {"total": total, "page": page, "size": size, "items": [t.to_dict() for t in rows]}
        cache.set_json(cache_key, data, cache.CACHE_TTL_TICKETS)  # 回填缓存 60 秒
        return data
    finally:
        session.close()


@app.put("/tickets/{ticket_id}/status")
def update_status(ticket_id: int, body: StatusUpdate,
                  current_user: dict = Depends(require_login)):
    """工单状态流转：严格按 待处理→处理中→已完成 单向前进（状态机防跳级/回退）。"""
    target = body.status
    session = models.get_session()
    try:
        ticket = session.get(models.Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        ok, msg = models.can_transition(ticket.status, target)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        ticket.status = target                    # updated_at 由 ORM onupdate 自动刷新
        session.commit()
        session.refresh(ticket)
        cache.delete_by_pattern("tickets:list:*") # 状态是列表展示字段，写后必须失效缓存
        return ticket.to_dict()
    finally:
        session.close()

