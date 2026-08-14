---
name: lessons-learned
description: 经验沉淀——把复盘结论写回 Agent 记忆（追加式情景记忆 + 关键词检索），形成"教训-规则"闭环。写入失败不阻断主线。
assign_when: 每个任务闭环收尾时、每次折返复盘时，由 M-OPER 或任意 Agent 调用。任务被折返过、出过事故或完成重大里程碑后必须触发。
---

# lessons-learned

> Switchback 六大核心 Skill 之六 · 归属 Agent：M-OPER / 全体 Agent

## 用途
堵住"同样的坑踩两次"：把折返、事故、评审反馈沉淀为可检索记忆。京张"5 轮内容增强无效"的教训若早入记忆，可省 3 轮无效迭代。

## 输入
- `agent_id` (str)：沉淀者标识
- `conclusion` (str)：复盘结论（教训 / 规则 / 模式）
- `tags` (list)：关键词标签（用于检索）

## 输出
`MemoryEntry`（追加式，可被 `search(keyword)` 检索）。

## 调用条件
每个任务闭环收尾 / 每次折返复盘时。强制：被折返过的任务必须在复盘后收尾。

## 依赖工具
`AgentMemory`（追加式情景记忆，关键词检索，RAG 的种子层）。

## 失败处理
写入失败不影响主线，标记 `memory_warn`；记忆是增强而非阻断组件。

## 安全边界
只写回记忆，不自动改写治理策略——经验沉淀与策略变更之间永远隔着人工评审。

## 复用价值
让系统越用越聪明；"经验沉淀"是赛道闭环 8 步的第 8 步，也是复赛知识库 RAG 的直接落点。

## 与多 Agent 协同流程的关系
闭环第 8 步（经验沉淀）：复盘结论写回 AgentMemory，后续任务经关键词检索复用——京张 `'加内容' 5 轮无效` 的教训即此类条目。

## 实现
`switchback/state.py` → `AgentMemory.remember()/search()`，案例中 `lessons` 计数由该 Skill 产出