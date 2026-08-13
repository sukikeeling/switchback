# Switchback · 折返治理

> **让每一次 Agent 决策，都沿轨道可查、可停、可回头。**
> Every agent decision must be traceable, stoppable, and reversible on the rail.

**Switchback（折返治理）** 是一层**多 Agent 协同的人机监理（Human-in-the-Loop）治理协议与开源实现**。它以京张铁路青龙桥"人字形折返"展线为制度原型——列车遇陡坡必停、换向、以退为进；任何 Agent 决策同样必须"**到站必停、三方复核、不设自动恢复**"。

- **协议**：折返点 / 坡度分级准入 / K 标版本 / 道岔三态，四大机制全部以代码实现、可复算、可审计、可接手。
- **实证**：旗舰案例是 **sukikeeling 在"百年京张 AI 创新带国际城市设计开源征集"（open-city-ai/haidian）中拿到 84/100 最高纪录**的真实过程——16 个 PR、确定性 CI、官方多模态 AI 评审（CocoSgt），这不是玩具 demo，是一段真实任务闭环。
- **技术**：Python 3.10+，**零第三方依赖**，`pip install -e .` 即可跑；CLI 一键复现全流程。

```
┌────────────────────────────────────────────────────────────────────┐
│  Switchback Governance Layer（治理层）                              │
│  ┌──────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │ 折返点    │  │ 坡度分级准入 │  │ K标版本(哈希链)│  │ 道岔三态(状态机)│  │
│  │ Switchback│  │ Grade-based │  │ K-marker     │  │ Switch States │  │
│  │ Node      │  │ Access      │  │ Ledger       │  │ (no auto-resume)│ │
│  └──────────┘  └────────────┘  └─────────────┘  └──────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                       ▲ 任何一方否决即强制折返
  ┌─────────────────────┴─────────────────────┐
  │ AgentTeams 多 Agent 编排（Manager-Worker） │
  │  M-OPER 运营总监 → 拆解/调度/折返触发        │
  │  W-… Worker 协同 → 调研/内容/校验/合规      │
  │  G-GOVERNOR 监理  → 裁决/准入/状态/审计      │
  └───────────────────────────────────────────┘
```

---

## 为什么需要它 —— Agent 从 Demo 到 Production 的四道坎

多 Agent 系统跑通 demo 很容易，上生产最难的不是"能不能跑通"，而是：

| 鸿沟 | 具体症状（京张实证踩坑） | 折返治理的应答 |
|---|---|---|
| **结果不可信** | 数值三处对不齐、引用错位、幻觉 | 证据核验 Skill：数值三处对齐 + 引用双向检查 + 内容寻址哈希 |
| **过程不可停** | 编排一旦开始就自动往下走，错误被一路放大 | 折返点：到站必停，三方复核后才继续 |
| **出事了不可回** | 没有审批/回滚/隔离的语义，只能"硬杀进程" | 道岔三态：正线 / 侧线折返 / 入段检修，**不设自动恢复** |
| **账目不可审** | 谁做了什么、基于哪个数据版本、结论是什么，无账本 | K 标账本：内容寻址哈希链，不可篡改，逐条可复核 |

> 京张 84 分项目里，`package_id 残留`（状态漂移）、`CRLF 哈希错位`（证据链断裂）、`中英标记漂移 42 处`（一致性失控）全部发生在这四道坎上。折返治理 = 把"人字坡"上的铁路规则，转译成 Agent 工程的安全协议。

---

## 四大机制（协议核心）

### 1. 折返点 Switchback Node —— 到站必停
任务管线上设固定检查点，到达即停，由坡度要求的**复核方**共同裁决：**放行 / 折返 / 入段**。**任何一方否决即强制折返**，不自动续行。

### 2. 坡度分级准入 Grade-based Access —— 越陡越严
任务按风险面分三级，坡度越高准入复审越严：

| 坡度 | 适用 | 复核要求 |
|---|---|---|
| 缓坡 `gentle` | 普惠/常规任务 | 单一责任人 |
| 中坡 `medium` | 行业验证类任务 | 责任人 + 专业复核 |
| 陡坡 `steep` | 高影响/攻坚类任务 | 责任人 + 专业复核 + 公众代表 |

### 3. K 标版本 K-marker Versioning —— 永久留痕
每次数据更新、复算、放行记入一个新 K 标，以 **SHA-256 内容寻址 + 哈希链** 串联：篡改任何一条都会断链，账本逐条可复核。

### 4. 道岔三态 Switch States —— 不设自动恢复
任务状态机：**正线运行 / 侧线折返 / 入段检修**。**不设自动恢复**——从检修态回正线，必须经折返点重新评估；第一次放行走准入闸门，被放行过又被拉回检修的任务禁止自动回正线。

---

## 快速开始

```bash
# 零依赖，3 秒跑通
git clone https://github.com/sukikeeling/switchback
cd switchback
pip install -e ".[dev]"

# 一键复现京张 84 分真实案例（输出转写 + K标账本 + 可观测 trace）
python -m switchback.cli replay jingzhang

# 或从命令行驱动整条治理管线
switchback init
switchback register jz-001 --title "京张方案 v8.1" --grade steep
switchback verify  jz-001 --claims tests/fixtures/claims.json --sources tests/fixtures/sources.json
switchback approve jz-001 --label release
switchback status  jz-001
switchback ledger
```

运行测试：

```bash
python -m pytest            # 23 项测试全绿：协议/治理/账本/技能/案例
```

---

## 多 Agent 协同设计（以 AgentTeams 为设计基点）

GOAI 大赛赛道 1「新智基座 Agent Infra」要求多 Agent 协同设计**必须以 AgentTeams（原名 Hiclaw，开源多 Agent OS）为设计基点**。本项目在其 Manager-Worker 双层 + Matrix 房间 + Higress 网关上编排 6 个 Agent 身份：

| ID | 角色 | 类型 | 职责 | 对应 AgentTeams 能力 |
|---|---|---|---|---|
| `M-OPER` | 运营总监 | Manager | 任务接单、坡度拆解、调度、触发折返点 | Manager Agent 控制流 |
| `W-RESEARCH` | 调研专员 | Worker | 情报采集、事实核验、来源管理 | Worker + MCP 工具 |
| `W-CREATE` | 内容专员 | Worker | 结构化工件生产、双语输出 | Worker + Skill |
| `W-VERIFY` | 校验专员 | Worker | 数值三处对齐、引用双向、哈希核对 | Worker + evidence-verify |
| `W-RISK` | 风险与合规 | Worker | risk ledger、权利声明、合规矩阵 | Worker + 审计记录 |
| `G-GOVERNOR` | 监理 Agent | 治理组件 | 折返裁决、坡度准入、道岔三态、不设自动恢复 | Matrix 房间内人机可见、可实时干预 |

**闭环 8 步全覆盖**：任务输入 → 任务拆解 → 上下文传递 → 工具调用 → 结果验证 → 执行证据沉淀 → 审批与回滚 → 经验沉淀。人通过 Matrix 客户端观察任意房间、实时干预；Worker 不持有真实 API Key（凭证透传 + 消费者令牌），即使被攻破也不泄露凭证。

详见 [docs/agentteams-mapping.md](docs/agentteams-mapping.md) 与 [docs/identity.md](docs/identity.md)。

---

## 六大核心 Skill

Skill 是赛道 25% 权重的评审轴。六个 Skill 全部以可执行 Python 函数实现，每个都带结构化 `SkillSpec`（名称/用途/输入输出/调用条件/依赖/失败处理/安全边界/复用价值）：

| Skill | 功能 | 失败处理 |
|---|---|---|
| `grade-access` | 坡度准入：按风险面分缓/中/陡 | 无法判定时默认陡坡（从严） |
| `evidence-verify` | 证据核验：数值三处对齐 + 引用双向 + 内容哈希 | 任一失败 → 强制折返 |
| `kmarker-ledger` | K 标账本：不可变哈希链 | 链校验失败 → 拒绝写入 |
| `risk-ledger` | 风险台账：结构化风险 + 缓释 + 人工复核责任人 | score≥4 → 强制人工复核 |
| `switch-decision` | 折返裁决：三方复核，任何否决即折返 | 票数不足 → 拒绝裁决 |
| `lessons-learned` | 经验沉淀：复盘写回 Agent 记忆 | 失败不阻断主线 |

详见 [docs/skills.md](docs/skills.md)。这些 Skill 可作为**可复用 Skill 资产**沉淀进 AgentTeams 生态（Skill 门户 / 自托管）。

---

## 可观测（OTel 兼容）与上下文机制

- **可观测**：`Tracer` 输出 OpenTelemetry 形状的 JSONL 事件流（`trace_id`/`span_id`/parent/属性），同时维护 Metric 计数器；满足赛道"Trace/Log/Metrics 至少 1-2 类 + 建议遵循 OTel GenAI 标准"。
- **上下文（RAG 4 选 2+1）**：
  - **共享状态管理** `SharedState` — Manager 写、Worker 读，带 K 标版本溯源；
  - **Agent 记忆存储** `AgentMemory` — 追加式情景记忆 + 关键词检索（RAG 的种子层）；
  - **轨迹可观测** — Tracer 事件流即执行轨迹。

---

## 真实案例：京张 84 分（旗舰证据）

```
$ python -m switchback.cli replay jingzhang

== 京张 84 分案例重放（Switchback Governance in action）==
版本     PR        分    裁决            证据
------------------------------------------------
v5      PR#605    67    PASS           ✓
v8      PR#1220   70    折返↩           ✓
v8.1    PR#1468   84    PASS           ✓
v8.2    PR#1816   70    折返↩           ✓
v8.5    PR#2205   77    折返↩           ✓
v8.10   PR#2328   76    折返↩           ✓
最高分：84（v8.1 PR#1468）→ 84 高水位保持
教训：'加内容' 5 轮无效；克制 + 结构化证据 + 折返复核 = 高分配方。
```

每次提交都过"证据核验 → 折返点三方复核 → K 标放行/折返"，账本不可变，Trace 可回放。这就是"**真实任务闭环 + 结果校验 + 安全熔断审计**"的直接实证。

---

## 目录结构

```
switchback/
├── switchback/               # Python 包（零第三方依赖）
│   ├── protocol.py           #   协议类型：Grade/SwitchState/Verdict/Checkpoint/KMarker
│   ├── governor.py           #   监理 Governor：状态机 + 声明式策略引擎
│   ├── ledger.py             #   K标账本（哈希链）+ 风险/权利台账
│   ├── trace.py              #   OTel 兼容可观测（Trace/Log/Metrics）
│   ├── state.py              #   共享状态 + Agent 记忆
│   ├── skills.py             #   六大核心 Skill（可执行）
│   ├── cases/jingzhang.py    #   京张 84 分案例重放
│   └── cli.py                #   CLI：init/register/verify/approve/reject/status/ledger/replay
├── tests/                    # 23 项测试
├── docs/                     # 协议/架构/Agent Identity/Skill/AgentTeams 映射
├── competition/              # GOAI 初赛材料（简介/方案 PDF/清单）
└── DESIGN.md                 # 设计蓝图
```

## 开源与合规

- **License**：[Apache-2.0](LICENSE)（与 AgentTeams/Hiclaw 一致，全量开源）
- **第三方依赖**：运行零依赖；开发依赖仅 pytest
- **数据与权利**：京张案例数据来自公开的开源竞赛仓库（open-city-ai/haidian），demo 不包含任何非公开或受限数据
- **安全**：凭证透传设计（Worker 不持真实 Key）；见 [SECURITY.md](SECURITY.md)

## 相关文档

| 文档 | 内容 |
|---|---|
| [DESIGN.md](DESIGN.md) | 设计蓝图与赛道 rubric 对齐 |
| [docs/protocol.md](docs/protocol.md) | 折返治理协议规范 |
| [docs/architecture.md](docs/architecture.md) | 系统架构 |
| [docs/identity.md](docs/identity.md) | Agent Identity 清单（参赛手册附录A 对应） |
| [docs/skills.md](docs/skills.md) | Skill 清单（名称/用途/输入输出/失败处理/复用） |
| [docs/agentteams-mapping.md](docs/agentteams-mapping.md) | 到 AgentTeams 的协同设计映射 |
| [competition/](competition/) | GOAI 初赛材料（简介/方案 PDF/清单） |
