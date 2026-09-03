# 任务：Prometheus + Grafana + Alertmanager + Loki 监控告警体系

## 部署方案
1. 用 kube-prometheus-stack（给出 helm 安装命令，或手动 YAML 两种方式都给）
2. 业务服务的 /metrics 接入：用 prometheus-fastapi-instrumentator 给两个服务加指标暴露，改造代码并给出新增的 ServiceMonitor 或 Prometheus 配置
3. Loki + Promtail 采集 Pod 日志，Grafana 接入 Loki 数据源

## 告警规则（Alertmanager → 钉钉机器人）
写 3 条 PrometheusRule：
1. Pod 重启次数 5 分钟内 >3 次
2. 服务 5xx 错误率 >5% 持续 2 分钟
3. 节点内存使用率 >85% 持续 5 分钟
钉钉告警消息模板里带上：告警名称、当前值、Pod/节点、处理建议链接

## Grafana 看板
列出我需要导入的 3 个官方看板 ID（Node Exporter、K8s 集群、FastAPI），以及每个看板里我要截图放进论文的 4 个核心面板（QPS、P95延迟、CPU、内存）

## 交付物
1. 所有 YAML 完整内容
2. "从告警触发到钉钉收到消息"的完整链路文字描述——我要写进论文的告警流程章节
3. 【面试预警】：Prometheus 拉取（pull）和推送（push）模式的区别；Grafana 上 CPU 图突然飙升，你的排查步骤是什么？
