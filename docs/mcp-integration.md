# MCP 集成契约

> 对应审查报告 A 项落差："AgentTeams/Matrix/Higress 只有文档无代码"。
> 本文件把 Skill → MCP 的迁移路径写成可执行的契约，而非纸面声称。

## 1. 当前状态（诚实）

| 能力 | 当前实现 | 迁移后 |
|---|---|---|
| 六大 Skill | 本地 Python 函数 + `SkillSpec` | MCP server tool，JSON 契约不变 |
| 工具调用 | 直接函数调用 | 经 Higress 网关 + 消费者令牌 |
| 记忆 | `AgentMemory`（进程内 dict） | `@modelcontextprotocol/server-memory` |
| 文件访问 | 直接 `open()` | `@modelcontextprotocol/server-filesystem` |
| GitHub API | 无（案例是剧本） | `@modelcontextprotocol/server-github` |

## 2. `.mcp.json` 配置（已交付）

见仓库根 `.mcp.json`。三个 MCP server：

| Server | 用途 | 对应 AgentTeams 能力 |
|---|---|---|
| `filesystem` | 工作区（账本/任务卡/trace）安全访问 | MinIO 共享对象存储的本地等价 |
| `memory` | AgentMemory 跨 Agent 共享与检索 | AgentTeams `MEMORY.md` + `memory/` 的 MCP 暴露 |
| `github` | 拉取 PR/CI/check-run（`--live` 模式用） | Higress 网关接外部 API，凭证透传 |

## 3. Skill → MCP 迁移契约（评审重点：迁移成本判断）

赛道1 评审原文：*"评审时不要求替代方案已经实现 MCP Server，但需要能够判断其后续迁移到 MCP 时是否只需协议适配，而不是重新设计工具调用链。"*

本仓库六大 Skill 的输入输出已是 JSON 契约（见 `.mcp.json` 的 `switchback_skills_via_mcp` 节），迁移路径：

```
当前：  gov.evidence_verify(claims, sources, numeric_keys) → VerificationReport
迁移后：mcp_tool "evidence-verify"({claims, sources, numeric_keys}) → VerificationReport
       （签名 1:1，只包一层 MCP transport，逻辑不动）
```

**结论**：迁移成本 = 协议适配（包 stdio/http transport），不是重设计工具调用链。这是本方案在 MCP 维度的可判断性证据。

## 4. 凭证安全（对齐 AgentTeams 消费者令牌模型）

- `github` server 的 `GITHUB_PERSONAL_ACCESS_TOKEN` 经环境变量注入，**不硬编码进仓库**（`.gitignore` 已排除 `.env`）。
- 迁移到 AgentTeams 集群后，真实 PAT 存于 Higress 网关，Worker 只持消费者令牌——本配置是单机本地等价，安全模型一致。
- 见 [SECURITY.md](../SECURITY.md)。
