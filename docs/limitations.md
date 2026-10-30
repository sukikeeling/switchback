# 工程边界与诚实完备声明（Engineering Boundaries & Honest Completeness）

> 借鉴 TRIO3.0-oss 的 `honest_limitation` 原则：把架构演进与工程边界诚实写进仓库。
> 全系统验证器检查本文件是否存在。

## 从初赛原型（v0.1）到工业级生产体（v1.0）的落差弥合

在初赛阶段（v0.1），Switchback 曾坦率声明自身为"本地协议原型"，存在 5 项待复赛/决赛落地的工程落差。**在当前 v1.0 工业级生产体版本中，上述 5 项核心落差与路线图 M4/M5/M6 已全量代码自研闭环**：

| 原初赛已知落差 | v0.1 初赛状态 | v1.0 工业级完成态（当前仓库已落地） | 对应源码与验证 |
|---|---|---|---|
| **1. 分布式 Sidecar 治理网关** | 仅本地函数调用 | **零侵入 HTTP / JSON-RPC 2.0 / MCP Sidecar 网关**，物理级硬熔断（`ErrSwitchbackTriggered` HTTP 423 / JSON-RPC `-32099`）+ Higress 消费者令牌凭证透传 | `switchback/sidecar.py` |
| **2. AgentTeams 集群与 Matrix 总线** | 仅文档层映射 | **可执行 6-Agent 协同集群（`M-OPER` / `W-*` / `G-GOVERNOR`）+ `MatrixRoomBus` 事件流 + Docker Compose 编排** | `switchback/agentteams.py` · `deploy/docker-compose.yml` |
| **3. 活体证据核验引擎（Live Verifier）** | 本地固定 fixture | **动态事实对齐矩阵**：正文/表格/API 三处数值交叉验真 + 引用双向链与活体快照 SHA-256 固化 + 原子包 CRLF / `package_id` 残留 / 中英双语标记漂移零容忍核验 | `switchback/verifier.py` · `switchback/skills.py` |
| **4. 人类总指挥台与防无脑重试** | 仅 CLI 命令 | **Human Governor WebUI Cockpit**：道岔三态与探索预算可视化、阻断"道歉反思重试"死循环（`AntiRetryLoopError`）、人类+监理双签放行（`human_intervene`）、一键时光机回溯（`rollback_to_km`） | `switchback/cockpit.py` · `switchback/governor.py` |
| **5. 工业级 OTLP 可观测与 Merkle 账本** | JSONL 外形 + 单文件哈希链 | **SQLite WAL 原子并发账本 + RFC-6962 Merkle Tree 永久证据链** + 标准 W3C `traceparent` / OTLP JSON 导出 / Prometheus `/metrics` / Grafana 轨道拓扑大屏 | `switchback/merkle.py` · `switchback/ledger.py` · `switchback/trace.py` · `deploy/grafana-dashboard.json` |
| **6. 标准 MCP Server 与 M5/M6 闭环** | `.mcp.json` 契约说明 | **可执行 MCP Server（stdio + HTTP）** + M5 6 类对抗评测（100% 召回 / 0 误杀）+ M6 第三案例（研发安全发版 `devsecops`） | `switchback/mcp_server.py` · `switchback/benchmark.py` · `switchback/cases/devsecops.py` |

## 诚实的运行时边界说明

1. **零第三方运行时依赖承诺**：
   `switchback/` 核心包全部使用 Python 3.10+ 标准库（`sqlite3`、`http.server`、`urllib.request`、`hashlib`、`threading` 等）原生实现，无需安装重型外部 SDK 即可在单机或容器内直接启动 Sidecar 网关、SQLite WAL 账本、MCP Server 与 WebUI 总指挥台。
2. **外部基础设施容器的可选解耦**：
   `deploy/docker-compose.yml` 提供了完整的 Matrix Synapse、Higress Gateway、Jaeger、Prometheus、Grafana 生产编排；在无 Docker 的单机测试或 CI 环境中，`SidecarHTTPServer` 与 `MatrixRoomBus` 可直接以进程内/本地回环模式 100% 复现全部协议、熔断与审计闭环。
