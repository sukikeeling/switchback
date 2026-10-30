"""Human Governor WebUI Cockpit (人类总指挥台).

Provides the interactive human-in-the-loop governance cockpit required for:
  * Visualizing the 3 Switch States (MAINLINE / SIDING / DEPOT) and exploration budgets
  * Reviewing anomalous branches & millisecond causal trace trees
  * Dual-Signature Parameter Patching & Release (`G-GOVERNOR` + Human Governor)
  * One-Click Time Machine Rollback (`rollback_to_km`) with Merkle proof verification
  * IM Governance Card generation for Matrix / Webhook notifications
"""

from __future__ import annotations

import json
from typing import Any

from .sidecar import SwitchbackSidecarGateway


def build_cockpit_overview(gateway: SwitchbackSidecarGateway) -> dict[str, Any]:
    """Build real-time snapshot for the Human Governor WebUI Cockpit."""
    gov = gateway.governor
    tasks = [t.to_dict() for t in gov.tasks()]
    entries = [m.to_dict() for m in gov.ledger.entries()]
    return {
        "schema": "switchback.cockpit.overview/v1",
        "merkle_root": gov.ledger.merkle_root(),
        "chain_integrity": gov.ledger.verify_chain(),
        "tasks_count": len(tasks),
        "tasks": tasks,
        "km_count": len(entries),
        "ledger": entries[-30:],
        "causal_tree": gov.tracer.build_causal_tree(),
        "counters": gov.tracer.counters(),
    }


def format_im_card(
    task_id: str,
    violation_kind: str,
    target_state: str,
    merkle_root: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a structured Human-in-the-Loop IM governance card (Matrix / Webhook)."""
    return {
        "card_type": "switchback.human_governor_card/v1",
        "header": {
            "title": f"🚨 Switchback 道岔告警 · {task_id} -> {target_state.upper()}",
            "template": "red" if target_state == "depot" else "orange",
        },
        "body": {
            "task_id": task_id,
            "violation_kind": violation_kind,
            "target_state": target_state,
            "auto_resume": "DISABLED (物理拔除自动续行)",
            "merkle_root": merkle_root,
            "details": details or {},
        },
        "actions": [
            {"action": "intervene_dual_sign", "label": "✍️ 注入修正参数并双签放行 (MAINLINE)"},
            {"action": "time_machine_rollback", "label": "⏪ 时光机回溯至上一 K 标"},
            {"action": "keep_depot_locked", "label": "🔒 维持入段检修锁定 (DEPOT)"},
        ],
    }


def render_cockpit_html(gateway: SwitchbackSidecarGateway) -> str:
    """Render the self-contained Human Governor WebUI Cockpit HTML."""
    overview = build_cockpit_overview(gateway)
    initial_json = json.dumps(overview, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Switchback 人类总指挥台 · Human Governor WebUI Cockpit</title>
<style>
  :root {{
    --bg:#081523; --panel:#0f243a; --line:#1f4062; --ink:#e6f0fa;
    --muted:#8aa4be; --green:#2ecc71; --amber:#f39c12; --red:#e74c3c; --gold:#d4ac0d;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"Segoe UI","PingFang SC",sans-serif; background:var(--bg); color:var(--ink); padding:20px; line-height:1.6; }}
  .wrap {{ max-width:1200px; margin:0 auto; }}
  header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid var(--line); padding-bottom:14px; margin-bottom:20px; }}
  h1 {{ font-size:24px; color:#fff; }}
  .badge {{ background:var(--line); color:var(--gold); padding:4px 12px; border-radius:14px; font-family:Consolas,monospace; font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
  .card h2 {{ font-size:16px; color:var(--gold); margin-bottom:10px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; font-family:Consolas,monospace; }}
  th, td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; }}
  th {{ background:#14304d; color:#fff; }}
  .st-mainline {{ color:var(--green); font-weight:700; }}
  .st-siding {{ color:var(--amber); font-weight:700; }}
  .st-depot {{ color:var(--red); font-weight:700; }}
  button {{ background:#173a5e; color:#fff; border:1px solid var(--gold); padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px; margin:4px 4px 4px 0; }}
  button:hover {{ background:var(--gold); color:#000; }}
  input, textarea {{ width:100%; background:#081523; color:#fff; border:1px solid var(--line); padding:6px; border-radius:4px; font-family:Consolas,monospace; font-size:12px; margin:4px 0; }}
  pre {{ background:#050e18; padding:10px; border-radius:6px; font-family:Consolas,monospace; font-size:12px; max-height:220px; overflow:auto; color:#9ad1ff; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>🛤️ Switchback · 人类总指挥台 (Human Governor WebUI Cockpit)</h1>
      <div style="color:var(--muted);font-size:13px;">到站必停 · 三方复核 · 物理拔除自动续行 · 监理 Agent 与人类双签放行</div>
    </div>
    <div class="badge" id="merkleBadge">Merkle Root: Loading...</div>
  </header>

  <div class="grid">
    <div class="card">
      <h2>① 轨道拓扑与道岔三态监控 (Switch States & Exploration Budget)</h2>
      <table>
        <thead><tr><th>Task ID</th><th>坡度</th><th>道岔状态</th><th>探索预算</th><th>折返次数</th><th>双签</th></tr></thead>
        <tbody id="taskRows"></tbody>
      </table>
      <div style="margin-top:10px;">
        <button onclick="simIntercept('pass')">🟢 模拟正常流量放行</button>
        <button onclick="simIntercept('numeric_drift')">🟠 模拟三处数值不齐 (折返 SIDING)</button>
        <button onclick="simIntercept('secret_leak')">🔴 模拟密钥泄漏/删表 (锁死 DEPOT)</button>
      </div>
    </div>

    <div class="card">
      <h2>② 异态分支审查 · 人类与监理双签注入台 (Dual-Signature Release)</h2>
      <label>目标任务 Task ID:</label>
      <input id="inpTask" value="live-task-01">
      <label>人类总指挥签名 (Human Governor):</label>
      <input id="inpHuman" value="sukikeeling-governor">
      <label>注入修正参数 (JSON Patch):</label>
      <textarea id="inpPatch" rows="2">{{"migration_mode":"expand_contract_safe","human_approved":true}}</textarea>
      <button onclick="doIntervene()">✍️ 监理 Agent + 人类双签放行回正线 (MAINLINE)</button>
      <button onclick="doRollback()">⏪ 一键时光机回溯至 K0</button>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>③ K 标 Merkle 证据链账本 (K-Marker Immutable Ledger)</h2>
      <table>
        <thead><tr><th>K标</th><th>任务</th><th>标签</th><th>SHA-256</th><th>前链</th></tr></thead>
        <tbody id="kmRows"></tbody>
      </table>
    </div>
    <div class="card">
      <h2>④ 毫秒级决策因果 Trace (OTel / OTLP Causal Stream)</h2>
      <pre id="traceBox"></pre>
    </div>
  </div>
</div>

<script>
let DATA = {initial_json};

function render(d) {{
  document.getElementById('merkleBadge').textContent = 'Merkle Root: ' + (d.merkle_root ? d.merkle_root.slice(0, 20) + '…' : 'EMPTY');
  const tbody = document.getElementById('taskRows');
  tbody.innerHTML = (d.tasks || []).map(t => `
    <tr>
      <td>${{t.task_id}}</td>
      <td>${{t.grade}}</td>
      <td class="st-${{t.state}}">${{t.state.toUpperCase()}}</td>
      <td>${{t.exploration_budget}}</td>
      <td>${{t.turn_back_count}}</td>
      <td>${{t.human_cosigned ? '✅已双签' : '-'}}</td>
    </tr>`).join('');
  const kmBody = document.getElementById('kmRows');
  kmBody.innerHTML = (d.ledger || []).slice().reverse().map(m => `
    <tr>
      <td>K${{m.km}}</td>
      <td>${{m.task_id}}</td>
      <td>${{m.label}}</td>
      <td>${{m.sha256.slice(0, 14)}}…</td>
      <td>${{m.prev_sha ? m.prev_sha.slice(0, 10) + '…' : '-'}}</td>
    </tr>`).join('');
  document.getElementById('traceBox').textContent = JSON.stringify(d.causal_tree, null, 2);
}}

async function refresh() {{
  const r = await fetch('/api/overview');
  DATA = await r.json();
  render(DATA);
}}

async function simIntercept(mode) {{
  const taskId = document.getElementById('inpTask').value || 'live-task-01';
  let body = {{ task_id: taskId, actor: 'W-CREATE', tool: 'artifact.publish', payload: {{ impact: 0.8 }} }};
  if (mode === 'numeric_drift') {{
    body.payload = {{
      prose_text: 'score: 84 source:S1',
      table_data: '| score | 84 |',
      api_payload: {{ score: 70 }},
      claims: {{ cite: 'source:S1' }},
      sources: {{ S1: 'official' }},
      numeric_keys: ['score']
    }};
  }} else if (mode === 'secret_leak') {{
    body.payload = {{ sql: 'DROP COLUMN user_balance;', token: 'ghp_1234567890abcdefghijklmnopqrstuv' }};
  }}
  await fetch('/v1/govern/intercept', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body) }});
  await refresh();
}}

async function doIntervene() {{
  const taskId = document.getElementById('inpTask').value;
  const human = document.getElementById('inpHuman').value;
  const patch = JSON.parse(document.getElementById('inpPatch').value || '{{}}');
  await fetch('/api/intervene', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ task_id: taskId, human_actor: human, governor_actor: 'G-GOVERNOR', patched_payload: patch }})
  }});
  await refresh();
}}

async function doRollback() {{
  const taskId = document.getElementById('inpTask').value;
  await fetch('/api/rollback', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ task_id: taskId, target_km: 0, actor: document.getElementById('inpHuman').value }})
  }});
  await refresh();
}}

render(DATA);
</script>
</body>
</html>"""
