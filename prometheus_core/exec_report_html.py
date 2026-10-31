"""Standalone, offline HTML for the Executive Import Savings Dashboard.

One file: the model built by the app (``_xr_build_model``) as embedded JSON,
the styles, and a small script that draws the charts as SVG, recomputes the
headline figures for the chosen commodity and status, and expands each
contract into its own report. Nothing is fetched from anywhere, so it opens
offline and prints to PDF from the browser.

Every headline figure is a plain sum of the contract rows shown beneath it,
the same arithmetic as ``exec_savings.kpis``; the CBOT pricing advantage is a
benchmark reported beside the savings and never added to them.
"""

from __future__ import annotations

import html
import json

EXEC_HTML_VERSION = "1.0"


def render(model):
    """The complete HTML document for ``model``."""
    data = json.dumps(model, default=str, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")          # only "</" can end a <script> early
    title = html.escape(model.get("title") or "Executive Import Savings Dashboard")
    return _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


def write(model, path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(model))
    return path


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#16243a;--muted:#5d6b7e;--line:#dfe5ee;--bg:#f3f6fa;--card:#fff;--navy:#1f3a5f;--blue:#1a6ebd;
--teal:#0f8b8d;--good:#1a7a1a;--good-bg:#e3f4e1;--bad:#b3261e;--bad-bg:#fbe3e1;--amber:#9a6b00;--amber-bg:#fff4d6}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{margin:0;font:14px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink)}
header{background:var(--navy);color:#fff;padding:22px 28px 18px}
header h1{margin:0 0 4px;font-size:24px;letter-spacing:.2px}
header p{margin:2px 0;color:#c9d6e8;font-size:13px}
main{max-width:1360px;margin:0 auto;padding:12px 16px 60px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0}
h2{font-size:17px;margin:0 0 4px;color:var(--navy)}
h2+.note{margin-bottom:10px}
.note{color:var(--muted);font-size:12.5px;margin:0}
.filters label,.chips{min-width:0}
@media (max-width:700px){.filters{position:static}.kpi .v{font-size:24px}header{padding:16px}main{padding:8px 16px 40px}select,input[type=search]{min-width:0;width:100%}}
.filters{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;background:#fff;
border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:14px 0;box-shadow:0 2px 6px rgba(0,0,0,.05)}
.filters label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:3px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--blue);background:#fff;color:var(--blue);border-radius:16px;padding:4px 12px;cursor:pointer;font:inherit;font-size:13px}
.chip.on{background:var(--blue);color:#fff}
select,input[type=search]{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;min-width:150px}
button.act{font:inherit;padding:6px 12px;border:1px solid var(--blue);background:#fff;color:var(--blue);border-radius:6px;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media (max-width:900px){.kpis{grid-template-columns:1fr}}
.kpi{border-radius:10px;padding:14px 16px;background:#fbfcfe;border:1px solid var(--line);border-top:4px solid var(--blue)}
.kpi.hist{border-top-color:var(--blue)}.kpi.pot{border-top-color:var(--teal)}.kpi.comb{border-top-color:var(--navy)}
.kpi .l{font-size:12.5px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.3px}
.kpi .v{font-size:30px;font-weight:750;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.kpi .s{font-size:12px;color:var(--muted)}
.bench{margin-top:12px;border:1px dashed #b8c4d4;border-radius:10px;padding:10px 14px;display:flex;flex-wrap:wrap;gap:8px 28px;align-items:baseline}
.bench .v{font-size:20px;font-weight:700}
.says{margin:10px 0 0;padding-left:20px}.says li{margin:3px 0}
.pos{color:var(--good)}.neg{color:var(--bad)}.na{color:var(--muted)}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
@media (max-width:900px){.grid2{grid-template-columns:minmax(0,1fr)}}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{background:var(--navy);color:#fff;text-align:left;padding:6px 7px;font-weight:600;position:sticky;top:0;white-space:nowrap;cursor:pointer}
th.n,td.n{text-align:right}
td{padding:5px 7px;border-bottom:1px solid var(--line);vertical-align:top;font-variant-numeric:tabular-nums}
tr.row{cursor:pointer}tr.row:hover td{background:#f4f8fd}
tr.tot td{font-weight:700;border-top:2px solid var(--navy);background:#f7f9fc}
tr.det td{background:#fafcff;padding:12px 14px}
.detbox{position:sticky;left:14px;width:min(1268px,calc(100vw - 110px))}
.badge{display:inline-block;border-radius:10px;padding:1px 8px;font-size:11.5px;font-weight:600;white-space:nowrap}
.b-real{background:var(--good-bg);color:var(--good)}.b-prov{background:var(--amber-bg);color:var(--amber)}
.b-open{background:#e2eefb;color:var(--blue)}.b-est{background:var(--amber-bg);color:var(--amber)}
.panels{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media (max-width:1000px){.panels{grid-template-columns:1fr 1fr}}
.panel{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:#fff}
.panel h4{margin:0 0 6px;font-size:12.5px;color:var(--navy)}
.panel dl{display:grid;grid-template-columns:auto auto;gap:2px 10px;margin:0;font-size:12px}
.panel dt{color:var(--muted)}.panel dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.assess{margin:10px 0 4px;padding:8px 12px;border-left:4px solid var(--navy);background:#fff;font-size:13px}
.legend{display:flex;gap:16px;font-size:12px;color:var(--muted);margin:4px 0}
.legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-2px}
svg text{font:11px -apple-system,"Segoe UI",Roboto,Arial,sans-serif;fill:#5d6b7e}
.rank td:first-child{color:var(--muted);width:24px}
.toggle{font-size:12px;color:var(--muted)}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:20px}
@media print{
 body{background:#fff;font-size:11px}.filters,.noprint{display:none!important}
 header{background:#fff;color:var(--ink);border-bottom:3px solid var(--navy);padding:8px 0}
 header p{color:var(--muted)} main{max-width:none;padding:0}
 section{break-inside:avoid-page;border:none;padding:6px 0;margin:8px 0}
 section.long{break-inside:auto} th{position:static} tr{break-inside:avoid}
 .kpi .v{font-size:22px} *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
</style>
</head>
<body>
<header>
 <h1 id="ttl"></h1>
 <p id="sub"></p>
 <p id="sub2"></p>
</header>
<main>
<div class="filters">
 <label>Commodity<div class="chips" id="chips"></div></label>
 <label>Contracts<select id="fStatus"><option value="ALL">All contracts</option><option value="OPEN">Open contracts</option><option value="CLOSED">Closed contracts</option></select></label>
 <label>Search<input type="search" id="fq" placeholder="contract, supplier, ID"></label>
 <label class="toggle"><span>&nbsp;</span><span><input type="checkbox" id="fneg"> Only contracts with a disadvantage</span></label>
 <label><span>&nbsp;</span><span><button class="act" id="expAll">Expand all</button> <button class="act" onclick="window.print()">Print / PDF</button></span></label>
</div>

<section id="secK">
 <h2>Management summary</h2>
 <p class="note" id="kNote"></p>
 <div class="kpis" id="kpis"></div>
 <div class="bench" id="bench"></div>
 <ol class="says" id="says"></ol>
</section>

<section>
 <h2>Historical vs open — by commodity</h2>
 <p class="note">Historical = tonnes consumed, against the local price on the day each was consumed (accounting result). Potential = tonnes not yet consumed (in stock or not yet delivered), against today's local price. Different tonnes, so they add up.</p>
 <div class="legend"><span><i style="background:var(--blue)"></i>Historical savings</span><span><i style="background:var(--teal)"></i>Open potential savings</span><span><i style="background:var(--bad)"></i>Negative (cost more than local)</span></div>
 <div id="chart"></div>
 <div class="tw"><table id="tCom"></table></div>
</section>

<section>
 <h2>Contract performance ranking</h2>
 <p class="note">Ranked on historical savings against local. <span class="noprint">Rank by <select id="rankBy"><option value="egp">total EGP</option><option value="mt">EGP per MT</option></select></span></p>
 <div class="grid2">
  <div><h3 class="pos" style="font-size:14px;margin:8px 0 4px">Highest savings</h3><div class="tw"><table class="rank" id="tTop"></table></div></div>
  <div><h3 class="neg" style="font-size:14px;margin:8px 0 4px">Financial disadvantage</h3><div class="tw"><table class="rank" id="tBot"></table></div></div>
 </div>
</section>

<section class="long">
 <h2>1 · Historical savings by contract</h2>
 <p class="note">Each day's consumption is allocated to contracts first-in, first-out and valued at that day's delivered local price (price + transport) for the contract's origin; where no price was logged that day, the latest earlier observation is used and its date is shown. Click a contract for its full report.</p>
 <div class="tw"><table id="tHist"></table></div>
</section>

<section class="long">
 <h2>2 · Open contracts vs today's local price</h2>
 <p class="note">Outstanding = contract quantity − delivered. Delivered-but-not-consumed stock is shown separately. Each tonne is counted once: consumed (section 1), in stock, or outstanding. Potential, not realized.</p>
 <div class="tw"><table id="tOpen"></table></div>
</section>

<section class="long">
 <h2>3 · CBOT pricing advantage — fixing vs CBOT during consumption</h2>
 <p class="note">Implied CBOT fixing = CIF ÷ factor − premium (CORN 0.3937; SOYBEAN, WHEAT 0.36745; SBM 1.1023); pricing lots use their recorded CBOT. Advantage per MT = (CBOT on the day consumed − fixing) × factor. Benchmark: the app's stored rolling front-month CBOT, not the contract's own futures month. This is already inside the saving against local — never added to it.</p>
 <div class="tw"><table id="tCbot"></table></div>
</section>

<section class="long">
 <h2>Data, sources and reconciliation</h2>
 <div id="src"></div>
</section>
<footer id="foot"></footer>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const M = JSON.parse(document.getElementById("data").textContent);
const C = M.contracts;
const BASES = [...new Set(C.map(c => c.base))].sort();
const S = {base: "ALL", status: "ALL", q: "", neg: false, sort: {}, open: new Set(), rank: "egp"};
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const isNum = v => typeof v === "number" && isFinite(v);
const fx = (v, d) => isNum(v) ? v.toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d}) : "—";
const n0 = v => fx(v, 0), n2 = v => fx(v, 2);
const sgn = v => !isNum(v) ? "na" : (v < 0 ? "neg" : (v > 0 ? "pos" : ""));
const cell = (v, f, colour) => `<td class="n ${colour ? sgn(v) : ""}">${(f || n0)(v)}</td>`;
const money = (cur, v) => isNum(v) ? (v < 0 ? "−" : "") + cur + " " + n0(Math.abs(v)) : "—";
const pct = v => isNum(v) ? fx(v, 1) + "%" : "—";
const sum = (rows, fn) => rows.reduce((a, r) => { const v = fn(r); return isNum(v) ? a + v : a; }, 0);
const H = c => c.history || {}, O = c => c.open || {};
const potOf = c => (O(c).stock_saving_egp || 0) + (O(c).outstanding_saving_egp || 0);
const hasPot = c => isNum(O(c).saving_egp_mt);

function filtered() {
  const q = S.q.trim().toLowerCase();
  return C.filter(c => (S.base === "ALL" || c.base === S.base)
    && (S.status === "ALL" || (S.status === "OPEN") === !!c.is_open)
    && (!q || [c.contract, c.supplier, c.id, c.commodity, c.origin].join(" ").toLowerCase().includes(q))
    && (!S.neg || (H(c).saving_egp < 0) || (hasPot(c) && potOf(c) < 0) || (H(c).adv_usd < 0)));
}

// Same arithmetic as exec_savings.commodity_rollup / kpis.
function rollup(rows) {
  const out = {};
  rows.forEach(c => { (out[c.base] = out[c.base] || []).push(c); });
  return Object.keys(out).sort().map(base => {
    const r = out[base];
    const b = {base, contracts: r.length,
      consumed_mt: sum(r, c => H(c).consumed_mt), local_priced_mt: sum(r, c => H(c).local_priced_mt),
      historical_saving_egp: sum(r, c => H(c).saving_egp),
      realized_saving_egp: sum(r, c => c.saving_kind === "Realized" ? H(c).saving_egp : null),
      provisional_saving_egp: sum(r, c => c.saving_kind !== "Realized" ? H(c).saving_egp : null),
      local_cost_egp: sum(r, c => (H(c).local_wavg || 0) * (H(c).local_priced_mt || 0)),
      in_stock_mt: sum(r, c => O(c).in_stock_mt), outstanding_mt: sum(r, c => O(c).outstanding_mt),
      stock_saving_egp: sum(r, c => O(c).stock_saving_egp), outstanding_saving_egp: sum(r, c => O(c).outstanding_saving_egp),
      cbot_adv_usd: sum(r, c => H(c).adv_usd), cbot_adv_egp: sum(r, c => H(c).adv_egp), cbot_mt: sum(r, c => H(c).cbot_mt)};
    b.historical_saving_egp_mt = b.local_priced_mt ? b.historical_saving_egp / b.local_priced_mt : null;
    b.historical_saving_pct = b.local_cost_egp ? b.historical_saving_egp / b.local_cost_egp * 100 : null;
    b.potential_saving_egp = b.stock_saving_egp + b.outstanding_saving_egp;
    return b;
  });
}
function kpis(rows, coms) {
  const s = k => sum(coms, b => b[k]);
  const hist = s("historical_saving_egp"), pot = s("potential_saving_egp"), histMt = s("local_priced_mt");
  const potMt = sum(rows, c => O(c).potential_priced_mt);
  const open = rows.filter(c => c.is_open);
  return {historical_saving_egp: hist, realized_saving_egp: s("realized_saving_egp"),
    provisional_saving_egp: s("provisional_saving_egp"), historical_priced_mt: histMt,
    potential_saving_egp: pot, stock_saving_egp: s("stock_saving_egp"), outstanding_saving_egp: s("outstanding_saving_egp"),
    potential_priced_mt: potMt, combined_benefit_egp: hist + pot,
    weighted_saving_egp_mt: (histMt + potMt) ? (hist + pot) / (histMt + potMt) : null,
    historical_saving_egp_mt: histMt ? hist / histMt : null, open_contracts: open.length,
    open_outstanding_mt: sum(open, c => O(c).outstanding_mt), open_in_stock_mt: sum(open, c => O(c).in_stock_mt),
    open_value_usd: sum(open, c => O(c).open_value_usd), open_full_value_usd: sum(open, c => c.contract_value_usd),
    cbot_adv_usd: s("cbot_adv_usd"), cbot_adv_egp: s("cbot_adv_egp"), contracts: rows.length};
}

function renderKpis(rows, coms, K) {
  window.__K = K;
  const scope = (S.base === "ALL" ? "All commodities" : S.base) + " · " + ({ALL: "all contracts", OPEN: "open contracts", CLOSED: "closed contracts"}[S.status])
    + (S.q ? ` · matching “${esc(S.q)}”` : "") + (S.neg ? " · disadvantage only" : "") + ` · ${K.contracts} contracts`;
  $("kNote").innerHTML = scope;
  const card = (cls, label, v, txt, sub) => `<div class="kpi ${cls}"><div class="l">${esc(label)}</div><div class="v ${sgn(v)}">${txt}</div><div class="s">${sub}</div></div>`;
  $("kpis").innerHTML = [
    card("hist", "Total historical savings", K.historical_saving_egp, money("EGP", K.historical_saving_egp),
      `Realized ${money("EGP", K.realized_saving_egp)} · provisional ${money("EGP", K.provisional_saving_egp)} (CIF not final)<br>${n0(K.historical_priced_mt)} MT consumed vs local on the day consumed`),
    card("pot", "Open contract potential savings", K.potential_saving_egp, money("EGP", K.potential_saving_egp),
      `In stock ${money("EGP", K.stock_saving_egp)} · outstanding ${money("EGP", K.outstanding_saving_egp)}<br>${n0(K.potential_priced_mt)} MT not yet consumed vs today's local — potential`),
    card("comb", "Combined historical + potential benefit", K.combined_benefit_egp, money("EGP", K.combined_benefit_egp),
      "Different tonnes, so the two add up · CBOT advantage not included"),
    card("pot", "Open contract outstanding quantity", K.open_outstanding_mt, n0(K.open_outstanding_mt) + " MT",
      `not yet delivered · plus ${n0(K.open_in_stock_mt)} MT delivered and still in stock`),
    card("pot", "Open contract value", K.open_full_value_usd, money("USD", K.open_full_value_usd),
      `${K.open_contracts} open contracts at contract CIF · not yet consumed ${money("USD", K.open_value_usd)}`),
    card("comb", "Weighted average savings per MT", K.weighted_saving_egp_mt, (isNum(K.weighted_saving_egp_mt) ? n0(K.weighted_saving_egp_mt) + " EGP/MT" : "—"),
      `historical alone ${isNum(K.historical_saving_egp_mt) ? n0(K.historical_saving_egp_mt) + " EGP/MT" : "—"}`)
  ].join("");
  $("bench").innerHTML = `<div><b>CBOT pricing advantage</b> <span class="note">(benchmark — already inside the savings, not added)</span></div>
    <div class="v ${sgn(K.cbot_adv_usd)}">${money("USD", K.cbot_adv_usd)}</div><div class="v ${sgn(K.cbot_adv_egp)}">${money("EGP", K.cbot_adv_egp)}</div>
    <div class="note">Fixing vs the CBOT on each day the tonnes were consumed. Positive = fixed below the market during consumption.</div>`;
  const says = [];
  says.push(`Importing instead of buying locally ${K.historical_saving_egp >= 0 ? "saved" : "cost"} <b class="${sgn(K.historical_saving_egp)}">${money("EGP", Math.abs(K.historical_saving_egp))}</b> on the tonnes already consumed (${isNum(K.historical_saving_egp_mt) ? n0(K.historical_saving_egp_mt) : "—"} EGP/MT): ${money("EGP", K.realized_saving_egp)} on final prices, ${money("EGP", K.provisional_saving_egp)} provisional.`);
  says.push(`Tonnes not yet consumed would ${K.potential_saving_egp >= 0 ? "save" : "cost"} a further <b class="${sgn(K.potential_saving_egp)}">${money("EGP", Math.abs(K.potential_saving_egp))}</b> against today's local price — a potential that moves with the market, not a realized figure.`);
  if (K.cbot_adv_usd) says.push(`Against the CBOT prevailing while the material was consumed, the fixings were ${K.cbot_adv_usd >= 0 ? "favourable" : "unfavourable"} by <b class="${sgn(K.cbot_adv_usd)}">${money("USD", Math.abs(K.cbot_adv_usd))}</b> — a timing benchmark, already reflected in the saving against local.`);
  const negs = rows.filter(c => H(c).saving_egp < 0);
  if (negs.length) says.push(`${negs.length} contract${negs.length > 1 ? "s" : ""} cost more than local on the days consumed, together ${money("EGP", sum(negs, c => H(c).saving_egp))} — listed under financial disadvantage.`);
  $("says").innerHTML = says.map(s => `<li>${s}</li>`).join("");
}

function renderChart(coms) {
  const rows = coms.filter(b => b.historical_saving_egp || b.potential_saving_egp);
  if (!rows.length) { $("chart").innerHTML = '<p class="note">Nothing to chart for this selection.</p>'; return; }
  const W = 900, L = 90, R = 130, bh = 16, gap = 14, top = 10;
  const h = top + rows.length * (2 * bh + gap) + 20;
  const vals = rows.flatMap(b => [b.historical_saving_egp, b.potential_saving_egp]);
  const mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), span = (mx - mn) || 1;
  const X = v => L + (v - mn) / span * (W - L - R);
  const short = v => { const a = Math.abs(v); return (v < 0 ? "−" : "") + (a >= 1e6 ? fx(a / 1e6, 1) + "M" : a >= 1e3 ? fx(a / 1e3, 0) + "k" : fx(a, 0)); };
  let s = `<svg viewBox="0 0 ${W} ${h}" width="100%" role="img" aria-label="Savings by commodity">`;
  s += `<line x1="${X(0)}" x2="${X(0)}" y1="${top - 4}" y2="${h - 16}" stroke="#9aa7b8"/>`;
  rows.forEach((b, i) => {
    const y = top + i * (2 * bh + gap);
    s += `<text x="${L - 8}" y="${y + bh + 4}" text-anchor="end" style="font-weight:600;fill:#16243a">${esc(b.base)}</text>`;
    [[b.historical_saving_egp, "#1a6ebd", "Historical"], [b.potential_saving_egp, "#0f8b8d", "Potential"]].forEach(([v, col, lab], j) => {
      const yy = y + j * bh, x0 = X(Math.min(0, v)), w = Math.abs(X(v) - X(0));
      s += `<rect x="${x0}" y="${yy + 1}" width="${Math.max(w, v ? 1 : 0)}" height="${bh - 3}" rx="2" fill="${v < 0 ? "#b3261e" : col}"><title>${esc(b.base)} ${lab}: EGP ${n0(v)}</title></rect>`;
      if (v) s += `<text x="${(v < 0 ? x0 : X(v)) + (v < 0 ? -4 : 4)}" y="${yy + bh - 3}" text-anchor="${v < 0 ? "end" : "start"}">${short(v)}</text>`;
    });
  });
  s += `<text x="${X(0)}" y="${h - 3}" text-anchor="middle">0</text></svg>`;
  $("chart").innerHTML = s;
}

function renderComTable(coms, K) {
  let s = `<thead><tr><th>Commodity</th><th class="n">Contracts</th><th class="n">Consumed MT</th><th class="n">Priced vs local MT</th><th class="n">Historical savings EGP</th><th class="n">of which realized</th><th class="n">of which provisional</th><th class="n">EGP/MT</th><th class="n">Savings %</th><th class="n">In stock MT</th><th class="n">Outstanding MT</th><th class="n">Potential EGP</th><th class="n">CBOT advantage USD</th></tr></thead><tbody>`;
  coms.forEach(b => {
    s += `<tr><td><b>${esc(b.base)}</b></td>${cell(b.contracts)}${cell(b.consumed_mt)}${cell(b.local_priced_mt)}${cell(b.historical_saving_egp, n0, 1)}${cell(b.realized_saving_egp, n0, 1)}${cell(b.provisional_saving_egp, n0, 1)}${cell(b.historical_saving_egp_mt, n0, 1)}<td class="n ${sgn(b.historical_saving_pct)}">${pct(b.historical_saving_pct)}</td>${cell(b.in_stock_mt)}${cell(b.outstanding_mt)}${cell(b.potential_saving_egp, n0, 1)}${cell(b.cbot_adv_usd, n0, 1)}</tr>`;
  });
  s += `<tr class="tot"><td>TOTAL</td>${cell(K.contracts)}${cell(sum(coms, b => b.consumed_mt))}${cell(K.historical_priced_mt)}${cell(K.historical_saving_egp, n0, 1)}${cell(K.realized_saving_egp, n0, 1)}${cell(K.provisional_saving_egp, n0, 1)}${cell(K.historical_saving_egp_mt, n0, 1)}<td></td>${cell(sum(coms, b => b.in_stock_mt))}${cell(sum(coms, b => b.outstanding_mt))}${cell(K.potential_saving_egp, n0, 1)}${cell(K.cbot_adv_usd, n0, 1)}</tr></tbody>`;
  $("tCom").innerHTML = s;
}

function renderRank(rows) {
  const key = S.rank === "mt" ? (c => H(c).saving_egp_mt) : (c => H(c).saving_egp);
  const priced = rows.filter(c => isNum(key(c)));
  const top = priced.filter(c => key(c) > 0).sort((a, b) => key(b) - key(a)).slice(0, 10);
  const bot = priced.filter(c => key(c) < 0).sort((a, b) => key(a) - key(b)).slice(0, 10);
  const t = list => list.length ? `<thead><tr><th>#</th><th>Contract</th><th>Commodity</th><th>Supplier</th><th class="n">Savings EGP</th><th class="n">EGP/MT</th></tr></thead><tbody>` +
    list.map((c, i) => `<tr class="row" data-goto="${esc(c.id)}"><td>${i + 1}</td><td>${esc(c.contract)}</td><td>${esc(c.commodity)}</td><td>${esc(c.supplier)}</td>${cell(H(c).saving_egp, n0, 1)}${cell(H(c).saving_egp_mt, n0, 1)}</tr>`).join("") + "</tbody>"
    : `<tbody><tr><td class="na">None in this selection.</td></tr></tbody>`;
  $("tTop").innerHTML = t(top); $("tBot").innerHTML = t(bot);
}

function kindBadge(c) {
  return c.saving_kind === "Realized" ? '<span class="badge b-real">Realized</span>' : `<span class="badge b-prov">${esc(c.saving_kind || "Provisional")}</span>`;
}
function sortRows(rows, table, cols) {
  const st = S.sort[table];
  if (!st) return rows;
  const col = cols[st.i];
  return rows.slice().sort((a, b) => {
    let x = col.v(a), y = col.v(b);
    const nx = x == null || x === "", ny = y == null || y === "";
    if (nx && ny) return 0; if (nx) return 1; if (ny) return -1;
    return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * st.dir;
  });
}
function head(table, cols) {
  const st = S.sort[table] || {};
  return "<thead><tr>" + cols.map((c, i) => `<th class="${c.n ? "n" : ""}" data-t="${table}" data-i="${i}" title="Sort">${esc(c.h)}${st.i === i ? (st.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr></thead>";
}

const HIST_COLS = [
  {h: "Commodity", v: c => c.commodity}, {h: "Contract No.", v: c => c.contract}, {h: "Supplier", v: c => c.supplier},
  {h: "Contract qty MT", n: 1, v: c => c.qty_mt}, {h: "Consumed MT", n: 1, v: c => H(c).consumed_mt},
  {h: "First consumption", v: c => H(c).first_date}, {h: "Last consumption", v: c => H(c).last_date},
  {h: "Landed EGP/MT", n: 1, v: c => H(c).landed_egp_mt}, {h: "Wtd avg local EGP/MT", n: 1, v: c => H(c).local_wavg},
  {h: "Historical savings EGP", n: 1, v: c => H(c).saving_egp}, {h: "Savings %", n: 1, v: c => H(c).saving_pct},
  {h: "EGP/MT", n: 1, v: c => H(c).saving_egp_mt}, {h: "Basis", v: c => c.saving_kind}];

function renderHist(rows) {
  const list = sortRows(rows.filter(c => H(c).consumed_mt), "hist", HIST_COLS);
  let s = head("hist", HIST_COLS) + "<tbody>";
  list.forEach(c => {
    const h = H(c);
    s += `<tr class="row" data-id="${esc(c.id)}" id="r-${esc(c.id)}"><td>${esc(c.commodity)}</td><td><b>${esc(c.contract)}</b> <span class="na">${esc(c.id)}</span></td><td>${esc(c.supplier)}</td>${cell(c.qty_mt)}${cell(h.consumed_mt)}<td>${esc(h.first_date || "—")}</td><td>${esc(h.last_date || "—")}</td>${cell(h.landed_egp_mt, n2)}${cell(h.local_wavg, n2)}${cell(h.saving_egp, n0, 1)}<td class="n ${sgn(h.saving_pct)}">${pct(h.saving_pct)}</td>${cell(h.saving_egp_mt, n0, 1)}<td>${kindBadge(c)}</td></tr>`;
    if (S.open.has(c.id)) s += `<tr class="det"><td colspan="${HIST_COLS.length}">${detail(c)}</td></tr>`;
  });
  const consumed = sum(list, c => H(c).consumed_mt), priced = sum(list, c => H(c).local_priced_mt), sav = sum(list, c => H(c).saving_egp);
  s += `<tr class="tot"><td colspan="3">TOTAL · ${list.length} contracts</td>${cell(sum(list, c => c.qty_mt))}${cell(consumed)}<td></td><td></td><td></td><td></td>${cell(sav, n0, 1)}<td></td>${cell(priced ? sav / priced : null, n0, 1)}<td></td></tr></tbody>`;
  $("tHist").innerHTML = s;
}

function dl(pairs) {
  return "<dl>" + pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("") + "</dl>";
}
function detail(c) {
  const h = H(c), o = O(c), f = c.fixing || {}, p = c.position || {};
  const overview = dl([["Contract", esc(c.contract)], ["Supplier", esc(c.supplier)], ["Commodity / origin", esc(c.commodity + (c.origin ? " · " + c.origin : ""))],
    ["Status", esc(c.status) + (c.is_open ? ' <span class="badge b-open">open</span>' : "")], ["Quantity", n0(c.qty_mt) + " MT"],
    ["Delivered / arrival", esc(c.delivery_date || "—")], ["Pricing", esc(c.pricing_status || "—") + (c.pricing_date ? " · " + esc(c.pricing_date) : "")],
    ["CIF USD/MT", n2(c.cif_usd_mt) + ` <span class="na">${esc(c.cif_basis || "")}</span>`], ["FX", fx(c.fx, 4) + ` <span class="na">${esc(c.fx_basis || "")}</span>`],
    ["Landed EGP/MT", n2(c.landed_egp_mt)], ["Contract value USD", n0(c.contract_value_usd)]]);
  const local = dl([["Consumed", n0(h.consumed_mt) + " MT over " + (h.days || 0) + " days"], ["Period", esc((h.first_date || "—") + " → " + (h.last_date || "—"))],
    ["Cost used EGP/MT", n2(h.landed_egp_mt)], ["Wtd avg local EGP/MT", n2(h.local_wavg)], ["Priced vs local", n0(h.local_priced_mt) + " MT"],
    ["No local price", n0(h.unpriced_mt) + " MT"], ["Saving EGP/MT", `<span class="${sgn(h.saving_egp_mt)}">${n2(h.saving_egp_mt)}</span>`],
    ["Total saving", `<b class="${sgn(h.saving_egp)}">${money("EGP", h.saving_egp)}</b>`], ["Savings %", pct(h.saving_pct)],
    ["Basis", kindBadge(c)]].concat(h.stale_mt ? [["Local older than 7 days", n0(h.stale_mt) + " MT"]] : []).concat(h.cost_note ? [["Note", esc(h.cost_note)]] : []));
  const cbot = isNum(f.value) ? dl([["Fixing", `${n2(f.value)} ${esc(f.unit || "")}`], ["Type", esc(f.label)], ["Source", esc(f.source)],
    ["Futures month", esc(c.futures_month || "—")], ["Premium / factor", n2(c.premium) + " / " + fx(c.factor, 4)],
    ["Possible fixing dates", (f.possible_dates || []).map(d => esc(d.date)).join(", ") || "—"],
    ["CBOT during consumption", n2(h.cbot_wavg)], ["Difference (CBOT − fixing)", `<span class="${sgn(h.cbot_diff)}">${n2(h.cbot_diff)}</span>`],
    ["Advantage USD/MT", `<span class="${sgn(h.adv_usd_mt)}">${n2(h.adv_usd_mt)}</span>`], ["Advantage", `<b class="${sgn(h.adv_usd)}">${money("USD", h.adv_usd)}</b> · ${money("EGP", h.adv_egp)}`]]
    .concat(f.flag ? [["Check", `<span class="neg">${esc(f.flag)}</span>`]] : []))
    : `<p class="note">${esc(f.flag || "No CBOT fixing for this contract.")}</p>`;
  const open = dl([["Delivered", n0(p.delivered_mt) + " MT"], ["Consumed", n0(p.consumed_mt) + " MT"], ["In stock", n0(p.in_stock_mt) + " MT"],
    ["Outstanding", n0(p.outstanding_mt) + " MT"], ["Local today EGP/MT", n2(o.local_today) + (o.local_date ? ` <span class="na">${esc(o.local_key)} · ${esc(o.local_date)}</span>` : "")],
    ["Landed today EGP/MT", n2(o.landed_today)], ["Potential EGP/MT", `<span class="${sgn(o.saving_egp_mt)}">${n2(o.saving_egp_mt)}</span>`],
    ["Potential EGP", (p.in_stock_mt + p.outstanding_mt) > 0 ? `<b class="${sgn(potOf(c))}">${money("EGP", potOf(c))}</b>` : "—"]]);
  return `<div class="detbox"><div class="panels"><div class="panel"><h4>Contract overview</h4>${overview}</div><div class="panel"><h4>Savings vs local market</h4>${local}</div>
    <div class="panel"><h4>CBOT pricing advantage</h4>${cbot}</div><div class="panel"><h4>Open position</h4>${open}</div></div>
    ${dailyChart(c)}<div class="assess"><b>Final assessment.</b> ${esc(c.assessment || "")}</div></div>`;
}
function dailyChart(c) {
  const d = (H(c).daily || []).filter(x => isNum(x.local) && isNum(x.cost));
  if (d.length < 2) return "";
  const W = 1200, Hh = 170, L = 60, R = 16, T = 10, B = 24;
  const ys = d.flatMap(x => [x.local, x.cost]); const mn = Math.min(...ys), mx = Math.max(...ys), sp = (mx - mn) || 1;
  const X = i => L + i / (d.length - 1) * (W - L - R), Y = v => T + (1 - (v - mn) / sp) * (Hh - T - B);
  const line = (fn, col) => `<polyline fill="none" stroke="${col}" stroke-width="2" points="${d.map((x, i) => X(i).toFixed(1) + "," + Y(fn(x)).toFixed(1)).join(" ")}"/>`;
  return `<div class="legend"><span><i style="background:#1a7a1a"></i>Local price on the day (EGP/MT)</span><span><i style="background:#1f3a5f"></i>Contract landed cost</span><span>${d.length} consumption days</span></div>
    <svg viewBox="0 0 ${W} ${Hh}" width="100%" role="img" aria-label="Local price vs landed cost"><text x="${L - 6}" y="${Y(mx) + 4}" text-anchor="end">${n0(mx)}</text><text x="${L - 6}" y="${Y(mn) + 4}" text-anchor="end">${n0(mn)}</text>
    ${line(x => x.cost, "#1f3a5f")}${line(x => x.local, "#1a7a1a")}<text x="${L}" y="${Hh - 6}">${esc(d[0].date)}</text><text x="${W - R}" y="${Hh - 6}" text-anchor="end">${esc(d[d.length - 1].date)}</text></svg>`;
}

const OPEN_COLS = [
  {h: "Commodity", v: c => c.commodity}, {h: "Contract No.", v: c => c.contract}, {h: "Supplier", v: c => c.supplier},
  {h: "Open?", v: c => c.is_open ? "Yes" : "No"}, {h: "Contract MT", n: 1, v: c => c.qty_mt}, {h: "Delivered MT", n: 1, v: c => c.position.delivered_mt},
  {h: "In stock MT", n: 1, v: c => c.position.in_stock_mt}, {h: "Outstanding MT", n: 1, v: c => c.position.outstanding_mt},
  {h: "CIF USD/MT", n: 1, v: c => c.cif_usd_mt}, {h: "Landed today EGP/MT", n: 1, v: c => O(c).landed_today},
  {h: "Local today EGP/MT", n: 1, v: c => O(c).local_today}, {h: "Local observed", v: c => O(c).local_date},
  {h: "Potential EGP/MT", n: 1, v: c => O(c).saving_egp_mt}, {h: "Potential EGP", n: 1, v: c => hasPot(c) ? potOf(c) : null},
  {h: "Arrival", v: c => c.delivery_date}, {h: "Pricing", v: c => c.pricing_status}, {h: "CIF / FX", v: c => (c.cif_basis || "") + " / " + (c.fx_basis || "")}];
function renderOpen(rows) {
  const list = sortRows(rows.filter(c => c.is_open || (O(c).in_stock_mt + O(c).outstanding_mt) > 0), "open", OPEN_COLS);
  let s = head("open", OPEN_COLS) + "<tbody>";
  if (!list.length) s += `<tr><td colspan="${OPEN_COLS.length}" class="na">No open contracts or stock in this selection.</td></tr>`;
  list.forEach(c => {
    const o = O(c), p = c.position;
    const est = !/fixed/i.test(c.cif_basis || "") ? ' <span class="badge b-est">estimate</span>' : "";
    s += `<tr class="row" data-goto="${esc(c.id)}"><td>${esc(c.commodity)}</td><td><b>${esc(c.contract)}</b> <span class="na">${esc(c.id)}</span></td><td>${esc(c.supplier)}</td><td>${c.is_open ? '<span class="badge b-open">Yes</span>' : "No"}</td>${cell(c.qty_mt)}${cell(p.delivered_mt)}${cell(p.in_stock_mt)}${cell(p.outstanding_mt)}${cell(c.cif_usd_mt, n2)}${cell(o.landed_today, n2)}${cell(o.local_today, n2)}<td>${esc(o.local_date || "—")} <span class="na">${esc(o.local_key || "")}</span></td>${cell(o.saving_egp_mt, n2, 1)}${cell(hasPot(c) ? potOf(c) : null, n0, 1)}<td>${esc(c.delivery_date || "—")}</td><td>${esc(c.pricing_status || "")}</td><td>${esc(c.cif_basis || "")}${est} / ${esc(c.fx_basis || "")}</td></tr>`;
  });
  s += `<tr class="tot"><td colspan="4">TOTAL · ${list.length}</td>${cell(sum(list, c => c.qty_mt))}${cell(sum(list, c => c.position.delivered_mt))}${cell(sum(list, c => c.position.in_stock_mt))}${cell(sum(list, c => c.position.outstanding_mt))}<td colspan="5"></td>${cell(sum(list, c => hasPot(c) ? potOf(c) : null), n0, 1)}<td colspan="3"></td></tr></tbody>`;
  $("tOpen").innerHTML = s;
}

const CBOT_COLS = [
  {h: "Commodity", v: c => c.commodity}, {h: "Contract No.", v: c => c.contract}, {h: "Fixing type", v: c => c.fixing.label},
  {h: "Futures month", v: c => c.futures_month}, {h: "Pricing date", v: c => c.pricing_date}, {h: "CBOT fixing", n: 1, v: c => c.fixing.value},
  {h: "Possible fixing dates", v: c => (c.fixing.possible_dates || []).map(d => d.date).join(", ")},
  {h: "Consumed MT with CBOT", n: 1, v: c => H(c).cbot_mt}, {h: "Wtd avg CBOT in consumption", n: 1, v: c => H(c).cbot_wavg},
  {h: "Difference", n: 1, v: c => H(c).cbot_diff}, {h: "Advantage USD/MT", n: 1, v: c => H(c).adv_usd_mt},
  {h: "Advantage USD", n: 1, v: c => H(c).adv_usd}, {h: "Advantage EGP", n: 1, v: c => H(c).adv_egp}];
function renderCbot(rows) {
  const list = sortRows(rows.filter(c => c.fixing && isNum(c.fixing.value)), "cbot", CBOT_COLS);
  let s = head("cbot", CBOT_COLS) + "<tbody>";
  if (!list.length) s += `<tr><td colspan="${CBOT_COLS.length}" class="na">No CBOT-priced contracts in this selection (flat-price contracts have no CBOT fixing).</td></tr>`;
  list.forEach(c => {
    const h = H(c), f = c.fixing;
    s += `<tr class="row" data-goto="${esc(c.id)}"><td>${esc(c.commodity)}</td><td><b>${esc(c.contract)}</b> <span class="na">${esc(c.id)}</span></td><td>${esc(f.label)}${f.flag ? ` <span class="neg" title="${esc(f.flag)}">⚠</span>` : ""}</td><td>${esc(c.futures_month || "—")}</td><td>${esc(c.pricing_date || "—")}</td>${cell(f.value, n2)}<td>${esc((f.possible_dates || []).map(d => d.date).join(", ") || "—")}</td>${cell(h.cbot_mt)}${cell(h.cbot_wavg, n2)}${cell(h.cbot_diff, n2, 1)}${cell(h.adv_usd_mt, n2, 1)}${cell(h.adv_usd, n0, 1)}${cell(h.adv_egp, n0, 1)}</tr>`;
  });
  const mt = sum(list, c => H(c).cbot_mt), usd = sum(list, c => H(c).adv_usd);
  s += `<tr class="tot"><td colspan="7">TOTAL · ${list.length}</td>${cell(mt)}<td></td><td></td>${cell(mt ? usd / mt : null, n2, 1)}${cell(usd, n0, 1)}${cell(sum(list, c => H(c).adv_egp), n0, 1)}</tr></tbody>`;
  $("tCbot").innerHTML = s;
}

function renderSources() {
  const src = M.sources || {};
  const kv = o => Object.entries(o || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(Array.isArray(v) ? v.join(" · ") : v)}</td></tr>`).join("");
  let s = `<div class="grid2"><div><h3>Calculation method</h3><ul class="note">
   <li>Historical saving per day = (local price on the consumption date − contract landed cost) × tonnes consumed that day from the contract (FIFO).</li>
   <li>Local price = the origin's delivered local price (price + transport); when none was logged that day, the latest earlier observation, with its date. No earlier observation → that tonnage is left unpriced, never estimated.</li>
   <li>Landed cost = CIF × FX + discharge + clearance + inland freight. FX: Form 4 once entered (all commodities except SBM), else delivery FX.</li>
   <li>Realized = final CIF; provisional = CIF not yet final (unpriced / partially priced).</li>
   <li>Potential = (today's local − landed cost today) × (in-stock + outstanding tonnes).</li>
   <li>CBOT advantage = (CBOT on each consumption day − contract fixing) × factor × tonnes. Days with one-day stray prints step back to the last valid day.</li></ul></div>
   <div><h3>Sources and dates</h3><table><tbody>
   <tr><td>Data as of</td><td>${esc(M.as_of)}</td></tr><tr><td>Generated</td><td>${esc(M.generated)}</td></tr>
   ${Object.entries(src.local_latest || {}).map(([k, v]) => `<tr><td>Latest local price — ${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}
   ${Object.entries(src.cbot || {}).map(([k, v]) => `<tr><td>CBOT history — ${esc(k)}</td><td>${esc(Array.isArray(v) ? `${v[0]} → ${v[1]} (${v[2]} days)` : v)}</td></tr>`).join("")}
   <tr><td>FX history</td><td>${esc(Array.isArray(src.fx) ? src.fx.join(" → ") : src.fx || "—")}</td></tr>
   ${Object.entries(src.rates || {}).map(([k, v]) => `<tr><td>Daily consumption rate — ${esc(k)}</td><td>${n0(v)} MT/day</td></tr>`).join("")}
   ${Object.entries(src.spikes || {}).map(([k, v]) => `<tr><td>One-day CBOT spikes stepped over — ${esc(k)}</td><td>${n0(v)}</td></tr>`).join("")}
   </tbody></table></div></div>`;
  const rec = M.reconciliation || [];
  if (rec.length) {
    s += `<h3>Quantity reconciliation — consumption by source</h3><div class="tw"><table><thead><tr><th>Commodity</th><th>Mode</th><th class="n">Consumed MT</th><th class="n">From imports MT</th><th class="n">From local purchases MT</th><th class="n">Unsourced MT</th><th class="n">Stock MT</th><th class="n">Counted MT</th></tr></thead><tbody>` +
      rec.map(r => `<tr><td>${esc(r.base)}</td><td>${esc(r.mode)}${r.daily_rate ? " · " + n0(r.daily_rate) + " MT/day" : ""}</td>${cell(r.consumed_mt)}${cell(r.import_mt)}${cell(r.local_purchase_mt)}${cell(r.unsourced_mt)}${cell(r.stock_mt)}${cell(r.counted_mt)}</tr>`).join("") +
      `</tbody></table></div><p class="note">Unsourced = consumption at the daily rate on days when no import or local lot was in stock; it is not valued and not counted as savings.</p>`;
  }
  const unrec = C.filter(c => Math.abs((c.position || {}).unreconciled_mt || 0) > 0.01);
  s += `<h3>Checks</h3><ul class="note"><li>${C.length} contracts after removing ${(M.dropped || []).length} exact duplicate${(M.dropped || []).length === 1 ? "" : "s"}${(M.dropped || []).length ? ": " + esc(M.dropped.map(d => d.id || d).join(", ")) : ""}.</li>
   <li>${unrec.length ? `<span class="neg">${unrec.length} contracts where delivered ≠ consumed + in stock: ${esc(unrec.map(c => c.id).join(", "))}</span>` : "Every contract: delivered = consumed + in stock (no tonne counted twice)."}</li>
   ${(M.look_alikes || []).map(l => `<li>Look-alike records kept: ${esc(l.ids.join(" / "))} (${esc(l.contract)}) — ${esc(l.note)}</li>`).join("")}
   <li>Sum of contract historical savings = ${money("EGP", sum(C, c => H(c).saving_egp))}; headline figure = ${money("EGP", M.kpis.historical_saving_egp)}.</li></ul>`;
  $("src").innerHTML = s;
}

function render() {
  const rows = filtered(), coms = rollup(rows), K = kpis(rows, coms);
  renderKpis(rows, coms, K); renderChart(coms); renderComTable(coms, K); renderRank(rows);
  renderHist(rows); renderOpen(rows); renderCbot(rows);
}

$("ttl").textContent = M.title || "Executive Import Savings Dashboard";
const latest = Object.values((M.sources || {}).local_latest || {}).sort().pop() || "—";
$("sub").textContent = `Data as of ${M.as_of} · latest local price ${latest} · generated ${M.generated} · ${C.length} contracts`;
$("sub2").textContent = "Historical savings are realized against the local market on the days consumed; open-contract savings are potential at today's local price; the CBOT advantage is a benchmark and is never added to either.";
$("foot").textContent = `${M.app || "Prometheus"} · executive savings model ${M.version || ""} · offline report`;
$("chips").innerHTML = ["ALL"].concat(BASES).map(b => `<button class="chip${b === "ALL" ? " on" : ""}" data-b="${esc(b)}">${b === "ALL" ? "All" : esc(b)}</button>`).join("");
$("chips").addEventListener("click", e => { const b = e.target.closest(".chip"); if (!b) return; S.base = b.dataset.b;
  document.querySelectorAll(".chip").forEach(x => x.classList.toggle("on", x === b)); render(); });
$("fStatus").addEventListener("change", e => { S.status = e.target.value; render(); });
$("fq").addEventListener("input", e => { S.q = e.target.value; render(); });
$("fneg").addEventListener("change", e => { S.neg = e.target.checked; render(); });
$("rankBy").addEventListener("change", e => { S.rank = e.target.value; render(); });
$("expAll").addEventListener("click", () => { const rows = filtered().filter(c => H(c).consumed_mt);
  const all = rows.every(c => S.open.has(c.id)); rows.forEach(c => all ? S.open.delete(c.id) : S.open.add(c.id));
  $("expAll").textContent = all ? "Expand all" : "Collapse all"; renderHist(filtered()); });
document.addEventListener("click", e => {
  const th = e.target.closest("th[data-t]");
  if (th) { const t = th.dataset.t, i = +th.dataset.i, cur = S.sort[t]; S.sort[t] = {i, dir: cur && cur.i === i ? -cur.dir : -1}; render(); return; }
  const row = e.target.closest("tr.row");
  if (!row) return;
  if (row.dataset.id) { S.open.has(row.dataset.id) ? S.open.delete(row.dataset.id) : S.open.add(row.dataset.id); renderHist(filtered()); return; }
  const id = row.dataset.goto, c = C.find(x => x.id === id);
  if (c && H(c).consumed_mt) { S.open.add(id); renderHist(filtered()); const el = $("r-" + id); if (el) el.scrollIntoView({behavior: "smooth", block: "center"}); }
});
renderSources();
render();
</script>
</body>
</html>
"""
