# 任务：GitHub Actions 自动化流水线（论文第5章第二节）

设计一条完整流水线，push 到 main 分支时自动触发：

## 阶段设计
1. lint：对两个服务分别跑 ruff/flake8
2. build：Docker 构建，tag 规则为 {服务名}:{git短sha}，同时打 latest
3. push：推送到镜像仓库（默认阿里云容器镜像服务 ACR，因为 GitHub Packages 国内拉取慢；请同时给出 Docker Hub 的写法备选）
4. deploy：用 SSH action 登录我的云服务器，kubectl set image 滚动更新
   - 部署后自动跑 kubectl rollout status 验证，失败则输出回滚命令

## 交付物
1. .github/workflows/deploy.yml 完整内容，所有敏感信息用 GitHub Secrets 占位符（ACR_REGISTRY、ACR_USERNAME、ACR_PASSWORD、SSH_HOST 等），并列表告诉我需要配哪几个 Secret
2. 一张流水线阶段的 ASCII 流程图（我要照着画进论文）
3. 解释"滚动更新 vs 重建部署 vs 蓝绿部署"，说明 K8s 默认策略为什么是滚动更新——这段进论文
4. 【面试预警】：镜像 tag 为什么不用 latest？流水线某一环失败怎么定位？
