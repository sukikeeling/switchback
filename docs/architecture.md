# 系统架构

## 分层

```
┌────────────────────────────────────────────────────────────────┐
│ 人（人工监理）：终端 CLI / Matrix 客户端观察与实时干预            │
├────────────────────────────────────────────────────────────────┤
│ 治理层 Switchback Governance Layer                             │
│   Governor（监理 Agent G-GOVERNOR）                             │
│   ├─ admission       坡度分级准入（grade-access）               │
│   ├─ checkpoint      折返点裁决（switch-decision）              │
│   ├─ switch          道岔三态状态机（no auto-resume）           │
│   └─ seal            K标账本（kmarker-ledger）                  │
├────────────────────────────────────────────────────────────────┤
│ 编排层 AgentTeams（Manager-Worker + Matrix + Higress）          │
│   M-OPER（Manager）  W-RESEARCH  W-CREATE  W-VERIFY  W-RISK     │
├────────────────────────────────────────────────────────────────┤
│ 基础设施：SharedState 共享状态 · AgentMemory 记忆 · Tracer 可观测│
│           MCP 工具（GitHub API / Web Fetch / 数据源）           │
└────────────────────────────────────────────────────────────────┘
```

## 模块职责（Python 包 `switchback/`）

| 模块 | 职责 | 关键 API |
|---|---|---|
| `protocol.py` | 协议类型：Grade/SwitchState/Verdict/Checkpoint/KMarker/PartyVote | `Checkpoint.resolve()` |
| `governor.py` | 监理引擎：任务准入、折返裁决、道岔操作、K 标密封 | `admit/open_checkpoint/vote/resolve/switch/seal/re_enter_mainline` |
| `ledger.py` | K标账本（哈希链）+ 风险/权利台账 | `append/verify_chain/export` |
| `trace.py` | OTel 兼容可观测：SPAN_START/SPAN_END/LOG + 指标 | `start_span/event/metric` |
| `state.py` | 共享状态（K标溯源）+ Agent 记忆（RAG 种子） | `put/get / remember/recall` |
| `skills.py` | 六大 Skill（含 `SkillSpec` 声明） | `grade_access/evidence_verify/kmarker_seal/risk_record/switch_decision/lessons_learned` |
| `cli.py` | 可复现命令行入口 | `init/register/verify/approve/reject/status/ledger/replay` |
| `cases/jingzhang.py` | 京张 84 分案例端到端重放 | `run_jingzhang_case()` |

## 数据流（一次完整闭环）

```
1. 任务输入    M-OPER 在 Matrix 房间接单，登记任务卡
2. 任务拆解    M-OPER 调 grade-access → 按坡度拆为子任务 DAG
3. 上下文传递  SharedState（带 K 标溯源）+ Matrix 房间共享上下文
4. 工具调用    Worker 经 Higress 网关调 MCP 工具（凭证透传，Worker 不持真实 Key）
5. 结果验证    W-VERIFY 调 evidence-verify：数值三处/引用双向/内容哈希
6. 证据沉淀    通过 → KMarkerLedger.seal() 记入不可变 K 标
7. 审批与回滚  折返点三方复核 → PASS 放行 / TURN_BACK 侧线 / DEPOT 入段（不设自动恢复）
8. 经验沉淀    lessons-learned 写回 AgentMemory → 教训-规则闭环
```

## 可观测信号

`trace.jsonl` 每行为一个 OTel 形状记录：

```json
{"kind":"SPAN_START","name":"evidence-verify","trace_id":"…","span_id":"…","parent_span_id":"…","timestamp_ms":…,"service":"switchback","genai_semconv":"gen_ai.usage.switchback/v1"}
{"kind":"LOG","name":"checkpoint.resolved","attributes":{"verdict":"turn_back",…},…}
```

Metric 计数器随 `Tracer.metric()` 累加，满足"Trace/Log/Metrics ≥1-2 类"。
