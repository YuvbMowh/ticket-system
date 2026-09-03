# 监控体系部署总说明（论文第6章）

> 归档：2026-09-03 | 前置：已完成阶段2（k8s 集群与应用部署）与阶段3（CI/CD）
> 组件：Prometheus + Grafana + Alertmanager（kube-prometheus-stack）、钉钉告警桥接、
>       Loki + Promtail（loki-stack）、两个服务的 /metrics

## 一、部署方案 A：Helm（推荐，论文按此执行）

```bash
# 1. 创建监控命名空间
kubectl create ns monitoring

# 2. 安装 kube-prometheus-stack（自带 Prometheus/Grafana/Alertmanager/kube-state-metrics/node-exporter）
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace

# 3. 安装 Loki + Promtail（日志；--set grafana.enabled=false 复用 kube-prometheus-stack 的 grafana）
helm repo add grafana https://grafana.github.io/helm-charts
helm upgrade --install loki grafana/loki-stack -n monitoring \
  --set loki.persistence.enabled=false --set grafana.enabled=false
```

等待所有 Pod Running 后，应用本目录的业务侧配置（顺序无严格依赖，operator 会 reconcile）：

```bash
kubectl apply -f monitoring/servicemonitor-user-service.yaml
kubectl apply -f monitoring/servicemonitor-ticket-service.yaml
kubectl apply -f monitoring/prometheusrule-app-alerts.yaml
kubectl apply -f monitoring/dingtalk-secret.yaml       # 先改好钉钉 token
kubectl apply -f monitoring/dingtalk-deployment.yaml
kubectl apply -f monitoring/dingtalk-service.yaml
kubectl apply -f monitoring/alertmanagerconfig-dingtalk.yaml
kubectl apply -f monitoring/grafana-loki-datasource.yaml
```

## 二、部署方案 B：手动 YAML（不装 helm 时的等价物，说明思路）

手动方式 = 把 helm 包里的清单逐个 apply，核心组件与职责对应如下：

| 组件 | 手动需要的东西 | 对应我们交付 |
|---|---|---|
| Prometheus | Deployment/StatefulSet + Prometheus 实例（CRD 或原生 config）| 需手动写 service discovery 抓取规则 |
| 业务指标发现 | ServiceMonitor 或原生 `prometheus.yml` 的 `kubernetes_sd_configs` | `servicemonitor-*.yaml` |
| 告警规则 | PrometheusRule 或原生 `rule_files` | `prometheusrule-app-alerts.yaml` |
| 告警路由 | AlertmanagerConfig 或原生 `alertmanager.yml` | `alertmanagerconfig-dingtalk.yaml` |
| 钉钉桥接 | 一个转换服务 | `dingtalk-*.yaml` |
| 集群指标 | kube-state-metrics + node-exporter | helm 包内置 |
| Grafana | Deployment + 数据源 provision | `grafana-loki-datasource.yaml` |

手动方式维护成本高（升级/告警规则管理都要手写），论文建议主线写 helm + CRD 声明式管理，手动方式作为"原理对照"一段带过。

## 三、Grafana 看板导入与论文截图面板

### 3.1 需要导入的 3 块看板

| 看板 | 来源 | 导入方式 | 论文用途 |
|---|---|---|---|
| Node Exporter Full | 官方 **ID: 1860** | Dashboards → Import → 填 1860 | 节点 CPU/内存/网络/磁盘 |
| Kubernetes 集群监控 | kube-prometheus-stack **自带**（无需导入）；Community 版 **ID: 315** | 自带：Home 里直接找 | 集群总览：Pod 数/资源请求/API Server |
| FastAPI 服务 | **无官方独立 ID** | 见下方 3.2 | 业务 QPS/P95/CPU/内存 |

### 3.2 FastAPI 服务看板

Prometheus 生态没有"FastAPI 官方看板 ID"，论文里如实写"业务指标看板基于 prometheus-fastapi-instrumentator 指标自建"。两个途径：
1. 导入 instrumentator 项目自带的 dashboard JSON（仓库 `trallnag/prometheus-fastapi-instrumentator` 的 `grafana.json`）；
2. 按下方 3.3 的 4 个查询自建面板（更贴合本系统命名空间/服务维度）。

### 3.3 论文截图用的 4 个核心面板（PromQL 可直接用）

| 面板 | PromQL（选择 Loki/Prometheus 数据源） |
|---|---|
| **QPS** | `sum(rate(http_requests_total{namespace="ticket-system"}[5m])) by (service)` |
| **P95 延迟** | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{namespace="ticket-system"}[5m])) by (le, service))` |
| **CPU** | `rate(process_cpu_seconds_total{namespace="ticket-system"}[1m])` |
| **内存** | `process_resident_memory_bytes{namespace="ticket-system"}` |

> 截图建议组合：① QPS 波浪图（压测时截，配合第6章 JMeter 章节）；② P95 阶梯下降图（演示缓存命中 vs 未命中对比）；③ CPU/内存（滚动发布前后对比）。

## 四、Loki 日志链路说明

- Promtail 以 DaemonSet 运行在每个节点，采集 `/var/log/containers/*.log`（即所有 Pod 的 stdout/stderr），打上 Pod/namespace/container 标签后推送到 Loki；
- Grafana 的 Loki 数据源已由 `grafana-loki-datasource.yaml` 自动注入；
- 排查方式：Grafana → Explore → 选 Loki → `{namespace="ticket-system"}` + `{service="ticket-service"}` 过滤，或用日志查询 `{app="ticket-service"} |= "error"`。

## 五、接入后自检清单

```bash
kubectl -n monitoring get pods                                # 全部 Running
kubectl -n monitoring get servicemonitor                      # 两个 service monitor
kubectl -n monitoring get prometheusrule                      # 规则已加载
kubectl -n monitoring get alertmanagerconfig                  # 钉钉路由已加载
# 触发验证：临时造 5xx（如停掉 user-service 再请求工单接口），
# 观察 Alertmanager → 钉钉群收到 High5xxErrorRate 告警
```

## 六、遗留事项

1. 钉钉机器人 token 需替换 `dingtalk-secret.yaml` 后再 apply；
2. 本机暂无集群，上述命令在装好 minikube/k3s 后执行；
3. 监控体系上线后，压测（阶段6）将产生真实指标与告警素材供论文使用。

## 七、2026-09-03 实际安装验证实录（kind 环境，全链路通过）

**安装结果**：kube-prometheus-stack（10 组件 Running）+ loki-stack（loki + promtail×2）均部署成功；业务 ServiceMonitor 抓取 user/ticket 各 2 个 target 全部 `up`；`http_requests_total` 可查询；三条业务规则加载，5xx 规则经"制造 503 流量"验证进入 `pending`（for 防抖生效）；Loki 可检索 `{namespace="ticket-system"}` 日志；Grafana 数据源含 Prometheus/Alertmanager/Loki。

**五个避坑点（真实踩坑记录）**：

1. **AlertmanagerConfig 的 CRD 版本是 `v1alpha1`**（新版 chart），YAML 用 `monitoring.coreos.com/v1` 会报 `no matches for kind`；本仓库 `alertmanagerconfig-dingtalk.yaml` 已改用 v1alpha1。
2. **Service 必须带 `metadata.labels`**：Prometheus 的 `__meta_kubernetes_service_label_app` 来自 Service 的 metadata.labels（非 selector）——Service 缺 labels 会导致 relabel keep 全部丢弃、target 永远为空。`k8s/services/service-*.yaml` 已补 `labels.app`。
3. **Prometheus 默认只授权 monitoring 命名空间**：跨命名空间抓取需新增 RBAC（本仓库 `monitoring/rbac-prometheus-cross-namespace.yaml`），否则 auth can-i 为 no、target 一直为空。
4. **Docker Desktop 的 DaoCloud 镜像白名单**会拒绝非白名单镜像（如 `timonwong/prometheus-webhook-dingtalk`）：本地 kind 无法拉取钉钉桥接镜像，deployment 未启用（清单保留），AlertmanagerConfig 已就绪——在可拉取镜像的集群/网络环境 apply `dingtalk-deployment.yaml` 并替换 `dingtalk-secret.yaml` 的 token 即可接通钉钉。
5. **Grafana datasource sidecar** 未自动加载我们提交的 Loki datasource ConfigMap（原因待查），本次以 Grafana API 手动创建兜底（效果一致）；ConfigMap 保留，chart 升级后可能自动生效。

**验证命令备忘**：
```bash
kubectl get servicemonitor,prometheusrule,alertmanagerconfig -n monitoring
curl -s localhost:19090/api/v1/targets | ...   # 业务 target up
curl -s localhost:19090/api/v1/rules | ...     # 三条规则加载/状态
```


