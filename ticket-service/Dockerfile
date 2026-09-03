# ============================================================
# ticket-service 镜像 —— 多阶段构建（论文第5章"容器化"）
# 目标：最终镜像 <200MB；非 root 运行（容器安全基线）
# 体积策略（V2，实测 slim 版 319MB 超标后的优化）：
#   1) 基础镜像 slim → alpine：省约 90MB（本项目依赖均有 musllinux wheel，无需编译）；
#   2) 去掉 uvicorn[standard]：省 uvloop/httptools/watchfiles 约 20MB，
#      并发能力由 K8s 副本数保证；
#   3) 裁冗余：pip/setuptools、SQLAlchemy 非 MySQL 方言。
# ============================================================

# ---------- 阶段1：builder（构建专用，产物最终丢弃） ----------
FROM python:3.11-alpine AS builder

WORKDIR /build
COPY requirements.txt .
# --prefix=/install：依赖统一安装到 /install，下一阶段整体 COPY 即可
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- 阶段2：runtime（最终镜像，只留运行所需） ----------
FROM python:3.11-alpine

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

# 仅拷贝已安装好的依赖（/install/lib/python3.11/site-packages → /usr/local 对应路径）
COPY --from=builder /install /usr/local

# 业务代码最后拷入：改动最频繁，放最后可最大化命中 Docker 层缓存
COPY app ./app

# 非 root + 冗余裁剪（alpine 用 adduser，slim 用 useradd —— 面试可讲两个发行版的差异）
RUN adduser -D -u 10001 -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
    && rm -rf /usr/local/lib/python3.11/site-packages/setuptools* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/postgresql* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/sqlite* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/oracle* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/mssql* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/firebird* \
    && rm -rf /usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/sybase*
USER appuser

EXPOSE 8002
# 单 worker：副本数交给 K8s Deployment 扩缩
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]


