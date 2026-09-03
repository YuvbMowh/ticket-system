# 任务：生成两个微服务的完整代码骨架

请生成 user-service 和 ticket-service 两个 FastAPI 微服务，要求：

## user-service（端口 8001）
- POST /register、POST /login：JWT 认证（PyJWT，access_token 2小时过期）
- GET /user/me：解析 token 返回用户信息
- 密码用 bcrypt 哈希存储

## ticket-service（端口 8002）
- POST /tickets：创建工单（标题、内容、优先级）
- GET /tickets：分页查询工单列表（这里要用 Redis 缓存，见下）
- PUT /tickets/{id}/status：工单状态流转 待处理→处理中→已完成
- 调用 user-service 的 /user/me 验证 token（模拟微服务间调用，用 httpx）

## Redis 缓存要求（论文第4章重点）
1. GET /tickets 的查询结果缓存 60 秒，key 设计为 tickets:list:{page}
2. 写操作（创建/改状态）后删除相关缓存 key（Cache Aside 模式）
3. 代码中用注释标出：如果 Redis 挂了会怎样，降级策略是什么
4. 单独用一个 cache.py 封装，方便我论文里画模块图

## 交付物清单
1. 完整目录树（tree 形式展示）
2. 所有代码文件内容（含中文注释）
3. 本地 docker-compose.yml（MySQL+Redis+两个服务，让我先本地跑通）
4. 每个接口的 curl 测试命令
5. 【面试预警】：微服务间调用token传递的3种方案对比
