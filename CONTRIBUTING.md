# Contributing

感谢你愿意参与 **Switchback（折返治理）**。本项目遵守《[行为准则](https://www.contributor-covenant.org/)》精神。

## 开发流程

1. Fork 本仓库并创建特性分支。
2. 安装：`pip install -e ".[dev]"`。
3. 改动后运行：`python -m pytest`（全部必须通过）。
4. 新能力需附带测试；协议不变量（见 `docs/protocol.md` §2）不允许被削弱。
5. 提交信息用清晰的祈使句（如 `feat: add grade-access confidence threshold`）。
6. 推送后开 Pull Request，描述动机与测试证据。

## 代码风格

- Python 3.10+，标准库优先；尽量零第三方运行依赖。
- 新类型放 `switchback/protocol.py`，行为放 `governor.py`，Skill 放 `skills.py`。
- 双语注释可接受；中文注释用于协议语义解释。

## 协议一致性

任何对裁决规则、账本哈希链、道岔状态机的改动，都必须更新 `docs/protocol.md` 的"不变量"节并保持全部测试绿色。**任何一方否决即强制折返**与**不设自动恢复**是项目的根基，不接受回退。
