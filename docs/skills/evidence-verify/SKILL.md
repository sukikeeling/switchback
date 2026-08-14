---
name: evidence-verify
description: 证据核验——数值三处对齐 + 引用双向检查 + 内容寻址哈希，堵住 Agent 输出的幻觉与错位。任一检查失败即强制折返，不自动放行。
assign_when: 当一个 Worker Agent 产出结构化工件（方案/文档/数据）并即将进入审批折返点之前，必须由 W-VERIFY 调用此 Skill 做证据核验。任何含数值声明、来源引用或需要内容完整性的产出都应触发。
---

# evidence-verify

> Switchback 六大核心 Skill 之二 · 归属 Agent：W-VERIFY 校验专员

## 用途
堵住 Agent 从 Demo 到 Production 的"结果不可信"鸿沟：数值三处对不齐、引用错位、内容哈希不符。京张竞赛的 `CRLF 哈希错位`、`数值三处对不齐` 正是此 Skill 拦截的失败模式。

## 输入
- `claims` (dict)：含数值声明、来源引用的产出物
- `sources` (dict)：可用来源清单
- `numeric_keys` (list)：需"三处对齐"的数值键名

## 输出
`VerificationReport`：
```json
{
  "passed": false,
  "checks": [
    {"check": "numeric_three_way", "key": "score", "ok": false, "values": [84, 84, 70]},
    {"check": "reference_forward", "ok": true, "missing": []},
    {"check": "reference_backward", "ok": false, "uncited": ["UNUSED"]},
    {"check": "content_hash", "ok": true, "digest": "e09eefc2ddaf…"}
  ]
}
```

## 调用条件
产出物进入 `post_verify` 折返点之前。任何含数值/引用/完整性的产出必经此 Skill。

## 依赖工具
`hashlib` / `re`（Python 内置，零依赖）。

## 失败处理
任一检查失败 ⇒ `passed=False` ⇒ `governor.turn_back()` 强制标记 REWORK 并折返到侧线。**不自动放行、不自动修复**——由人决定返工方向。

## 安全边界
只读校验，不改动工件本身。不通过不进入审批折返点。`content_sha256` 字段排除自身参与哈希计算（否则永不匹配）。

## 复用价值
"Agent 输出不可信"问题的第一道闸门，跨行业复用：运维事故根因核验、客服方案合规核验、研发缺陷复现核验、金融理赔材料核验。

## 与多 Agent 协同流程的关系
W-VERIFY 在闭环第 5 步（结果验证）执行。通过后 G-GOVERNOR 在第 6 步 seal K 标；失败则触发第 7 步的折返/回滚。是"任何否决即折返"不变量在证据层的落点。

## 实现
`switchback/skills.py` → `evidence_verify(claims, sources, numeric_keys)`
