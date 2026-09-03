# ticket-service 镜像（开发版：单阶段，保证 compose 本地先跑通）
# 注意：阶段2（容器化章节）将升级为"多阶段构建"，目标镜像体积 <200MB，届时直接重写本文件。
FROM python:3.11-slim

WORKDIR /app
# 关闭字节码缓存与输出缓冲，日志可实时进 stdout（后续 K8s 采集容器日志依赖这一行为）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 先 COPY 依赖清单再装依赖：利用 Docker 层缓存，requirements.txt 不变时不会重复 pip install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再 COPY 业务代码（业务代码改动最频繁，放后面可最大化命中上面那层缓存）
COPY app ./app

EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
