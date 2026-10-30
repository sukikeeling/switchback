# 系统架构（Industrial Production Guardrail v1.0）

## 全景拓扑

```
                    ┌──────────────────────────────────────────────┐
                    │       AgentTeams / Matrix / Multi-Agent Bus  │
                    │   (M-OPER 调度 / Worker 协同 / 用户交互会话)    │
                    └──────────────────────┬───────────────────────┘
                                           │  HTTP / JSON-RPC / MCP 实时流量
                                           ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │     Switchback Live Sidecar 治理网关 (零侵入内联中枢)            │
       │                                                                 │
       │  ┌───────────────────────┐   ┌───────────────────────────────┐  │
       │  │ 动态坡度准入引擎      │   │ 实时证据核验器 (Live Verifier)│  │
       │  │ - 缓坡/中坡/陡坡动态分级│   │ - 正文/表格/API三处数值对齐   │  │
       │  │ - 消费者令牌与防泄漏  │   │ - 引用快照哈希与原子包防漂移  │  │
       │  └───────────────────────┘   └───────────────────────────────┘  │
       │                                                                 │
       │  ┌───────────────────────────────────────────────────────────┐  │
       │  │ 折返点与道岔状态机 (Strict State Machine)                  │  │
       │  │ [正线运行] ──(异常/否决)──> [侧线折返] ──(严重)──> [入段检修]│  │
       │  │ ★ 铁律：物理拔除自动续行，必须经监理 Agent 与人类双签放行    │  │
       │  └───────────────────────────────────────────────────────────┘  │
       └───────────────────────────────────┬─────────────────────────────┘
                                           │
                                           ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │     不可篡改审计与全景可观测 (Verifiable Ledger & Observability) │
       │  ┌─────────────────────────────┐ ┌───────────────────────────┐  │
       │  │ K 标哈希链账本 (K-Marker)   │ │ 工业级 OTel / OTLP 链路   │  │
       │  │ - SQLite WAL 原子并发存盘   │ │ - Grafana 轨道拓扑大屏    │  │
       │  │ - Merkle 树证据链防篡改     │ │ - Prometheus + 因果 Trace │  │
       │  └─────────────────────────────┘ └───────────────────────────┘  │
       └───────────────────────────────────┬─────────────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │         人类总指挥台 (Human Governor WebUI)   │
                    │  - 一键回溯时光机 / 异态分支审查 / 双签注入放行 │
                    └──────────────────────────────────────────────┘
```

## 模块职责（Python 包 `switchback/`）

| 模块 | 职责 | 关键 API / 组件 |
|---|---|---|
| `protocol.py` | 协议核心类型与物理熔断异常 | `Grade` / `SwitchState` / `Verdict` / `Checkpoint` / `KMarker` / `ErrSwitchbackTriggered` / `AntiRetryLoopError` |
| `governor.py` | 监理引擎：准入、折返裁决、探索预算、防道歉重试、双签放行、时光机回溯 | `admit` / `open_checkpoint` / `vote` / `switch` / `turn_back` / `guard_retry` / `human_intervene` / `rollback_to_km` |
| `merkle.py` | RFC-6962 域分离 SHA-256 Merkle 树与包含证明 | `MerkleTree` / `MerkleProof` / `verify_proof` |
| `ledger.py` | K标账本（SHA-256 哈希链 + Merkle Root + SQLite WAL 原子并发持久化 + 审计报告） | `append` / `verify_chain` / `merkle_root` / `merkle_proof` / `generate_audit_report` |
| `verifier.py` | 活体证据核验引擎（三处数值提取比对 + 引用快照锁 + 原子包 CRLF/`package_id`/双语漂移核验） | `LiveEvidenceEngine` / `SourceSnapshot` |
| `sidecar.py` | 零侵入内联 Sidecar 治理网关与嵌入式 HTTP Server | `SwitchbackSidecarGateway` / `SidecarHTTPServer` / `ConsumerTokenVault` |
| `mcp_server.py` | 标准 MCP JSON-RPC 2.0 Server（支持 `stdio` 与 `/v1/mcp/rpc` HTTP 传输） | `SwitchbackMCPServer` |
| `agentteams.py` | AgentTeams 六大智能体角色协同与 Matrix 房间事件总线 | `AgentTeamsCluster` / `MatrixRoomBus` / `AGENTTEAMS_ROSTER` |
| `cockpit.py` | 人类总指挥台 WebUI 与 IM 审批卡片渲染 | `render_cockpit_html` / `build_cockpit_overview` / `format_im_card` |
| `trace.py` | W3C TraceContext + OTLP/JSON 导出 + Prometheus `/metrics` + 因果决策树 | `Tracer` / `export_otlp_payload` / `export_prometheus` / `build_causal_tree` |
| `benchmark.py` | M5 工业级对抗评测套件与 AgentTeams Skill 门户清单导出 | `run_benchmark_suite` / `export_skill_portal_manifest` |
| `cases/` | 三大跨行业实证闭环（京张 `jingzhang` / 运维 `ops` / 研发安全发版 `devsecops`） | `run_jingzhang_case` / `run_ops_case` / `run_devsecops_case` |
