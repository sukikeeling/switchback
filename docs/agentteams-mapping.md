# 到 AgentTeams（Hiclaw）的协同设计映射

> GOAI 赛道 1 硬性要求：多 Agent 协同设计必须以 **AgentTeams（原名 Hiclaw）** 为设计基点；评审重点核验**角色编排、任务拆解、上下文传递、协同执行、状态追踪**如何映射到框架能力。
> 本文档给出逐点映射（基于 hiclaw.io / alibaba/hiclaw 公开资料，标注出处）。

## 1. 框架事实（出处：hiclaw.io、github.com/alibaba/hiclaw）

| 项 | AgentTeams / Hiclaw 能力 |
|---|---|
| 定位 | 开源多 Agent 操作系统（Open Source Multi-Agent OS），加速 OPOC 与数字化劳动力落地 |
| 架构 | **Manager Agent 协调多个 Worker Agent** 在 Matrix 房间中协作，全程对人类可见、可实时干预 |
| 通信 | Matrix IM 协议（支持端到端加密与联邦部署） |
| 安全 | 凭证透传 + 消费者令牌：Worker 只携带"工牌"，不持有真实 API Key 或 GitHub PAT |
| 网关 | Higress AI Gateway：统一网关，安全访问 LLM（Qwen/Claude/OpenAI/本地模型）与外部 API / MCP Servers / Skills |
| 部署 | Docker（2 核 / 4GB+）；Web UI 登录后"Create a Worker named alice…"创建 Worker |
| 开源 | Apache-2.0，社区驱动，支持私有化部署 |

## 2. 角色编排映射

| 本项目角色 | AgentTeams 落位 | 框架能力点 |
|---|---|---|
| `M-OPER` 运营总监 | Manager Agent（Control Flow） | 智能拆解任务、协调多个 Worker 并行 |
| `W-RESEARCH / W-CREATE / W-VERIFY / W-RISK` | Worker Agent（Task Flow） | 各自专注的职能 Worker，可扩展 |
| `G-GOVERNOR` 监理 | Matrix 房间内的人类监督 + Manager 侧治理 Skill | "全程可见、可实时干预"正是折返点的人机监理落地 |
| 人工终审/公众代表 | Matrix 客户端人类 | 人类可随时进入任意房间观察、实时干预、纠正 Agent 行为 |

## 3. 闭环 8 步映射

| 步骤 | AgentTeams 能力落位 |
|---|---|
| 1 任务输入 | Manager 在 Matrix 房间接单 |
| 2 任务拆解 | Manager 拆解为子任务 DAG（按坡度分级） |
| 3 上下文传递 | Matrix 房间共享上下文 + SharedState（K 标溯源） |
| 4 工具调用 | Worker 经 Higress 网关调 MCP Servers / Skills（凭证透传） |
| 5 结果验证 | W-VERIFY 的 evidence-verify Skill 执行 |
| 6 执行证据沉淀 | G-GOVERNOR 将结果 seal 进 K 标账本 |
| 7 审批与回滚 | Matrix 房间三方复核折返点 + 道岔三态 |
| 8 经验沉淀 | lessons-learned 写回 AgentMemory（AgentTeams 生态可扩展记忆） |

## 4. 安全边界映射

- **凭证不落 Worker**：本项目 W-* 角色经 Higress 网关访问工具，与 AgentTeams"消费者令牌"机制一致——Worker 被攻破也不泄露真实凭证。
- **人机可见可干预**：折返点"到站必停"要求人类在 Matrix 房间内看到每个决策点——AgentTeams 的实时可干预性是该协议的基础设施前提。
- **审计留痕**：K 标账本 + OTel 兼容 trace 覆盖 AgentTeams 执行日志，满足"结果校验、复审、安全熔断审计"。

## 5. 诚实的边界说明

- 本仓库目前提供**协议实现与可复现 demo**；AgentTeams 集群的实际编排（Docker 部署、Matrix 房间、Higress 路由）为复赛"可执行代码包"的部署目标。
- 初赛以方案设计为主：本映射证明设计在框架能力之上成立、可迁移，且迁移成本是"配置/协议适配"而非"重新设计工具调用链"。
