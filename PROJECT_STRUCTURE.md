# ticket-system 项目目录结构与生成规则（PROJECT_STRUCTURE.md）

> 本文件是项目的"目录宪法"。**任何文件生成任务开始前，必须先完整读取本文件**，
> 并严格按以下目录与命名规则放置产物。未覆盖的新文件类型一律先提议、经确认后再创建。

> 根目录说明：本文件位于 `c:\Users\avavy\Desktop\bu`，**该目录即项目根**（下文树中的 `ticket-system/`）。
> 会话中生成的所有代码 / K8s YAML / 监控配置 / CI 流水线 / 论文素材，均落在此根下的对应子目录。

## 一、整体目录树

```
ticket-system/                          # = c:\Users\avavy\Desktop\bu
├── user-service/                       # 用户微服务 (FastAPI, 端口 8001)
│   ├── app/
│   │   ├── main.py                     # 入口
│   │   ├── cache.py                    # Redis 缓存封装
│   │   └── models.py                   # 数据模型
│   ├── Dockerfile
│   └── requirements.txt
├── ticket-service/                     # 工单微服务 (FastAPI, 端口 8002)
│   └── （结构同上：app/main.py、app/cache.py、app/models.py、Dockerfile、requirements.txt）
├── k8s/                                # 所有 K8s YAML 按资源类型分子目录
│   ├── base/                           # Namespace / ConfigMap / Secret
│   ├── mysql/                          # MySQL StatefulSet + PVC
│   ├── services/                       # 两个微服务的 Deployment + Service
│   └── ingress.yaml                    # 集群入口
├── monitoring/                         # Prometheus / Alertmanager / Loki / Promtail 配置
├── .github/workflows/                  # CI/CD 流水线（GitHub Actions）
├── docs/                               # 论文素材：架构图说明、故障排查记录、压测报告
├── .clinerules/                        # 常驻规则（已有，勿改）
└── .cline/skills/                      # 阶段技能（已有，勿改）
```

## 二、硬性要求

1. **新文件必须放入上表对应目录，禁止堆在项目根目录。**
2. **K8s YAML 命名规范：`{资源类型}-{服务名}.yaml`**，例如：
   - `k8s/services/deployment-user-service.yaml`
   - `k8s/services/service-ticket-service.yaml`
   - `k8s/mysql/statefulset-mysql.yaml`
   - `k8s/base/namespace.yaml`（无服务归属的集群级资源直接用具名，如 `secret-mysql.yaml`、`configmap-app.yaml`）
3. **`docs/` 论文素材按 `{日期}-{主题}.md` 命名**（如 `20260903-压测报告.md`），用于沉淀论文素材。
4. **文件生成前必须读取本文件**，违反目录约定的产物视为无效。

## 三、目录职责与论文章节映射（所有输出须能对上章节）

| 目录 / 产物 | 论文章节 | 职责 |
|---|---|---|
| `user-service/`、`ticket-service/` | 第 4 章 | 微服务业务代码 + Redis 缓存实现 |
| `user-service/Dockerfile` 等 | 第 5 章 | 多阶段构建、镜像 <200MB |
| `k8s/` | 第 5 章 | 高可用部署清单（含 mysql/redis 编排） |
| `.github/workflows/` | 第 5 章 | CI/CD 流水线 |
| `monitoring/` | 第 6 章 | Prometheus+Grafana+Alertmanager+Loki |
| `docs/` 故障/压测记录 | 第 6、7 章 | 测试数据与总结素材 |

## 四、技术栈与端口速查（每个任务快速对齐）

| 组件 | 值 |
|---|---|
| user-service | FastAPI，端口 8001 |
| ticket-service | FastAPI，端口 8002 |
| MySQL | 8.0，StatefulSet 部署 |
| Redis | 7，作为缓存（user 登录态 / ticket 列表） |
| 编排 | K8s（minikube / k3s，论文口径"单 Master 多 Worker"） |
| CI/CD | GitHub Actions（备选 Gitee + Jenkins） |
| 监控 | Prometheus + Grafana + Alertmanager（钉钉告警） |
| 日志 | Loki + Promtail |
| 压测 | JMeter |
