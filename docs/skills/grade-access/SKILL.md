---
name: grade-access
description: 坡度分级准入——按任务风险面（影响度/敏感度/可逆性/信任度）分配缓坡/中坡/陡坡，坡度越高准入复核越严。无法判定时默认陡坡（从严）。
assign_when: 当 M-OPER 运营总监接到新任务、需要决定其风险等级与复核角色集合时调用。任何任务进入 admission 折返点之前必须完成分级。
---

# grade-access

> Switchback 六大核心 Skill 之一 · 归属 Agent：M-OPER 运营总监 / G-GOVERNOR 监理

## 用途
把"坡度越高越严"的协议不变量落到任务准入层：任务按风险面分级，决定后续所有折返点的复核角色集合，堵住"低风险任务过度审批、高风险任务裸奔"两类失衡。

## 输入
- `task_payload` (dict)：任务影响度 / 敏感度 / 可逆性 / 信任度字段
- `trust_score` (float)：对任务来源或执行方的信任评分

## 输出
`Grade` 枚举：`gentle`（缓坡）/ `medium`（中坡）/ `steep`（陡坡）。

## 调用条件
任务接单时（admission 折返点之前）。任何任务未经分级不得进入执行管线。

## 依赖工具
无（纯函数，零依赖）。

## 失败处理
无法判定时默认 `STEEP`（从严）——宁严勿松，分级错误由折返点复核兜底。

## 安全边界
只做分级不做授权：分级决定"需要谁复核"，不决定"谁能执行"；授权仍由折返点裁决完成。

## 复用价值
任何多 Agent 系统的任务准入层。跨行业：运维告警分级、客服工单分级、研发缺陷分级、金融交易风险分级——同一套坡度语义。

## 与多 Agent 协同流程的关系
闭环第 2 步（任务拆解）前置：M-OPER 先分级、再按级拆解子任务 DAG。决定后续所有折返点的 required_roles。

## 实现
`switchback/skills.py` → `grade_access(task_payload, trust_score)`，返回 `protocol.Grade`