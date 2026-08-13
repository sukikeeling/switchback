# Skill 清单

> GOAI 赛道 1 要求：每个方案至少提供核心 Skill 清单，并说明名称/用途/输入输出/调用条件/依赖工具/失败处理/安全边界/复用价值/与多 Agent 协同流程的关系。
> 本清单与 `switchback/skills.py` 中的 `SkillSpec` **逐项对应**（Skill 即代码）。

## 概览

| # | Skill | 归属 Agent | 功能 |
|---|---|---|---|
| S1 | `grade-access` | M-OPER / G-GOVERNOR | 坡度分级准入 |
| S2 | `evidence-verify` | W-VERIFY | 证据核验（数值三处/引用双向/内容哈希） |
| S3 | `kmarker-ledger` | G-GOVERNOR | K 标账本（不可变哈希链） |
| S4 | `risk-ledger` | W-RISK | 风险台账 |
| S5 | `switch-decision` | G-GOVERNOR | 折返裁决（三方复核） |
| S6 | `lessons-learned` | M-OPER / 全体 | 经验沉淀 |

## 逐项说明

### S1 grade-access 坡度准入
- **用途**：按任务风险面（影响度/敏感度/可逆性/信任度）分配缓坡/中坡/陡坡。
- **输入**：task payload（impact/sensitivity/reversibility）+ trust_score
- **输出**：`Grade` 枚举
- **调用条件**：任务接单时（admission 折返点前）
- **依赖工具**：无（纯函数）
- **失败处理**：无法判定时默认 `STEEP`（从严）
- **安全边界**：只做分级不做授权，授权仍需折返点复核
- **复用价值**：任何多 Agent 系统的任务准入层
- **与协同流程**：决定后续所有折返点的复核角色集合

### S2 evidence-verify 证据核验
- **用途**：数值三处对齐 + 引用双向检查 + 内容寻址哈希，堵住幻觉与错位。
- **输入**：claims dict + sources dict + numeric_keys
- **输出**：`VerificationReport`（passed + 逐项检查）
- **调用条件**：产出物进入 post_verify 折返点之前
- **依赖工具**：hashlib/re（内置）
- **失败处理**：任一检查失败 ⇒ passed=False ⇒ 强制标记 REWORK 并折返
- **安全边界**：只读校验不改工件；不通过不进入审批
- **复用价值**："Agent 输出不可信"问题的第一道闸门，跨行业复用
- **实证**：京张 `CRLF 哈希错位`、`数值三处对不齐` 正是此 Skill 拦截的失败模式

### S3 kmarker-ledger K 标账本
- **用途**：每次数据更新/复算/放行记入不可变哈希链 K 标。
- **输入**：task_id + label + payload
- **输出**：`KMarker`（km/sha256/prev_sha）
- **调用条件**：任何数据更新、复算、放行时刻
- **依赖工具**：`KMarkerLedger`
- **失败处理**：链校验失败 ⇒ `LedgerIntegrityError`，拒绝写入
- **安全边界**：只追加不覆盖；审计方持链可全量复核
- **复用价值**：金融/合规/政务等一切需审计留痕场景

### S4 risk-ledger 风险台账
- **用途**：结构化记录风险、缓释措施与人工复核责任人。
- **输入**：风险字段（id/title/score/note/mitigation/human_review）
- **输出**：风险条目（score≥4 ⇒ 标记 `mandatory_human_review`）
- **调用条件**：全流程持续（准入/每次折返/放行前）
- **依赖工具**：`RiskLedger`
- **失败处理**：风险升级 ⇒ 标记强制人工复核并暂停放行
- **安全边界**：只记录与标记，不替代人工决策
- **复用价值**：等保/合规审计的标准化风险视图

### S5 switch-decision 折返裁决
- **用途**：三方复核裁决，任何否决即强制折返/入段。
- **输入**：`Checkpoint`（required_roles 已全部投票）
- **输出**：`Verdict`（pass/turn_back/depot）
- **调用条件**：每个折返点票数收满时
- **依赖工具**：`Checkpoint`
- **失败处理**：票数不足 ⇒ `SwitchbackError` 拒绝裁决；不自动恢复
- **安全边界**：裁决后状态迁移必须由人显式触发（道岔）
- **复用价值**：一切需审批与回滚的 Agent 管线核心

### S6 lessons-learned 经验沉淀
- **用途**：把复盘结论写回 Agent 记忆，形成"教训-规则"闭环。
- **输入**：agent_id + 复盘结论 + tags
- **输出**：`MemoryEntry`
- **调用条件**：每个任务闭环收尾 / 每次折返复盘时
- **依赖工具**：`AgentMemory`
- **失败处理**：写入失败不影响主线，标记 `memory_warn`
- **安全边界**：只写回记忆，不自动改写治理策略
- **复用价值**：让系统越用越聪明；复赛"经验沉淀"维度的直接落点

## 复用与生态分发

- 每个 Skill 的 `SkillSpec` 是**机器可读声明**，可沉淀进 AgentTeams 生态（Skill 门户 / 自托管 AI 市场）。
- 迁移成本：Skill 与协议解耦，输入/输出为 JSON 契约，替换实现（如换向量 RAG）只需协议适配。
- 京张 84 分案例（`examples/cases/jingzhang.py`）是全部六 Skill 的一次真实组合演练。
