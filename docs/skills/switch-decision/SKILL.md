---
name: switch-decision
description: 折返裁决——三方复核（责任人/专业/公众），任何一方否决即强制折返或入段，不因多数票放行。票数不足拒绝裁决，不设自动恢复。
assign_when: 当一个折返点（Switchback Node）收集满坡度要求的复核角色投票后，由 G-GOVERNOR 监理 Agent 调用此 Skill 做最终裁决。任何需审批与回滚的 Agent 管线节点都应触发。
---

# switch-decision

> Switchback 六大核心 Skill 之五 · 归属 Agent：G-GOVERNOR 监理 Agent

## 用途
实现"到站必停、任何否决即折返"的协议不变量。堵住"过程不可停"鸿沟——编排一旦开始就自动往下走、错误被一路放大。

## 输入
`Checkpoint`（已收集满 `required_roles` 投票的对象）。

## 输出
`Verdict` 枚举：
- `pass` — 全部放行，继续沿正线
- `turn_back` — 存在否决票，强制折返到侧线（退回重做）
- `depot` — 存在入段票，安全隔离（更安全的一票优先）

## 调用条件
每个折返点票数收满时。票数不足 ⇒ `SwitchbackError` 拒绝裁决，不搞少数服从多数。

## 依赖工具
`Checkpoint`（协议类型）。

## 失败处理
- 票数不足 ⇒ 拒绝裁决（`SwitchbackError`）
- 一票否决 ⇒ 强制折返/入段，**不自动恢复**
- 裁决后状态迁移必须由人显式触发（道岔操作），裁决本身不迁移状态

## 安全边界
裁决与状态迁移解耦：裁决只给 Verdict，状态迁移由 `governor.switch()` 显式触发。这保证"不设自动恢复"不会被裁决逻辑绕过。

## 复用价值
一切需审批与回滚的 Agent 管线核心。跨行业：运维变更审批、客服方案放行、研发发布门、金融处置复核。

## 与多 Agent 协同流程的关系
闭环第 7 步（审批与回滚）。G-GOVERNOR 在 Matrix 房间内裁决，人可随时干预。是"不设自动恢复"不变量在裁决层的落点。

## 实现
`switchback/skills.py` → `switch_decision(checkpoint)`，底层调 `Checkpoint.resolve()`
