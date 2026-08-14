#!/bin/bash
# Switchback 全系统验证器 —— 8 维度健康检查（借鉴 TRIO3.0-oss full-system-verify.sh）
#
# 设计目标：把 evidence-verify 从"返回 passed=False"升级为"阻断交付（exit 1）"。
# 评审/CI 可直接跑此脚本判定仓库是否健康。任何一维失败 => exit 1。
#
# 用法：  bash scripts/full-system-verify.sh
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

PASS=0; WARN=0; FAIL=0
pass(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
warn(){ echo "  ⚠️  $1"; WARN=$((WARN+1)); }
fail(){ echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "═══ Switchback 全系统验证（8 维度）═══"
echo ""

# ── 1. 代码质量 ───────────────────────────────────────────
echo "═══ 1. 代码质量 ═══"
python -m pytest tests/ -q --tb=no >/dev/null 2>&1 && pass "pytest 全通过" || fail "pytest 有失败"
python -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read()) for f in __import__('pathlib').Path('switchback').rglob('*.py')]" 2>/dev/null && pass "全部 .py 语法有效" || fail "存在语法错误"
grep -rqE 'import\s+(requests|openai|anthropic|langchain)' switchback/ 2>/dev/null && fail "运行时引入了第三方依赖（违反零依赖承诺）" || pass "零第三方运行时依赖"

# ── 2. 协议完整性 ──────────────────────────────────────────
echo "═══ 2. 协议完整性 ═══"
python -c "
from switchback import Grade, SwitchState, Verdict, PartyRole, CheckpointKind, Checkpoint
from switchback.protocol import PartyVote
# 不变量：任何否决即折返
cp = Checkpoint(kind=CheckpointKind.APPROVAL, task_id='t', grade=Grade.STEEP,
                required_roles=[PartyRole.OWNER, PartyRole.PROFESSIONAL, PartyRole.PUBLIC])
cp.add_vote(PartyVote(role=PartyRole.OWNER, name='o', verdict=Verdict.PASS))
cp.add_vote(PartyVote(role=PartyRole.PROFESSIONAL, name='p', verdict=Verdict.PASS))
cp.add_vote(PartyVote(role=PartyRole.PUBLIC, name='u', verdict=Verdict.TURN_BACK))
assert cp.resolve() == Verdict.TURN_BACK, '一票否决未触发折返'
print('协议不变量②（任何否决即折返）成立')
" 2>/dev/null && pass "折返裁决不变量成立" || fail "折返裁决不变量被破坏"

# ── 3. 不设自动恢复 ────────────────────────────────────────
echo "═══ 3. 安全熔断（不设自动恢复）═══"
python -c "
from switchback import SwitchbackGovernor, Grade, SwitchState, NoAutoResumeError
gov = SwitchbackGovernor()
gov.admit('t7', 'test', Grade.MEDIUM)
gov.switch('t7', SwitchState.MAINLINE, actor='approver', reason='first release')
gov.pull_into_depot('t7', actor='safety', reason='test')
try:
    gov.switch('t7', SwitchState.MAINLINE, actor='x')
    raise SystemExit('FAIL: 自动恢复未被阻断')
except NoAutoResumeError:
    print('不设自动恢复熔断成立')
" 2>/dev/null && pass "不设自动恢复熔断成立" || fail "不设自动恢复被破坏"

# ── 4. K标账本哈希链 ───────────────────────────────────────
echo "═══ 4. K标账本完整性 ═══"
python -c "
from switchback import SwitchbackGovernor, KMarkerLedger, Grade, LedgerIntegrityError
ledger = KMarkerLedger()
gov = SwitchbackGovernor(ledger=ledger)
gov.admit('t10', 'test', Grade.GENTLE)
gov.seal('t10', 'K0', {'a': 1})
gov.seal('t10', 'K1', {'a': 2})
assert ledger.verify_chain(), '链校验失败'
# 篡改检测
gov.ledger.entries()[0].payload['a'] = 999
try:
    ledger.verify_chain()
    raise SystemExit('FAIL: 篡改未被检出')
except LedgerIntegrityError:
    print('篡改检测成立')
" 2>/dev/null && pass "哈希链不可篡改 + 篡改检测" || fail "账本完整性检查失败"

# ── 5. Skill 工程体系 ──────────────────────────────────────
echo "═══ 5. Skill 工程体系 ═══"
python -c "
from switchback.skills import ALL_SKILLS
required = {'name','purpose','inputs','outputs','invoke_condition','dependencies','failure_handling','safety_boundary','reuse_value'}
assert len(ALL_SKILLS) == 6, f'Skill 数应为6, 实际{len(ALL_SKILLS)}'
for spec in ALL_SKILLS.values():
    d = spec.to_dict()
    assert required.issubset(d), f'{spec.name} 字段不全'
    assert all(d[f] for f in required), f'{spec.name} 有空字段'
print('6 Skill 全部带完整 SkillSpec 声明')
" 2>/dev/null && pass "六大 Skill 声明完整" || fail "Skill 声明不完整"

# ── 6. CLI 幸福路径 ───────────────────────────────────────
echo "═══ 6. CLI 幸福路径 ═══"
python -m switchback.cli --help >/dev/null 2>&1 && pass "CLI --help 正常" || fail "CLI --help 失败"
# 子命令注册检查（审查报告 bug1：vote/seal 曾未注册）
python -m switchback.cli vote --help >/dev/null 2>&1 && pass "vote 子命令已注册" || fail "vote 子命令未注册"
python -m switchback.cli seal --help >/dev/null 2>&1 && pass "seal 子命令已注册" || fail "seal 子命令未注册"

# ── 7. 案例可复现 ──────────────────────────────────────────
echo "═══ 7. 案例可复现 ═══"
python -m switchback.cli replay jingzhang >/dev/null 2>&1 && pass "京张案例重放正常" || fail "京张案例重放失败"
python -m switchback.cli replay ops >/dev/null 2>&1 && pass "运维案例重放正常" || fail "运维案例重放失败"

# ── 诚实局限声明（借鉴 TRIO milestones.json 的 honest_limitation）────────
echo "═══ 8. 诚实局限声明 ═══"
[ -f docs/limitations.md ] && pass "limitations.md 诚实局限声明存在" || warn "无 limitations.md（建议补'本仓为协议原型，非生产中间件'声明）"

echo ""
echo "═══ 结果：✅${PASS}  ⚠️${WARN}  ❌${FAIL} ═══"
if [ "$FAIL" -gt 0 ]; then
  echo "❌ 验证失败 — 存在阻断性问题，禁止交付"
  exit 1
fi
echo "✅ 全系统验证通过 — 可交付"
exit 0
