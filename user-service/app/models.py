# -*- coding: utf-8 -*-
"""
user-service 数据模型层（对应论文第4章"用户服务数据库设计"）
职责：users 表结构 + MySQL 连接的唯一出处，main.py 不直接接触连接串。
"""
import os
from datetime import datetime

import pymysql
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------- 连接参数全部来自环境变量 ----------
# 这样同一个镜像在 docker-compose（host=mysql）与 K8s（host=mysql 服务名）下可复用，只换配置不换代码
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root123456")
DB_NAME = os.getenv("DB_NAME", "user_db")  # user-service 独占 user_db，与 ticket-service 逻辑隔离

# SQLAlchemy 2.0 声明式基类：所有 ORM 模型的父类
Base = declarative_base()


class User(Base):
    """用户表：只存登录/身份所需字段，字段刻意精简（业务极简原则）。"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)  # 唯一约束兜底并发注册
    password_hash = Column(String(100), nullable=False)  # bcrypt 密文（$2b$12$...，60 字符），绝不存明文
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        """ORM → dict：接口响应与 Redis 缓存共用此序列化，保证格式一致。"""
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


# 惰性单例：连接池只创建一次，避免每次请求重建（高并发下会打爆 MySQL 连接数）
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        # pool_pre_ping=True：取连接前先 ping，MySQL 重启/断连后不会把"死连接"发给业务
        #（这是面试常问的"MySQL 连接池关键参数"之一，也是故障演练剧本3的伏笔）
        _engine = create_engine(
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
            pool_pre_ping=True, pool_recycle=3600, pool_size=5, max_overflow=10,
        )
    return _engine


def get_session():
    """请求级会话工厂：main.py 中 finally 负责 close，避免连接泄漏。"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()


def init_db() -> None:
    """启动时幂等初始化：建库 + 建表。"""
    # SQLAlchemy 的 create_all 只能建"表"不能建"库"，所以先用裸连接确保 user_db 存在
    # 微服务"数据隔离"：user_db 只属于 user-service；演示环境与 ticket_db 共享同一 MySQL 实例
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4")
        conn.commit()
    finally:
        conn.close()
    Base.metadata.create_all(_get_engine())  # IF NOT EXISTS 语义，重复启动安全
