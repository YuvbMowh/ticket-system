# 基于 Kubernetes 与 CI/CD 的高可用工单交付系统

> 本科毕业设计 | 云原生架构 | FastAPI 微服务 + K8s 编排 + GitHub Actions CI/CD + Prometheus 监控

一套"薄业务、厚运维"的工单交付系统：业务仅保留登录、工单提交与单向状态流转，把设计重心放在微服务拆分、容器化、Kubernetes 编排、持续交付与可观测上，形成「代码 → 镜像 → 集群 → 交付 → 观测 → 验证」的完整云原生闭环。

## 架构总览

```
客户端 / 浏览器
   │
   ▼
Ingress (nginx) ── /api/user ──► user-service (认证, 8001, ×2)
   │                            │  JWT 签发 / bcrypt / user_db
   │
   └────────────── /api/ticket ─► ticket-service (工单, 8002, ×2)
                                 │  认证委托回调 / 状态机 / 缓存
                                 ▼
                    MySQL(StatefulSet) + Redis(Deployment)
   （外围：Prometheus 指标 · Loki/Promtail 日志 · GitHub Actions 流水线）
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python FastAPI + SQLAlchemy + PyMySQL |
| 数据库/缓存 | MySQL 8.0（StatefulSet）+ Redis 7（Cache Aside） |
| 容器 | Docker 多阶段构建（镜像 <200MB，非 root） |
| 编排 | Kubernetes（kind 单 Master 多 Worker），Deployment/StatefulSet/Service/Ingress |
| CI/CD | GitHub Actions（lint → build → push → SSH 滚动发布 + 自动回滚） |
| 监控 | Prometheus + Alertmanager（钉钉告警）+ Grafana + Loki/Promtail |
| 压测 | JMeter（梯度并发 + 缓存对比） |
| 前端 | 单文件 index.html（原生 JS，离线可用，答辩演示） |

## 目录结构

```
ticket-system/
├── user-service/          # 认证微服务（app/main.py、cache.py、models.py + static/）
├── ticket-service/        # 工单微服务（同构）
├── k8s/                   # 部署清单：base/ mysql/ redis/ services/ ingress.yaml
├── monitoring/            # Prometheus 规则/ServiceMonitor/钉钉桥接/Loki + 部署说明
├── .github/workflows/     # CI/CD 流水线（deploy.yml）
├── frontend/              # 答辩演示前端（单文件 index.html）
├── docs/                  # 论文素材（故障演练/压测/监控/k8s/CI 记录，git 忽略）
├── thesis/                # 毕业论文 + 答辩全流程（git 忽略）
├── docker-compose.yml     # 本地一键联调（MySQL+Redis+两服务）
└── PROJECT_STRUCTURE.md   # 项目目录规范（宪法）
```

## 快速开始

### 方式一：docker-compose（本地联调 / 答辩演示）

```bash
docker compose up -d --build
# 访问演示页（FastAPI 静态托管）：
open http://127.0.0.1:8001/
# 演示账号：alice / demo123456（首次需注册：见 docs）
```

### 方式二：kind 集群（论文"单 Master 多 Worker"口径）

```bash
kind create cluster --name desktop --config <2节点配置>
kubectl apply -f k8s/base -f k8s/mysql -f k8s/redis -f k8s/services -f k8s/ingress.yaml
# 监控：见 monitoring/install-monitoring.md（helm 安装 kube-prometheus-stack + loki-stack）
```

## 核心特性

- **微服务认证委托**：工单服务不持有 JWT 密钥，回调 user-service `/user/me` 校验（服务边界清晰）
- **严格单向状态机**：pending → processing → completed，跳级/回退返回 400
- **旁路缓存**：列表缓存 60s，写后删除缓存族，Redis 故障自动降级回源
- **高可用**：双副本 + liveness/readiness 探针 + StatefulSet 持久化 MySQL
- **镜像瘦身**：多阶段 + Alpine + 依赖裁剪，318MB → 190MB
- **监控告警**：三层指标 + 3 条告警规则 + 钉钉桥接 + Loki 日志
- **故障演练**：ImagePullBackOff / CrashLoopBackOff / Service 不通 三案例沉淀排查手册


## License

仅用于毕业设计学习与演示。
