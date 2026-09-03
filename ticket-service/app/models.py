# -*- coding: utf-8 -*-
"""
ticket-service 数据模型层（对应论文第4章"工单服务数据库设计"）
职责：tickets 表结构 + 工单状态机规则 + MySQL 连接封装。

设计取舍（答辩点）：user/ticket 两个库共用同一 MySQL 实例 —— "物理共享、逻辑隔离"。
演示环境资源有限不拆数据库实例，但应用层互不越权访问对方库；
生产演进为独立实例时只需改 DB_HOST（连接串外置的价值）。【面试预警】数据隔离是微服务核心原则。
"""
import os
from datetime import datetime

import pymysql
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 连接参数来自环境变量（与 user-service/models.py 完全同构，便于论文对照讲解）
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root123456")
DB_NAME = os.getenv("DB_NAME", "ticket_db")  # ticket-service 独占 ticket_db

Base = declarative_base()

# ---------- 工单状态机 ----------
# 只允许沿 待处理(pending)→处理中(processing)→已完成(completed) 单向前进
# 为什么需要：杜绝"任意改状态"，保证工单流转可审计、可回放，是"流转正确性"的答案
ALLOWED_TRANSITIONS = {
    "pending": ["processing"],    # 待处理 → 处理中
    "processing": ["completed"],  # 处理中 → 已完成
    "completed": [],              # 已完成是终态，禁止再流转
}
PRIORITIES = ("low", "normal", "high")  # 优先级取值白名单


def can_transition(current: str, target: str) -> tuple[bool, str]:
    """校验状态流转是否合法：返回 (是否合法, 错误提示)。"""
    if current == target:
        return False, "状态未发生变化"
    if target not in ALLOWED_TRANSITIONS.get(current, []):
        return False, f"非法流转：{current} 不能直接变为 {target}（必须按 待处理→处理中→已完成 单向前进）"
    return True, ""


class Ticket(Base):
    """工单表：字段贴合需求（标题/内容/优先级/状态/操作人），无多余业务字段。"""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    priority = Column(String(10), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="pending", index=True)  # 列表按状态筛选会用到索引
    created_by = Column(String(50), nullable=False)  # 操作人：来自认证服务返回的 username
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 状态流转时自动刷新

    def to_dict(self) -> dict:
        """ORM → dict：接口响应与 Redis 缓存共用此序列化，时间统一格式化为字符串。"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "priority": self.priority,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


# 惰性单例：连接池只建一次（与 user-service 同款配置）
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        # pool_pre_ping：取连接前先探测，MySQL 重启后不把死连接发给业务（故障演练伏笔）
        _engine = create_engine(
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
            pool_pre_ping=True, pool_recycle=3600, pool_size=5, max_overflow=10,
        )
    return _engine


def get_session():
    """请求级会话工厂，main.py 中 finally 负责 close。"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()


def init_db() -> None:
    """启动时幂等初始化：建库（ticket_db）+ 建表。"""
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4")
        conn.commit()
    finally:
        conn.close()
    Base.metadata.create_all(_get_engine())
