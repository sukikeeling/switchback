# 诚实局限声明（Honest Limitations）

> 借鉴 TRIO3.0-oss 的 `honest_limitation` 字段：把局限写进仓库，不靠评审发现。
> 全系统验证器第 8 维检查本文件是否存在。

## 本仓库是什么

**Switchback 是"可执行的治理协议原型 + 竞赛叙事包装"**，不是接上真实多 Agent 运行时的生产中间件。

- **真实的东西**：折返治理状态机、K 标哈希链账本、六大 Skill 函数、CLI、43 项测试、双案例重放——这些本地能跑、能测、能复现。
- **文档层而非代码层**：AgentTeams / Matrix 房间 / Higress 网关——以"设计基点"形式给出映射文档（`docs/agentteams-mapping.md`），源码里没有 `import agentteams`。

## 已知落差与复赛/后续计划

| 落差 | 当前状态 | 后续 |
|---|---|---|
| AgentTeams 集群实际编排 | 文档映射 | 复赛部署 Docker + Matrix + Higress |
| 六大 Skill 是 Python 函数 | 函数 + SkillSpec 元数据 | 补 SKILL.md 标准 Skill 包格式 |
| 京张案例是剧本重放 | 写死分数表，不调 GitHub API | `--live` 模式拉真实 PR/CI |
| 可观测是 OTel 形状 | JSONL 兼容外形，未接 OTLP | 复赛接 OTLP exporter |
| 证据核验深度 | fixture 级引用/哈希 | 海淀级三处对齐校验器 |

## 为什么这样定位

初赛以**方案设计**为主（赛道1 明确"不要求提交可运行代码"），本仓库是"方案 + 可复现协议原型"的组合。把治理理念写成能跑的代码、把踩过的坑写成不变量，是初赛阶段能交付的最高密度。生产级 multi-agent guardrail 是复赛与决赛的目标。

## 一句话

**本地治理状态机和哈希账本是真的；Agent 集群、Matrix、海淀 CI 复现是文档层。** 不掩盖这个差距，是本仓库的工程诚实底线。
