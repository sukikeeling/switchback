# Switchback · 折返治理 — 设计蓝图

> GOAI 世界人工智能开源大赛（2026·杭州）｜赛道 1 新智基座 Agent Infra
> 作者：sukikeeling（AI Agent 协作参赛）｜日期：2026-08-13

## 1. 一句话定位

**折返治理（Switchback Governance）**：把京张铁路青龙桥"人字形折返"的制度智慧——列车遇陡坡必停、换向、以退为进——做成多 Agent 协同基础设施上的一层**人机监理治理协议**：任何 Agent 决策"到站必停、三方复核、不设自动恢复"。

> 口号：**让每一次 Agent 决策，都沿轨道可查、可停、可回头。**
> Every agent decision must be traceable, stoppable, and reversible on the rail.

## 2. 为什么是"治理"？——Agent 从 Demo 到 Production 的鸿沟

多 Agent 系统从 Demo 走向生产（赛道1 主题）时，真正卡住的不是"能不能跑通"，而是：

- **结果不可信**：Agent 输出幻觉、数值对不齐、引用错位，缺少可复算的证据链；
- **过程不可停**：一旦编排开始就自动往下走，错误被一路放大，没有"到站必停"的检查点；
- **出事了不可回**：没有审批、回滚、入段检修的语义，事故只能"硬杀进程"；
- **账目不可审**：谁做了什么、基于哪个数据版本、算出来的结论是什么，没有不可变账本。

京张竞赛（84 分最高纪录）的全部踩坑都发生在这四类鸿沟里：
`package_id 残留`（状态漂移）、`CRLF 哈希错位`（证据链断裂）、`中英标记漂移 42 处`（一致性失控）、`数值三处对不齐`（结果不可信）。

**折返治理 = 把"人字坡"上的铁路规则，转译为 Agent 工程的治理协议。**

## 3. 协议四大机制

| 机制 | 铁路原型 | Agent 工程转译 |
|---|---|---|
| **折返点 Switchback Node** | 列车到折返点必停 | 任务管线上的固定检查点，到达即停；三方（责任人/专业复核/公众代表）裁决：放行/折返/入段；**任何一方否决即强制折返** |
| **坡度分级准入 Grade-based Access** | 33‰ 坡度分陡缓 | 任务按风险/难度分三级（缓坡/中坡/陡坡），坡度越高准入复审越严 |
| **K标版本 K-marker Versioning** | 铁路里程 K 标 | 每次数据更新/复算/放行记入新 K 标，内容寻址哈希链，永久留痕 |
| **道岔三态 Switch States** | 正线/侧线/入段 | 任务状态机：正线运行 / 侧线折返 / 入段检修；**不设自动恢复**，从检修态回正线须重新评估 |

## 4. 多 Agent 协同设计（以 AgentTeams 为设计基点）

在 AgentTeams（Manager-Worker 双层 + Matrix 房间 + Higress 网关）之上编排 **6 个 Agent 身份**：

| ID | 角色 | 类型 | 职责 |
|---|---|---|---|
| M-OPER | 运营总监 | Manager | 任务接单、坡度分级拆解、Worker 调度、维护 Matrix 房间全局状态、触发折返点 |
| W-RESEARCH | 调研专员 | Worker | 情报采集、事实核验、来源管理、证据收集 |
| W-CREATE | 内容专员 | Worker | 结构化工件生产、双语输出、版本化文档 |
| W-VERIFY | 校验专员 | Worker | 数值三处对齐、引用双向检查、哈希逐文件核对、复算 |
| W-RISK | 风险与合规 | Worker | risk ledger、版权/权利声明、合规矩阵、K标登记 |
| G-GOVERNOR | 监理 Agent | 治理组件 | 折返点裁决、坡度准入、道岔三态、不设自动恢复；人工可随时接管 |

**闭环 8 步映射**：任务输入 → 任务拆解 → 上下文传递 → 工具调用 → 结果验证 → 执行证据沉淀 → 审批与回滚 → 经验沉淀。

## 5. 交付物

| 交付物 | 状态 |
|---|---|
| 开源仓库 `sukikeeling/switchback`（核心协议 + 可运行 demo） | 本仓 |
| 初赛方案 PDF（对照赛道 rubric 逐项） | competition/proposal.pdf |
| 500 字作品简介 | competition/intro-500.md |
| Agent Identity 清单 | docs/identity.md |
| Skill 清单 | docs/skills.md |
| 开源协议与依赖说明 | LICENSE + README |

## 6. 与赛道1 rubric 对齐

| 评审维度 | 权重 | 本方案落点 |
|---|---|---|
| 场景价值与行业可复制性 | 25% | 京张 84 分真实竞赛闭环为旗舰案例；治理协议可复制到运维/客服/研发/金融风控四方向 |
| 多 Agent 协同与自主闭环能力 | 25% | AgentTeams 上 Manager+4 Worker+Governor，闭环 8 步全覆盖 |
| Skill 工程体系与生态复用 | 25% | 6 个核心 Skill：evidence-verify / kmarker-ledger / grade-access / risk-ledger / switch-decision / lessons-learned |
| 工程落地、运行验证与安全可审计 | 20% | 可运行代码包 + pytest + K标不可变账本 + 审计日志 + risk/rights ledger |
| 开放/开源贡献 | 5% | Apache-2.0 全量开源；京张开源参赛包作开源凭证 |
