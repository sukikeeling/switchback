# 折返治理协议规范（Switchback Governance Protocol）

> 协议版本 v1.0 · 状态：实现于 `switchback/protocol.py` + `governor.py` · 引擎：声明式策略（JSON）

## 1. 词汇表

| 术语 | 铁路原型 | 语义 |
|---|---|---|
| **折返点** Switchback Node | 青龙桥人字形展线折返点 | 管线上的固定检查点，到达即停，任何一方否决即强制折返 |
| **坡度分级** Grade | 33‰ 极限坡度分陡缓 | 任务风险面分级：缓坡/中坡/陡坡 |
| **K 标** K-marker | 铁路里程标 | 每次数据更新/复算/放行记入新版本，内容寻址哈希链 |
| **道岔三态** Switch State | 正线/侧线/入段 | 任务状态机，不设自动恢复 |

## 2. 不变量（Invariants）

协议在任何实现中必须保持以下不变量：

1. **到站必停**：每个折返点未完成裁决前，任务不得越过该点继续执行。
2. **任何否决即折返**：`Verdict ∈ {TURN_BACK, DEPOT}` 的任意一票 ⇒ 整点裁决为折返/入段，绝不因多数票放行。
3. **坡度越高越严**：陡坡要求三方（责任人/专业/公众）全部复核；缓坡仅责任人。复核角色集合由策略声明。
4. **K 标不可篡改**：账本为 SHA-256 内容寻址哈希链；任一条被改，后续全部断链。
5. **不设自动恢复**：已被放行过、又被拉回检修（DEPOT）的任务，禁止自动回正线；必须经一次**全新的**放行式折返点复核。
6. **票数齐才有裁决**：复核方缺票即拒绝裁决（`SwitchbackError`），不搞"少数服从多数"。
7. **一票一投**：同一角色不得重复投票。

## 3. 状态机

```
                ┌──────────── 首次准入（准入闸门，受允许）─────────────┐
                ▼                                                    │
     ┌───────────────┐    决折（否决）      ┌───────────────┐          │
     │  DEPOT 入段检修 │ ──────────────────► │  SIDING 侧线折返 │         │
     └───────────────┘                     └───────────────┘          │
              ▲                                  │                     │
              │ 重新评估（全新approval折返点）      │ 返工后重过折返点      │
              │                                  ▼                     │
              └───────────── MAINLINE 正线运行 ◄───────────────────────┘
                              (放行/继续)
```

- 首次放行：`DEPOT → MAINLINE`，走准入闸门（admission/approval 折返点）。
- 否决：`MAINLINE/SIDING → SIDING`（退回重做）或 `→ DEPOT`（安全隔离）。
- 检修回归：`DEPOT → MAINLINE` **仅**允许经 `re_enter_mainline(approval_checkpoint=PASS)`，任何自动切换抛 `NoAutoResumeError`。

## 4. 折返点裁决规则

```python
def resolve(checkpoint) -> Verdict:
    assert 所有 required_roles 已投票            # 不变量 6
    if any(v.verdict in {TURN_BACK, DEPOT}):    # 不变量 2
        return DEPOT if 存在 DEPOT 票 else TURN_BACK
    return PASS
```

## 5. K 标账本结构

```
entry = {
  km, id, task_id, label, payload,
  prev_sha,          # 前一条的 sha256（链头为 "")
  sha256,            # SHA-256(km, task_id, label, payload, prev_sha, timestamp)
  timestamp,
}
```

校验：从头到尾重算每条 `sha256` 与 `prev_sha` 链接，任何不符抛 `LedgerIntegrityError`。

## 6. 声明式策略（governance.json）

```jsonc
{
  "admission": {
    "gentle": {"requires": ["owner"]},
    "medium": {"requires": ["owner", "professional"]},
    "steep":  {"requires": ["owner", "professional", "public"]}
  },
  "checkpoints": {
    "default": ["admission", "post_verify", "approval", "release"],
    "steep_extra": ["pre_verify", "evidence"]
  },
  "switch": {"no_auto_resume": true, "depot_to_mainline_requires": ["owner", "professional"]}
}
```

策略不进引擎，进配置 —— 运营者可调复核深度而无需改代码。

## 7. 与赛道评审点的对应

| 协议能力 | 赛道 1 评审点 | 权重落点 |
|---|---|---|
| 折返点 + 三方复核 | 结果验证、审批与回滚 | 多 Agent 闭环 25% |
| 坡度分级准入 | 权限边界、安全边界 | 工程落地/安全可审计 20% |
| K 标账本 | 执行证据沉淀、审计 | 工程落地/安全可审计 20% |
| evidence-verify | 结果校验、防幻觉 | Skill 工程 25% |
| 不设自动恢复 | 安全熔断、异常保护 | 工程落地/安全可审计 20% |
