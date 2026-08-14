---
name: kmarker-ledger
description: K 标账本——每次数据更新/复算/放行记入不可变 SHA-256 内容寻址哈希链，永久留痕，篡改即断链。链校验失败拒绝写入。
assign_when: 任何数据更新、复算、放行、回滚时刻，由 G-GOVERNOR 调用此 Skill 将动作 seal 进账本。需要审计留痕的 Agent 管线节点都应触发。
---

# kmarker-ledger

> Switchback 六大核心 Skill 之三 · 归属 Agent：G-GOVERNOR 监理 Agent

## 用途
堵住"账目不可审"鸿沟：谁做了什么、基于哪个数据版本、结论是什么，全部记入不可变哈希链。京张的 `package_id 残留`（状态漂移）、`CRLF 哈希错位`（证据链断裂）正是此 Skill 设计输入。

## 输入
- `task_id` (str)：任务标识
- `label` (str)：K 标标签（如 `K0 admission` / `K-release`）
- `payload` (dict)：本次变更内容（版本、数值、结论）

## 输出
`KMarker` 条目：`{km, task_id, label, payload, prev_sha, sha256, timestamp}`。

## 调用条件
任何数据更新、复算、放行、回滚时刻。账本只追加不覆盖。

## 依赖工具
`hashlib`（Python 内置，零依赖）＋ `KMarkerLedger`。

## 失败处理
链校验失败 ⇒ `LedgerIntegrityError`，拒绝写入——绝不带着断链继续。

## 安全边界
只追加不覆盖；审计方持链可全量复核；内容寻址保证"改任何一条，后续全部断链"。

## 复用价值
金融 / 合规 / 政务 / 研发发布等一切需审计留痕场景。跨行业：交易流水留痕、变更审计、合规举证。

## 与多 Agent 协同流程的关系
闭环第 6 步（执行证据沉淀）：W-VERIFY 核验通过后，G-GOVERNOR seal 进账本；第 7 步审批与回滚的每一次裁决也记 K 标。

## 实现
`switchback/ledger.py` → `KMarkerLedger.append()/verify_chain()`，CLI `switchback ledger`