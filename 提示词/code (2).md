# 任务：容器化 + 完整 K8s 部署清单（论文第5章核心）

## 第一步：Dockerfile
为两个微服务分别写 Dockerfile，要求：
- python:3.11-slim 多阶段构建，最终镜像 <200MB
- 非 root 用户运行
- 健康检查接口 /healthz（先帮我在代码里补上这个接口）

## 第二步：K8s YAML（逐个文件输出，不要省略）
为以下资源编写完整 YAML，命名空间统一 ticket-system：
1. Namespace
2. ConfigMap：两个服务的非敏感配置
3. Secret：MySQL 密码、JWT 密钥（用 stringData 示例）
4. MySQL StatefulSet + Headless Service + PVC（storageClassName 按 minikube 的 standard 调整）
5. Redis Deployment + Service
6. user-service / ticket-service 各一套：Deployment（2副本）+ Service
   - 配置 requests/limits（CPU 100m/500m，内存 128Mi/512Mi）
   - livenessProbe 和 readinessProbe 都指向 /healthz
7. Ingress：/api/user → user-service，/api/ticket → ticket-service

## 第三步：解释（对应论文写法）
1. 用一段话解释"为什么 MySQL 用 StatefulSet 而其他用 Deployment"——这段我直接进论文
2. 给出 Pod 创建失败时的排查命令速查表（kubectl describe/logs/events），我要在论文附录放"常见故障排查手册"
3. 【面试预警】：liveness 和 readiness 探针的区别、PVC 和 PV 的绑定过程
