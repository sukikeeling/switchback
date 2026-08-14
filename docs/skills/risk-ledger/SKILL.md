---
name: risk-ledger
description: 风险台账——结构化记录风险、缓释措施与人工复核责任人；风险评分 ≥4 强制标记人工复核并暂停放行。
assign_when: 全流程持续调用：任务准入时、每次折返时、放行前，由 W-RISK 风险与合规 Agent 维护。任何含高风险动作（写操作、外部发布、资金处置）的节点都应触发。
---

# risk-ledger

> Switchback 六大核心 Skill 之四 · 归属 Agent：W-RISK 风险与合规 Agent

## 用途
堵住"出事了不可回"的前置环节：把风险在放行前说清楚。京张实践中 `第三方素材权利边界不清`、`数值失实被评审抓到` 都是放行前未登记风险的教训。

## 输入
风险字段：`id` / `title` / `score`（1-5）/ `note` / `mitigation` / `human_review`（责任人角色）。

## 输出
风险条目；`score ≥ 4` 时自动标记 `mandatory_human_review`。

## 调用条件
全流程持续（准入 / 每次折返 / 放行前）。低风险任务至少登记一次；高风险任务逐节点登记。

## 依赖工具
`RiskLedger`（内存 + 持久化 JSON）。

## 失败处理
风险升级 ⇒ 标记强制人工复核并暂停放行，直到人工复核完成——不自动绕过。

## 安全边界
只记录与标记，不替代人工决策；人工复核是放行的必要条件而非充分条件。

## 复用价值
等保 / 合规审计的标准化风险视图。跨行业：运维变更风险评估、客服退款风险、研发发布风险、金融授信风险。

## 与多 Agent 协同流程的关系
贯穿闭环全流程：W-RISK 在准入、折返、放行前维护台账，与 evidence-verify 的输出一起构成 W-VERIFY/G-GOVERNOR 的裁决输入。

## 实现
`switchback/ledger.py` → `RiskLedger.add()/items()`，案例中 `risks` 计数由该 Skill 产出