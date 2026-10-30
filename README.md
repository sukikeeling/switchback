# Switchback · 折返治理（Industrial Production Guardrail v1.0）

<div align="center">

> **让每一次 Agent 决策，都沿轨道可查、可停、可回头。**  
> **让机器拥有狂奔的算力，让人类拥有随时拉下铁闸、换向折返的绝对主权。**

[![Status: Production Guardrail v1.0](https://img.shields.io/badge/Status-Production%20Guardrail%20v1.0-success?style=for-the-badge&logo=shield)](https://github.com/sukikeeling/switchback)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Stdlib)-brightgreen?style=for-the-badge)](https://github.com/sukikeeling/switchback)
[![12-Dim Verification](https://img.shields.io/badge/12--Dim%20Gates-22%2F22%20PASS-success?style=for-the-badge)](scripts/full-system-verify.sh)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg?style=for-the-badge)](LICENSE)

<br/>

🌐 **[在线折返模拟器](https://sukikeeling.github.io/switchback/)** &nbsp;&nbsp; | &nbsp;&nbsp; 📑 **[架构设计规范](docs/architecture.md)** &nbsp;&nbsp; | &nbsp;&nbsp; 🛡️ **[工程边界与诚实声明](docs/limitations.md)**

</div>

---

## 📖 项目溯源：从真实生产阵痛，到工业级治理中枢

**Switchback（折返治理）** 绝非凭空捏造的概念，它是作者在京张 AI 创新带开源征集（`open-city-ai/haidian`）中，**亲历 22 版迭代、16 个 PR 极限拉扯，被“数值三处对不齐”、“CRLF 换行符哈希错位”、“中英标记漂移 42 处”等真实生产事故折磨后，用血泪经验提炼出的制度杰作**。

它以中国铁路先驱詹天佑设计的京张铁路青龙桥**“人字形折返线”**为灵魂原型——列车遇陡坡必停、换向、以退为进；任何复杂的 Multi-Agent 决策同样必须：
> **“到站必停、三方复核、物理拔除自动续行”**。

在最初的比赛长海报里定格的遗憾，如今在 **v1.0 工业级生产体** 中已全面抹平与跨越。从一个 CLI 原型，彻底跃升为**真正嵌在现代多智能体集群咽喉上的“铁路道岔级”治理中枢（Production-Grade Agent Guardrail）**。

---

## 🏛️ 整体架构（System Architecture）

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
       │  │ - 缓坡/中坡/陡坡动态分级│   │ - 数值三处硬核交叉对齐        │  │
       │  │ - 敏感操作/凭证防泄漏  │   │ - 语义双向引用与源哈希校验    │  │
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
       │  │ - RFC-6962 Merkle 树防篡改  │ │ - 毫秒级决策因果 Trace     │  │
       │  └─────────────────────────────┘ └───────────────────────────┘  │
       └───────────────────────────────────┬─────────────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │         人类总指挥台 (Human Governor WebUI)   │
                    │  - 一键回溯时光机 / 异态分支审查 / 双签修正放行 │
                    └──────────────────────────────────────────────┘
```

---

## 🎯 工业级核心机制全景

| 模块 | 机制设计 | 解决的生产痛点 |
|---|---|---|
| **道岔状态机**<br/>`switchback/governor.py` | 严格定义 `MAIN_LINE`（正线）、`SIDING`（侧线折返）、`DEPOT`（入段检修）三态。<br/>• 物理拔除自动续行（`AntiRetryLoopError` 熔断）<br/>• 探索预算递减衰减，终结无脑“反思-道歉-重复试错”死循环。 | Agent 陷入循环报错并消耗百万 Token 的失控死锁。 |
| **实时证据核验器**<br/>`switchback/verifier.py` | **Live Evidence Engine**：<br/>• 文本、数据表、API 三处硬核交叉数值验证（容差 0.001）<br/>• 引用双向链接校验与源内容 SHA-256 活体快照锁<br/>• CRLF 换行符哈希错位、`package_id` 占位残留、中英标记漂移 100% 拦截。 | 幻觉胡编数据、数字前后打架、换行符污染哈希链。 |
| **不可篡改 K 标账本**<br/>`switchback/ledger.py`<br/>`switchback/merkle.py` | • 每一道决策形成不可篡改的递增公里标（`km`）<br/>• RFC-6962 域分离规范 SHA-256 Merkle 树，支持 $O(\log N)$ 存在性证明<br/>• 原生标准库实现 SQLite WAL 原子并发写，支持法律效力审计报告导出。 | 出了生产事故谁改了什么死无对证，日志被事后涂抹。 |
| **零侵入 Sidecar 网关**<br/>`switchback/sidecar.py` | • HTTP 反向代理与 JSON-RPC 拦截中枢<br/>• 触发折返即刻物理硬熔断：返回 HTTP `423 Locked` / JSON-RPC `-32099`，抛出 `ErrSwitchbackTriggered`<br/>• 内置 Higress 消费者凭证金库与速率控制。 | 业务代码需侵入式改动的包袱；高危命令脱离监管发往集群。 |
| **人类总指挥台**<br/>`switchback/cockpit.py` | **Human Governor Cockpit**：<br/>• `/cockpit` 响应式大屏，实时呈现决策轨道、道岔拓扑与因果树<br/>• **时光机一键回溯**（`rollback_to_km`），状态即时还原到任意健康历史锚点<br/>• **人类+监理双签补丁放行**（`human_intervene`），重设预算重回正线。 | 人工只能干瞪眼看 Agent 崩掉，无法在线安全干预。 |
| **标准 MCP 协议服务**<br/>`switchback/mcp_server.py` | 完整实现 Anthropic / Claude 标准 Model Context Protocol（JSON-RPC 2.0）：<br/>• 支持 `stdio` 传输与 HTTP `/v1/mcp/rpc`<br/>• 规范暴露 `register_task`、`verify_evidence`、`cast_vote`、`rollback_checkpoint`、`audit_ledger` 等全套工具。 | 与 Cursor、Windsurf、Claude Desktop、Antigravity 零配置即插即用。 |

---

## 🏆 三大跨行业实证闭环（Cases）

### 案例 1：京张城市设计 AI 评审（`jingzhang`）
- **背景**：海淀区城市更新 AI 方案方案征集真实历史复现。
- **验证**：真实重放 16 个 PR、22 版迭代的博弈全过程。
- **成果**：在严格的三方复核与道岔分流下，最终以 **84/100 分**（行业极高分）完成归档；支持 `--live` 参数直连 GitHub REST API 校验历史提交哈希真实性。

### 案例 2：生产零人工智能运维事故自愈（`ops`）
- **背景**：支付服务出现 5xx 突增与 CPU 报警。
- **过程**：Agent 误判企图执行全量数据库回滚，被动态坡度引擎（陡坡）一票否决，道岔紧急扳向侧线；随后切换至金丝雀热补丁，多指标复核通过后安全放行，实现 0 停机自愈。

### 案例 3：AI 软件研发与安全发布（`devsecops` · M6）
- **背景**：企业级生产数据库变更与版本发布流水线。
- **过程**：AI 编码助手尝试执行包含敏感未加密密钥提交与未经验证的高危删列（`DROP COLUMN`），Live Sidecar 网关直接物理切断网络链路，强制将列车压入检修段（`DEPOT`）；人类架构师于 WebUI 总指挥台在线审查，双签注入安全的 Expand-Contract 阶段性迁移并重回正线。

---

## ⚡ 快速开始（Quick Start）

本项目保持极致的**零第三方运行时依赖（Zero Runtime Dependencies）**，使用标准 Python 3.10+ 标准库即可运行全部核心组件。

### 1. 安装与准备
```bash
git clone https://github.com/sukikeeling/switchback.git
cd switchback
pip install -e ".[dev]"
```

### 2. 三大真实案例一键重放
```bash
# 案例一：京张 84 分城市设计评审重放
python -m switchback.cli replay jingzhang

# 案例一（Live 模式）：直连 GitHub API 校验真实 PR 与提交链
python -m switchback.cli replay jingzhang --live

# 案例二：生产支付系统故障自主运维闭环
python -m switchback.cli replay ops

# 案例三：研发安全发布与高危删列硬熔断（M6 闭环）
python -m switchback.cli replay devsecops
```

### 3. 运行 M5 工业级对抗评测基准
```bash
python -m switchback.cli benchmark
```
*输出：6 类恶意对抗场景（高危命令、死循环重试、数值伪造、标记漂移等）100% 召回率、100% 精确率、P50 判定延迟 < 2ms。*

### 4. 启动 Sidecar 治理网关与人类总指挥台 WebUI
```bash
# 启动本地治理中枢网关与 WebUI Cockpit（默认端口 8780）
python -m switchback.cli serve --host 127.0.0.1 --port 8780

# 浏览器访问总指挥台：http://127.0.0.1:8780/cockpit
# 查看 OTel 指标流：http://127.0.0.1:8780/metrics
```

### 5. 标准 MCP Server 启动（集成至 Claude Desktop / Cursor）
```bash
# stdio 模式启动
python -m switchback.cli mcp-stdio
```
在 Claude Desktop 或 Antigravity 的配置中添加：
```json
{
  "mcpServers": {
    "switchback": {
      "command": "python",
      "args": ["-m", "switchback.cli", "mcp-stdio"]
    }
  }
}
```

### 6. CLI 原生全链路交互体验
```bash
# 初始化环境
python -m switchback.cli init

# 注册任务并设定坡度（steep / moderate / gentle）
python -m switchback.cli register jz-001 --title "京张方案 v10" --grade steep

# 提交三处证据验证（正文、表格、API）
python -m switchback.cli verify jz-001 --claims tests/fixtures/claims.json --sources tests/fixtures/sources.json

# 监理方投票
python -m switchback.cli vote jz-001 --role governor --name G-ALPHA --verdict pass

# 遇阻入段后，人类总指挥台双签修正放行
python -m switchback.cli intervene jz-001 --human sukikeeling --governor G-ALPHA --patch '{"safe_migration":true}'

# 时光机一键回溯至指定里程标
python -m switchback.cli rollback jz-001 --km 0 --actor sukikeeling

# 导出带 Merkle Root 的密码学不可篡改审计报告
python -m switchback.cli audit --task jz-001
```

---

## 🧪 自动化测试与 12 维工业级交付门禁

Switchback 配备极其严苛的自动化交付防护网，任何一行代码破坏协议不变量都会被毫秒级拦截：

```bash
# 运行 56 项全覆盖自动化测试
python -m pytest

# 运行 12 维度全系统工业级交付门禁脚本（包含协议不变量/并发WAL/防漂移/OTel/Sidecar等）
bash scripts/full-system-verify.sh
```

**门禁验证概况：**
```
═══ 结果：✅ 22 维检测项全部通过   ⚠️ 0 警告   ❌ 0 失败 ═══
✅ 全系统 12 维验证全部通过 — 工业级生产体交付就绪
```

---

## 🗺️ 里程碑交付收官清单（ROADMAP 100% COMPLETE）

| 里程碑 | 状态 | 交付成果与技术内涵 |
|---|---|---|
| **M0 协议核心** | ✅ 100% 完成 | 纯原生实现折返点、坡度分级准入、K 标哈希链账本、道岔三态状态机，**物理拔除自动续行**。 |
| **M1 双案例实证** | ✅ 100% 完成 | 京张 84 分城市设计评审真实重放 + 生产运维故障自愈，`--live` 直连真实 GitHub API 验证历史 PR。 |
| **M2 标准 Skill 与 MCP** | ✅ 100% 完成 | 落地六大标准 Skill 包（配齐 `SkillSpec` 与标准 `SKILL.md`）+ 工业级 MCP JSON-RPC 2.0 服务端。 |
| **M3 在线模拟器与 WebUI** | ✅ 100% 完成 | 零依赖在线折返模拟器（`index.html`）+ 交互式人类总指挥台 Cockpit（`switchback/cockpit.py`）。 |
| **M4 集群部署与 Sidecar 网关** | ✅ 100% 完成 | `SwitchbackSidecarGateway` 物理硬熔断 + `AgentTeamsCluster` / `MatrixRoomBus` 事件总线 + `deploy/docker-compose.yml`（Matrix + Higress + OTel/Jaeger + Prometheus + Grafana）。 |
| **M5 评测体系与生态分发** | ✅ 100% 完成 | 6 类对抗负载工业级评测（100% 召回 / 100% 精确 / <2ms 延迟）+ AgentTeams Skill 门户清单自动导出（`switchback/benchmark.py`）。 |
| **M6 第三案例（研发安全发版）** | ✅ 100% 完成 | AI 软件研发与数据库安全变更闭环（`switchback/cases/devsecops.py`），验证框架跨行业通用性。 |

---

## ⚖️ 开源协议与版权声明

本项目基于 [Apache License 2.0](LICENSE) 开源。  
Copyright © 2026 sukikeeling. All rights reserved.
