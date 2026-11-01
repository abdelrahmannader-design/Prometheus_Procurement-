"""Standalone, offline management dashboard for the procurement savings report.

One HTML file: the ``mgmt_report`` model as embedded JSON, the styles, and a
script that draws every chart as SVG, recomputes the headline figures for
the chosen filters, expands each contract, exports the filtered view to a
real .xlsx file and prints. Nothing is fetched from anywhere.

The headline figures are sums of the same rows the Excel workbook holds,
with the same checksum printed in both, so the two exports can be checked
against each other at a glance.
"""

from __future__ import annotations

import html
import json

EXEC_HTML_VERSION = "2.0"


def render(model):
    """The complete HTML document for ``model``."""
    slim = {k: v for k, v in model.items() if k not in ("local_obs",) and not k.startswith("_")}
    data = json.dumps(slim, default=str, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")          # only "</" can end a <script> early
    title = html.escape(model.get("title") or "Procurement Savings — Management Report")
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
:root{color-scheme:light;--page:#f4f5f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--line:rgba(11,11,11,.10);--navy:#1f3a5f;--s1:#2a78d6;--s2:#eb6834;--good:#0ca30c;--good-ink:#006300;--bad:#d03b3b;--bad-ink:#b3261e;
--warn:#fab219;--warn-ink:#8a5a00;--chip:#eef1f5;--good-bg:rgba(12,163,12,.10);--bad-bg:rgba(208,59,59,.10);--warn-bg:rgba(250,178,25,.16);--hover:#f1f5fb}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--line:rgba(255,255,255,.10);--navy:#9cc3f5;--s1:#3987e5;--s2:#d95926;--good-ink:#0ca30c;--bad-ink:#e66767;--warn-ink:#fab219;
--chip:#26262a;--hover:#22252b}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--line:rgba(255,255,255,.10);--navy:#9cc3f5;--s1:#3987e5;--s2:#d95926;--good-ink:#0ca30c;--bad-ink:#e66767;--warn-ink:#fab219;--chip:#26262a;--hover:#22252b}
*{box-sizing:border-box}
html,body{background:var(--page)}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink)}
header{padding:20px 24px 8px;max-width:1440px;margin:0 auto}
header h1{margin:0;font-size:22px;letter-spacing:.1px}
header .meta{color:var(--ink2);font-size:12.5px;margin-top:4px}
.badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600;cursor:pointer;border:0}
.badge.ok{background:var(--good-bg);color:var(--good-ink)}.badge.no{background:var(--bad-bg);color:var(--bad-ink)}
.tag{display:inline-block;border-radius:6px;padding:1px 7px;font-size:11px;font-weight:600;background:var(--chip);color:var(--ink2);white-space:nowrap}
.tag.act{background:rgba(42,120,214,.12);color:var(--s1)}.tag.pot{background:var(--warn-bg);color:var(--warn-ink)}.tag.ben{background:var(--chip);color:var(--ink2)}
.tag.good{background:var(--good-bg);color:var(--good-ink)}.tag.bad{background:var(--bad-bg);color:var(--bad-ink)}
nav{max-width:1440px;margin:0 auto;padding:0 24px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.tab{border:1px solid var(--line);background:var(--surface);color:var(--ink2);border-radius:8px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}
.tab.on{background:var(--navy);color:var(--surface);border-color:var(--navy)}
.spacer{flex:1}
.btn{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer}
.btn.primary{background:var(--s1);color:#fff;border-color:var(--s1)}
.filters{position:sticky;top:0;z-index:20;max-width:1440px;margin:10px auto 0;padding:10px 24px;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;background:var(--page);border-bottom:1px solid var(--line)}
.filters label{display:flex;flex-direction:column;gap:3px;font-size:11.5px;color:var(--ink2)}
.filters select,.filters input{font:inherit;font-size:13px;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);min-width:120px;max-width:190px}
main{max-width:1440px;margin:0 auto;padding:6px 24px 60px}
.panel{display:none}.panel.on{display:block}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0}
.card h2{margin:0 0 2px;font-size:16px}.card .sub{color:var(--ink2);font-size:12.5px;margin:0 0 12px}
.kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.kpis{grid-template-columns:minmax(0,1fr)}header,nav,main,.filters{padding-left:16px;padding-right:16px}}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .l{font-size:12.5px;color:var(--ink2);display:flex;justify-content:space-between;gap:8px;align-items:center}
.kpi .v{font-size:28px;font-weight:700;margin:6px 0 2px}
.kpi .s{font-size:12px;color:var(--ink2)}
.pos{color:var(--good-ink)}.neg{color:var(--bad-ink)}.na{color:var(--muted)}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
@media(max-width:1000px){.grid2{grid-template-columns:minmax(0,1fr)}}
.says{margin:0;padding-left:20px}.says li{margin:4px 0}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{text-align:left;font-weight:600;color:var(--ink2);padding:7px 8px;border-bottom:1px solid var(--axis);white-space:nowrap;cursor:pointer;position:sticky;top:0;background:var(--surface)}
td{padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th.n,td.n{text-align:right;font-variant-numeric:tabular-nums}
#tO td,#tCP td,#tC td,#svT td,#svCom td{white-space:nowrap}
tr.row{cursor:pointer}tr.row:hover td{background:var(--hover)}
tr.det>td{background:var(--page);padding:14px}
tr.tot td{font-weight:700;border-top:2px solid var(--axis)}
.panels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
@media(max-width:1100px){.panels{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.panels{grid-template-columns:minmax(0,1fr)}}
.pn{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.pn h4{margin:0 0 6px;font-size:12.5px}
.pn dl{display:grid;grid-template-columns:auto auto;gap:2px 10px;margin:0;font-size:12px}
.pn dt{color:var(--ink2)}.pn dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.assess{margin-top:10px;padding:10px 12px;border-left:3px solid var(--s1);background:var(--surface);border-radius:0 8px 8px 0;font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink2);margin:4px 0 6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
svg text{font:11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--muted)}
svg .lbl{fill:var(--ink2)}
.tip{position:fixed;z-index:50;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--line);box-shadow:0 6px 18px rgba(0,0,0,.18);
border-radius:8px;padding:8px 10px;font-size:12px;max-width:300px;display:none}
.tip b{font-weight:600}
.dq{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
@media(max-width:1000px){.dq{grid-template-columns:repeat(2,minmax(0,1fr))}}
.dq button{text-align:left;font:inherit;color:inherit;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer}
.dq button .v{font-size:20px;font-weight:700}.dq button .l{font-size:12px;color:var(--ink2)}
.dq button.on{outline:2px solid var(--s1)}
.check{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--grid);font-size:13px}
.check .r{font-weight:700;min-width:44px}
.note{color:var(--ink2);font-size:12px}
select.ctl{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink)}
body.mgmt .tech{display:none!important}
body.mgmt .filters{display:none}
body.mgmt .mgmt-only{display:block!important}
.mgmt-only{display:none}
@media print{
 body{background:#fff}nav,.filters,.btn,.noprint{display:none!important}
 .panel{display:block!important}.tech-print-hide{display:none!important}
 .card,.kpi{break-inside:avoid;border-color:#ccc}
 main{max-width:none;padding:0}header{padding:0 0 6px}
 *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
 body.mgmt .panel:not(#p-overview):not(#p-savings):not(#p-open):not(#p-trends){display:none!important}
}
</style>
</head>
<body>
<header>
 <h1 id="ttl"></h1>
 <div class="meta" id="meta"></div>
 <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;align-items:center" id="badges"></div>
</header>
<nav>
 <button class="tab on" data-p="overview">Overview</button>
 <button class="tab" data-p="savings">Savings vs local</button>
 <button class="tab" data-p="contracts">Contracts</button>
 <button class="tab" data-p="cbot">CBOT fixed vs consumption</button>
 <button class="tab" data-p="open">Open contracts vs local</button>
 <button class="tab" data-p="trends">Trends &amp; breakdowns</button>
 <button class="tab tech" data-p="quality">Data quality</button>
 <span class="spacer"></span>
 <button class="btn primary" id="bMgmt">Management View</button>
 <button class="btn" id="bTheme" title="Switch dark / light">Dark / light</button>
 <button class="btn tech" id="bXlsx">Export view to Excel</button>
 <button class="btn" onclick="window.print()">Print / PDF</button>
</nav>
<div class="filters" id="filters">
 <label>Commodity<select id="fBase"></select></label>
 <label>Origin<select id="fOrigin"></select></label>
 <label>Supplier<select id="fSupplier"></select></label>
 <label>Contract<input id="fQ" list="dlC" placeholder="number or ID"><datalist id="dlC"></datalist></label>
 <label>From<input type="date" id="fFrom"></label>
 <label>To<input type="date" id="fTo"></label>
 <label>Period<select id="fPreset"><option value="">All dates</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="ytd">Year to date</option></select></label>
 <label>Status<select id="fOpen"><option value="">Open &amp; closed</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
 <label>CBOT fixing<select id="fFix"><option value="">All</option><option value="Recorded">Fixed — recorded lots</option><option value="Implied">Fixed — implied</option><option value="Not fixed">Not fixed (unpriced)</option><option value="other">Flat / not eligible</option></select></label>
 <label>Data quality<select id="fDQ"><option value="">All supported rows</option><option value="final">Final CIF only</option><option value="prov">Provisional CIF only</option><option value="same">Same-day local quote</option><option value="carry">Carried forward ≤ 7 d</option><option value="stale">Stale reference (8–30 d)</option></select></label>
 <button class="btn" id="bReset">Reset</button>
</div>
<main>
<section class="panel on" id="p-overview">
 <div class="kpis" id="kpis"></div>
 <div class="card mgmt-only" id="mgmtNote"></div>
 <div class="card"><h2>What this says</h2><ol class="says" id="says"></ol></div>
 <div class="grid2">
  <div class="card"><h2>Historical savings vs local, by commodity</h2><p class="sub">Consumed tonnes against the local price observed on the day · EGP</p><div id="chCom"></div></div>
  <div class="card"><h2>CBOT benchmark, by commodity</h2><p class="sub">CBOT stored for each consumption day · USD · separate from the savings</p><div id="chComCbot"></div></div>
 </div>
 <div class="grid2">
  <div class="card"><h2>Top 10 contracts by local market savings</h2><p class="sub">Click a bar to open the contract</p><div id="chTop"></div></div>
  <div class="card"><h2>Top 10 contracts by CBOT missed opportunity</h2><p class="sub">Historical benchmark, not a proven avoidable loss · click to open</p><div id="chMiss"></div></div>
 </div>
</section>

<section class="panel" id="p-savings">
 <div class="kpis" id="svKpis"></div>
 <div class="grid2">
  <div class="card"><h2>By commodity</h2><p class="sub">Imported tonnes consumed, each against the local delivered price observed on its day</p><div class="tw"><table id="svCom"></table></div></div>
  <div class="card"><h2>Saving vs loss, by contract</h2><p class="sub">Every consumed contract, best to worst · EGP · click a bar to open it</p><div id="svChart" style="max-height:520px;overflow-y:auto"></div></div>
 </div>
 <div class="card"><h2>Savings vs local — contract by contract</h2>
  <p class="sub">Daily saving = (local delivered price − our landed cost) × tonnes consumed that day. Click a contract to see its days, the local quote used and its date.</p>
  <div class="tw"><table id="svT"></table></div></div>
</section>

<section class="panel" id="p-contracts">
 <div class="card"><h2>Contract comparison</h2><p class="sub">Consumed contracts. CBOT fixed and the tonne-weighted CBOT on its consumption days side by side. Click a row for the full contract analysis.</p>
 <div class="tw"><table id="tC"></table></div></div>
</section>

<section class="panel" id="p-cbot">
 <div class="card"><h2>CBOT fixed vs consumption</h2>
  <p class="sub">Our fixed CBOT (reference line) against the stored CBOT on each day the contract was consumed. Green = market above our fixing (advantage), red = below (missed opportunity). Each point is the CBOT stored for that consumption day; hover for the difference, tonnes and USD impact.</p>
  <label class="note">Contract <select class="ctl" id="cbSel"></select></label>
  <div id="cbChart"></div><div id="cbBars"></div><div id="cbSum" class="note"></div>
 </div>
 <div class="card tech"><h2>Contract CBOT performance</h2><p class="sub">One row per fixed contract with consumption; result = sum of the consumption days' differences.</p><div class="tw"><table id="tCP"></table></div></div>
</section>

<section class="panel" id="p-open">
 <div class="kpis" id="okpis"></div>
 <div class="card"><h2>Landed cost vs today's local price</h2><p class="sub">Per contract with tonnes not yet consumed · EGP/MT · green = cheaper than local, red = dearer</p><div id="chOpen"></div></div>
 <div class="card"><h2>Open contracts and stock</h2><p class="sub">Fixed-price contracts are the confirmed potential; unpriced contracts are an indicative scenario totalled separately.</p><div class="tw"><table id="tO"></table></div></div>
</section>

<section class="panel" id="p-trends">
 <div class="grid2">
  <div class="card"><h2>Savings vs local by month</h2><p class="sub">Consumed tonnes against the local price on the day · EGP · by consumption month</p><div id="trMonth"></div></div>
  <div class="card"><h2>CBOT result by month</h2><p class="sub">Benchmark · USD · consumption days above (green) or below (red) our fixing</p><div id="trCbotMonth"></div></div>
 </div>
 <div class="card"><h2>Local price vs our landed cost</h2><p class="sub">Tonne-weighted, per consumption day · EGP/MT · the gap between the lines is the saving per tonne; breaks are periods with no imported tonnes consumed
  <label class="note" style="margin-left:10px">Commodity <select class="ctl" id="trLocBase"></select></label></p><div id="trLocal"></div></div>
 <div class="card"><h2>CBOT market vs our fixings</h2><p class="sub">Stored CBOT (line) and each fixed contract's CBOT across its consumption days (segment): green = market above our fixing while consumed, red = below
  <label class="note" style="margin-left:10px">Commodity <select class="ctl" id="trCbBase"></select></label></p><div id="trCbot"></div></div>
 <div class="grid2">
  <div class="card"><h2>Savings by supplier</h2><p class="sub">Historical savings vs local · EGP · click a bar for the supplier's contracts</p><div id="trSupplier"></div></div>
  <div class="card"><h2>Savings by origin</h2><p class="sub">Historical savings vs local · EGP</p><div id="trOrigin"></div></div>
 </div>
 <div class="card"><h2>Where consumption came from</h2><p class="sub">Share of consumed tonnes by source, per commodity · only compared imports carry savings</p><div id="trSource"></div></div>
</section>

<section class="panel" id="p-quality">
 <div class="card"><h2>Data quality</h2><p class="sub">Click a tile to list the records behind it.</p><div class="dq" id="dqTiles"></div></div>
 <div class="card"><h2>Validation before export</h2><div id="checks"></div><div class="tw" style="margin-top:10px"><table id="tAudit"></table></div></div>
 <div class="card"><h2 id="exTitle">Excluded &amp; missing data</h2><p class="sub" id="exSub"></p><div class="tw"><table id="tEx"></table></div></div>
 <div class="card"><h2>Sources and method</h2><div id="src" class="note"></div></div>
</section>
</main>
<div class="tip" id="tip"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const M = JSON.parse(document.getElementById("data").textContent);
const C = M.contracts, CI = Object.fromEntries(C.map(c => [c.id, c]));
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const isN = v => typeof v === "number" && isFinite(v);
const fx = (v, d) => isN(v) ? v.toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d}) : "—";
const f0 = v => fx(v, 0), f2 = v => fx(v, 2);
const sg = v => !isN(v) ? "na" : v > 0 ? "pos" : v < 0 ? "neg" : "";
const money = (cur, v) => isN(v) ? (v < 0 ? "−" : "") + cur + " " + f0(Math.abs(v)) : "—";
const short = v => { if (!isN(v)) return "—"; const a = Math.abs(v), s = v < 0 ? "−" : "";
  return s + (a >= 1e6 ? fx(a / 1e6, 1) + "M" : a >= 1e3 ? fx(a / 1e3, 0) + "k" : fx(a, 0)); };
const sum = (rows, fn) => rows.reduce((a, r) => { const v = fn(r); return isN(v) ? a + v : a; }, 0);
const td = (v, f, col) => `<td class="n ${col ? sg(v) : ""}">${(f || f0)(v)}</td>`;
const S = {tab: "overview", sort: {}, open: new Set(), dqTile: "", cb: ""};
const MATCHED = "Consumption-day CBOT";

// ── filters ──────────────────────────────────────────────────────────
function opts(sel, vals, all) { $(sel).innerHTML = `<option value="">${all}</option>` + vals.map(v => `<option>${esc(v)}</option>`).join(""); }
opts("fBase", [...new Set(C.map(c => c.base))].sort(), "All commodities");
opts("fOrigin", [...new Set(C.map(c => c.origin || "—"))].sort(), "All origins");
opts("fSupplier", [...new Set(C.map(c => c.supplier || "—"))].sort(), "All suppliers");
$("dlC").innerHTML = C.map(c => `<option value="${esc(c.contract)}">${esc(c.id)}</option>`).join("");
function F() {
  return {base: $("fBase").value, origin: $("fOrigin").value, supplier: $("fSupplier").value, q: $("fQ").value.trim().toLowerCase(),
          from: $("fFrom").value, to: $("fTo").value, open: $("fOpen").value, fix: $("fFix").value, dq: $("fDQ").value};
}
function contractOk(c, f) {
  if (f.base && c.base !== f.base) return false;
  if (f.origin && (c.origin || "—") !== f.origin) return false;
  if (f.supplier && (c.supplier || "—") !== f.supplier) return false;
  if (f.q && !(String(c.contract).toLowerCase().includes(f.q) || String(c.id).toLowerCase() === f.q)) return false;
  if (f.open === "open" && !c.is_open) return false;
  if (f.open === "closed" && c.is_open) return false;
  if (f.fix === "other" && ["Recorded", "Implied", "Not fixed"].includes(c.fix.type)) return false;
  if (f.fix && f.fix !== "other" && c.fix.type !== f.fix) return false;
  return true;
}
const inDates = (d, f) => (!f.from || d >= f.from) && (!f.to || d <= f.to);
function dqOk(r, f) {
  if (!f.dq) return true;
  if (f.dq === "final") return r.cif_basis === "Final CIF";
  if (f.dq === "prov") return r.cif_basis !== "Final CIF";
  if (f.dq === "same") return r.local_status.startsWith("Same");
  if (f.dq === "carry") return r.local_status.startsWith("Carried");
  if (f.dq === "stale") return r.local_status.startsWith("Stale");
  return true;
}
function view() {
  const f = F(), ids = new Set(C.filter(c => contractOk(c, f)).map(c => c.id));
  const sav = M.savings.filter(r => ids.has(r.contract_id) && inDates(r.date, f) && dqOk(r, f));
  const cb = M.cbot.filter(r => ids.has(r.contract_id) && inDates(r.date, f));
  const op = M.open.filter(r => ids.has(r.contract_id));
  return {f, ids, sav, cb, op, contracts: C.filter(c => ids.has(c.id)), filtered: Object.values(f).some(Boolean)};
}
function kpis(v) {
  const ass = v.cb.filter(r => r.assessable), fixed = v.op.filter(r => r.class === "Fixed price"), ind = v.op.filter(r => r.class === "Indicative (unpriced)");
  const openC = v.contracts.filter(c => c.is_open), mt = sum(v.sav, r => r.mt), hs = sum(v.sav, r => r.saving);
  const fixedMt = sum(v.cb, r => r.mt), aMt = sum(ass, r => r.mt);
  return {historical_saving_egp: hs, historical_mt: mt, historical_saving_egp_mt: mt ? hs / mt : null,
    historical_final_egp: sum(v.sav.filter(r => r.cif_basis === "Final CIF"), r => r.saving),
    historical_provisional_egp: sum(v.sav.filter(r => r.cif_basis !== "Final CIF"), r => r.saving),
    open_fixed_potential_egp: sum(fixed, r => r.potential), open_fixed_mt: sum(fixed, r => r.unconsumed_mt),
    open_indicative_potential_egp: sum(ind, r => r.potential), open_indicative_mt: sum(ind, r => r.unconsumed_mt),
    open_outstanding_mt: sum(openC.filter(c => c.delivery_verified), c => c.outstanding_mt),
    open_available_mt: sum(openC, c => c.available_mt), open_contracts: openC.length,
    cbot_advantage_usd: sum(ass.filter(r => r.usd > 0), r => r.usd), cbot_missed_usd: sum(ass.filter(r => r.usd < 0), r => r.usd),
    cbot_net_usd: sum(ass, r => r.usd), cbot_net_egp: sum(ass, r => r.egp), cbot_assessed_mt: aMt,
    cbot_fixed_consumed_mt: fixedMt, cbot_coverage: fixedMt ? aMt / fixedMt : null, contracts: v.contracts.length};
}

// ── tooltip ──────────────────────────────────────────────────────────
const tip = $("tip");
document.addEventListener("mousemove", e => {
  const t = e.target.closest && e.target.closest("[data-tip]");
  if (!t) { tip.style.display = "none"; return; }
  tip.innerHTML = t.getAttribute("data-tip"); tip.style.display = "block";
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - w - 8) + "px";
  tip.style.top = (e.clientY + 14 + h > innerHeight ? e.clientY - h - 10 : e.clientY + 14) + "px";
});

// ── charts ───────────────────────────────────────────────────────────
function hbar(items, o) {
  if (!items.length) return '<p class="note">Nothing to show for this selection.</p>';
  const W = 640, L = o.left || 150, R = 70, bh = 18, gap = 8, T = 6;
  const H = T + items.length * (bh + gap) + 18;
  const vals = items.map(i => i.value), mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), sp = (mx - mn) || 1;
  const X = v => L + (v - mn) / sp * (W - L - R);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria || "bar chart")}">`;
  s += `<line x1="${X(0)}" x2="${X(0)}" y1="${T - 2}" y2="${H - 16}" stroke="var(--axis)"/>`;
  items.forEach((it, i) => {
    const y = T + i * (bh + gap), x0 = X(Math.min(0, it.value)), w = Math.max(Math.abs(X(it.value) - X(0)), it.value ? 2 : 0);
    const col = it.color || (it.value < 0 ? "var(--bad)" : "var(--s1)");
    const lab = it.label.length > 24 ? it.label.slice(0, 23) + "…" : it.label;
    s += `<text class="lbl" x="${L - 8}" y="${y + bh - 5}" text-anchor="end">${esc(lab)}</text>`;
    s += `<g ${it.id ? `data-goto="${esc(it.id)}" style="cursor:pointer"` : ""} data-tip="${esc(it.tip || "")}">`;
    s += `<rect x="${L - 4}" y="${y - 2}" width="${W - L}" height="${bh + 4}" fill="transparent"/>`;
    s += `<rect x="${x0}" y="${y}" width="${w}" height="${bh}" rx="4" fill="${col}"/></g>`;
    const txt = esc(o.fmt ? o.fmt(it.value) : short(it.value));
    if (it.value >= 0) s += `<text class="lbl" x="${X(it.value) + 5}" y="${y + bh - 5}">${txt}</text>`;
    else if (w > 56) s += `<text x="${x0 + 6}" y="${y + bh - 5}" style="fill:#fff">${txt}</text>`;
    else s += `<text class="lbl" x="${X(0) + 5}" y="${y + bh - 5}">${txt}</text>`;
  });
  return s + "</svg>";
}

function cbotChart(c, rows) {
  rows = rows.filter(r => isN(r.cbot)).sort((a, b) => a.date < b.date ? -1 : 1);
  if (!rows.length) return '<p class="note">No consumption days with a stored CBOT for this selection.</p>';
  const W = 1200, H = 300, L = 56, R = 16, T = 14, B = 30, fix = c.fix.value;
  const ys = rows.map(r => r.cbot).concat([fix]), pad = (Math.max(...ys) - Math.min(...ys)) * 0.12 || 5;
  const lo = Math.min(...ys) - pad, hi = Math.max(...ys) + pad;
  const t0 = Date.parse(rows[0].date), t1 = Date.parse(rows[rows.length - 1].date), span = (t1 - t0) || 1;
  const X = d => rows.length === 1 ? (L + W - R) / 2 : L + (Date.parse(d) - t0) / span * (W - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="CBOT fixed vs consumption">`;
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fx(v, 0)}</text>`; }
  const bw = Math.max(2, Math.min(14, (W - L - R) / Math.max(rows.length, 1) * 0.8));
  rows.forEach(r => { if (!r.assessable) return; const x = X(r.date), y0 = Y(fix), y1 = Y(r.cbot);
    s += `<rect x="${x - bw / 2}" y="${Math.min(y0, y1)}" width="${bw}" height="${Math.max(Math.abs(y1 - y0), 1)}" fill="${r.cbot >= fix ? "var(--good)" : "var(--bad)"}" opacity=".28"/>`; });
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(fix)}" y2="${Y(fix)}" stroke="var(--ink)" stroke-width="1.5"/>`;
  s += `<text class="lbl" x="${W - R}" y="${Y(fix) - 6}" text-anchor="end">Our fixed CBOT ${f2(fix)} ${esc(c.fix.unit)}</text>`;
  s += `<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="${rows.map(r => X(r.date).toFixed(1) + "," + Y(r.cbot).toFixed(1)).join(" ")}"/>`;
  rows.forEach(r => {
    const t = `<b>${esc(r.date)}</b> · ${f0(r.mt)} MT consumed<br>CBOT ${f2(r.cbot)} (price of ${esc(r.cbot_date)}) vs fixed ${f2(fix)}<br>` +
      (r.assessable ? `Difference ${f2(r.diff)} → <b class="${sg(r.usd)}">${money("USD", r.usd)}</b> (${esc(r.result)})` : `Not compared: ${esc(r.benchmark)}`);
    s += `<circle cx="${X(r.date)}" cy="${Y(r.cbot)}" r="${r.assessable ? 4 : 3}" fill="${r.assessable ? "var(--s1)" : "var(--surface)"}" stroke="${r.assessable ? "var(--surface)" : "var(--muted)"}" stroke-width="2" data-tip="${esc(t)}"/>`;
  });
  s += `<text x="${L}" y="${H - 8}">${esc(rows[0].date)}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(rows[rows.length - 1].date)}</text></svg>`;
  return `<div class="legend"><span><i style="background:var(--s1)"></i>Stored CBOT on consumption days</span><span><i style="background:var(--ink)"></i>Our fixed CBOT</span><span><i style="background:var(--good);opacity:.5"></i>Above fixing (advantage)</span><span><i style="background:var(--bad);opacity:.5"></i>Below fixing (missed)</span></div>` + s;
}

function dailyBars(rows) {
  rows = rows.filter(r => r.assessable).sort((a, b) => a.date < b.date ? -1 : 1);
  if (!rows.length) return "";
  const W = 1200, H = 180, L = 56, R = 16, T = 10, B = 24;
  const vals = rows.map(r => r.usd), mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), sp = (mx - mn) || 1;
  const Y = v => T + (mx - v) / sp * (H - T - B), bw = Math.max(2, Math.min(22, (W - L - R) / rows.length - 2));
  let s = `<p class="note" style="margin:10px 0 2px">Daily financial difference on consumption days, USD</p><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Daily CBOT difference">`;
  [mx, 0, mn].forEach(v => { s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${v === 0 ? "var(--axis)" : "var(--grid)"}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${short(v)}</text>`; });
  const x0 = L + Math.max(0, (W - L - R - rows.length * (bw + 2)) / 2);
  rows.forEach((r, i) => { const x = x0 + i * (bw + 2);
    s += `<rect x="${x}" y="${Math.min(Y(0), Y(r.usd))}" width="${bw}" height="${Math.max(Math.abs(Y(r.usd) - Y(0)), 1)}" rx="2" fill="${r.usd >= 0 ? "var(--good)" : "var(--bad)"}" data-tip="${esc(`<b>${r.date}</b> · ${f0(r.mt)} MT<br>CBOT ${f2(r.cbot)} − fixed ${f2(r.fix)} = ${f2(r.diff)}<br><b>${money("USD", r.usd)}</b> · ${money("EGP", r.egp)}`)}"/>`; });
  return s + "</svg>";
}

function waterfall(c) {
  const h = c.hist; if (!isN(h.saving) || !h.priced_mt) return '<p class="note">No supported comparison against local for this contract.</p>';
  const landed = c.landed_egp_mt * h.priced_mt, local = h.local_wavg * h.priced_mt, sav = h.saving;
  const bars = [["Imported landed cost", 0, landed, "var(--s1)"], [sav >= 0 ? "Local savings" : "Loss vs local", landed, landed + sav, sav >= 0 ? "var(--good)" : "var(--bad)"], ["Comparable local cost", 0, local, "var(--muted)"]];
  const W = 520, H = 190, L = 56, T = 12, B = 34, mx = Math.max(landed, local) * 1.06, bw = 90;
  const Y = v => T + (1 - v / mx) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:560px" role="img" aria-label="Savings waterfall">`;
  [0, mx / 2, mx].forEach(v => { s += `<line x1="${L}" x2="${W - 10}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${short(v)}</text>`; });
  bars.forEach(([lab, a, b2, col], i) => { const x = L + 24 + i * (bw + 50), y = Y(Math.max(a, b2)), hh = Math.max(Math.abs(Y(a) - Y(b2)), 1);
    s += `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" rx="4" fill="${col}" data-tip="${esc(`<b>${lab}</b><br>EGP ${f0(b2 - a)}<br>${f0(h.priced_mt)} MT compared`)}"/>`;
    s += `<text class="lbl" x="${x + bw / 2}" y="${H - 18}" text-anchor="middle">${esc(lab)}</text><text class="lbl" x="${x + bw / 2}" y="${y - 4}" text-anchor="middle">${short(b2 - a)}</text>`; });
  return s + "</svg>";
}

function dumbbell(rows) {
  rows = rows.filter(r => isN(r.landed) && isN(r.local));
  if (!rows.length) return '<p class="note">No open contract has both a landed cost and a local price.</p>';
  const W = 1200, L = 240, R = 90, rh = 30, T = 18, H = T + rows.length * rh + 22;
  const vals = rows.flatMap(r => [r.landed, r.local]), lo = Math.min(...vals) * 0.98, hi = Math.max(...vals) * 1.02;
  const X = v => L + (v - lo) / (hi - lo) * (W - L - R);
  let s = `<div class="legend"><span><i style="background:var(--s1)"></i>Our landed cost</span><span><i style="background:var(--muted)"></i>Local delivered price today</span></div><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Landed vs local">`;
  rows.forEach((r, i) => { const y = T + i * rh + 8, good = r.local >= r.landed;
    s += `<text class="lbl" x="${L - 10}" y="${y + 4}" text-anchor="end">${esc((r.contract + " · " + r.class).slice(0, 34))}</text>`;
    s += `<g data-tip="${esc(`<b>${r.contract}</b> (${r.class})<br>Landed ${f2(r.landed)} vs local ${f2(r.local)} (${r.local_date})<br>${f2(r.saving_mt)} EGP/MT × ${f0(r.unconsumed_mt)} MT = <b>${money("EGP", r.potential)}</b>`)}">`;
    s += `<rect x="${L}" y="${y - 12}" width="${W - L - R}" height="24" fill="transparent"/>`;
    s += `<line x1="${X(r.landed)}" x2="${X(r.local)}" y1="${y}" y2="${y}" stroke="${good ? "var(--good)" : "var(--bad)"}" stroke-width="3"/>`;
    s += `<circle cx="${X(r.landed)}" cy="${y}" r="6" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/><circle cx="${X(r.local)}" cy="${y}" r="6" fill="var(--muted)" stroke="var(--surface)" stroke-width="2"/></g>`;
    s += `<text class="lbl" x="${W - R + 8}" y="${y + 4}">${short(r.potential)}</text>`; });
  return s + `<text x="${L}" y="${H - 4}">${f0(lo)}</text><text x="${W - R}" y="${H - 4}" text-anchor="end">${f0(hi)} EGP/MT</text></svg>`;
}

// ── overview ─────────────────────────────────────────────────────────
function kcard(label, val, txt, tag, sub) {
  return `<div class="kpi"><div class="l"><span>${esc(label)}</span>${tag}</div><div class="v ${sg(val)}">${txt}</div><div class="s">${sub}</div></div>`;
}
function renderOverview(v, K) {
  window.__K = K;
  const A = '<span class="tag act">Actual · FIFO estimated</span>', P = '<span class="tag pot">Potential</span>', B = '<span class="tag ben">Benchmark</span>';
  $("kpis").innerHTML = [
    kcard("Historical savings vs local", K.historical_saving_egp, money("EGP", K.historical_saving_egp), A,
      `${f0(K.historical_mt)} MT · ${isN(K.historical_saving_egp_mt) ? f0(K.historical_saving_egp_mt) : "—"} EGP/MT · final CIF ${short(K.historical_final_egp)}, provisional ${short(K.historical_provisional_egp)}`),
    kcard("Open contracts potential vs local", K.open_fixed_potential_egp, money("EGP", K.open_fixed_potential_egp), P,
      `Fixed-price · ${f0(K.open_fixed_mt)} MT · unpriced scenario ${money("EGP", K.open_indicative_potential_egp)} not included`),
    kcard("Open contract outstanding", K.open_outstanding_mt, f0(K.open_outstanding_mt) + " MT", '<span class="tag">Position</span>',
      `Not yet delivered · ${f0(K.open_available_mt)} MT delivered and in stock · ${K.open_contracts} open contracts`),
    kcard("Total CBOT pricing advantage", K.cbot_advantage_usd, money("USD", K.cbot_advantage_usd), B, "Consumption days the CBOT was above our fixing"),
    kcard("Total CBOT missed opportunity", K.cbot_missed_usd, money("USD", K.cbot_missed_usd), B, "Consumption days the CBOT was below our fixing"),
    kcard("Net CBOT pricing difference", K.cbot_net_usd, money("USD", K.cbot_net_usd), B,
      `${money("EGP", K.cbot_net_egp)} · ${isN(K.cbot_coverage) ? fx(K.cbot_coverage * 100, 0) : "—"}% of fixed-contract tonnes with a stored CBOT · never added to savings`),
  ].join("");
  const q = M.quality, negs = v.contracts.filter(c => isN(c.hist.saving) && c.hist.saving < 0);
  const lines = [
    `Importing instead of buying locally ${K.historical_saving_egp >= 0 ? "saved" : "cost"} <b class="${sg(K.historical_saving_egp)}">${money("EGP", Math.abs(K.historical_saving_egp))}</b> on ${f0(K.historical_mt)} MT consumed, each tonne against the local price observed on its day.`,
    `Fixed-price tonnes not yet consumed would save <b class="${sg(K.open_fixed_potential_egp)}">${money("EGP", K.open_fixed_potential_egp)}</b> at today's local price; unpriced contracts add an indicative ${money("EGP", K.open_indicative_potential_egp)} (scenario).`,
    `Against the CBOT on the consumption days our fixings gained ${money("USD", K.cbot_advantage_usd)} and missed ${money("USD", Math.abs(K.cbot_missed_usd))} — net <b class="${sg(K.cbot_net_usd)}">${money("USD", K.cbot_net_usd)}</b>, a historical benchmark already inside the savings above.`,
    negs.length ? `${negs.length} contract${negs.length > 1 ? "s" : ""} cost more than local on the days consumed (${money("EGP", sum(negs, c => c.hist.saving))} together).` : "No contract cost more than local on the days consumed.",
  ];
  if (!v.filtered) lines.push(`Kept out of these figures: ${f0(q.excluded_unsourced_mt)} MT of unsourced consumption and ${f0(q.missing_cbot_mt)} MT without a stored CBOT for the day — see Data quality.`);
  $("says").innerHTML = lines.map(l => `<li>${l}</li>`).join("");
  $("mgmtNote").innerHTML = `<b>${M.management_ready ? "✔ All validation checks passed" : "✖ Validation failed — not management-ready"}</b> · checksum ${esc(M.checksum)} · data as of ${esc(M.as_of)}. Actual = consumption already made (FIFO estimated); Potential = not yet consumed at today's local price; Benchmark = CBOT comparison, separate from savings.`;
  const bases = [...new Set(v.contracts.map(c => c.base))].sort();
  $("chCom").innerHTML = hbar(bases.map(b => { const r = v.sav.filter(x => x.base === b), val = sum(r, x => x.saving), mt = sum(r, x => x.mt);
    return {label: b, value: val, tip: `<b>${b}</b><br>${money("EGP", val)} on ${f0(mt)} MT<br>${mt ? f0(val / mt) : "—"} EGP/MT`}; }).filter(i => i.value), {left: 90, aria: "Savings by commodity"});
  $("chComCbot").innerHTML = hbar(bases.map(b => { const r = v.cb.filter(x => x.base === b && x.assessable), val = sum(r, x => x.usd);
    return {label: b, value: val, color: val >= 0 ? "var(--good)" : "var(--bad)", tip: `<b>${b}</b><br>${money("USD", val)} net on ${f0(sum(r, x => x.mt))} MT`}; }).filter(i => i.value), {left: 90, aria: "CBOT by commodity"});
  const per = {};
  v.sav.forEach(r => { per[r.contract_id] = (per[r.contract_id] || 0) + r.saving; });
  const top = Object.entries(per).filter(([, x]) => x > 0).sort((a, b) => b[1] - a[1]).slice(0, 10);
  $("chTop").innerHTML = hbar(top.map(([id, x]) => ({label: CI[id].contract, value: x, id, tip: `<b>${esc(CI[id].contract)}</b> · ${esc(CI[id].commodity)}<br>${money("EGP", x)}`})), {aria: "Top savings"});
  const pc = {};
  v.cb.filter(r => r.assessable).forEach(r => { pc[r.contract_id] = (pc[r.contract_id] || 0) + r.usd; });
  const miss = Object.entries(pc).filter(([, x]) => x < 0).sort((a, b) => a[1] - b[1]).slice(0, 10);
  $("chMiss").innerHTML = hbar(miss.map(([id, x]) => ({label: CI[id].contract, value: Math.abs(x), id, color: "var(--bad)", tip: `<b>${esc(CI[id].contract)}</b><br>Missed ${money("USD", Math.abs(x))} vs CBOT on its consumption days`})), {aria: "Top missed", fmt: x => "−" + short(x)});
}

// ── contracts tab ────────────────────────────────────────────────────
const CCOLS = [
  {h: "Contract", v: c => c.contract}, {h: "Supplier", v: c => c.supplier}, {h: "Commodity", v: c => c.commodity},
  {h: "Status", v: c => c.status}, {h: "Consumed MT", n: 1, v: c => c.x.mt}, {h: "Savings EGP", n: 1, v: c => c.x.sav, col: 1},
  {h: "EGP/MT", n: 1, v: c => c.x.mt ? c.x.sav / c.x.cmt : null, col: 1},
  {h: "CBOT fixed", n: 1, v: c => c.fix.value, f: f2}, {h: "Avg CBOT in consumption", n: 1, v: c => c.x.avg, f: f2},
  {h: "Difference", n: 1, v: c => isN(c.x.avg) ? c.x.avg - c.fix.value : null, f: f2, col: 1},
  {h: "CBOT result USD", n: 1, v: c => c.x.amt ? c.x.usd : null, col: 1}, {h: "Fixing", v: c => c.fix.type || "—"}, {h: "Data", v: c => c.cif_final ? "Final CIF" : "Provisional CIF"}];
function contractRows(v) {
  const sav = {}, cb = {};
  v.sav.forEach(r => { const s = sav[r.contract_id] = sav[r.contract_id] || {mt: 0, sav: 0}; s.mt += r.mt; s.sav += r.saving; });
  v.cb.forEach(r => { if (!r.assessable) return; const s = cb[r.contract_id] = cb[r.contract_id] || {mt: 0, usd: 0, w: 0}; s.mt += r.mt; s.usd += r.usd; s.w += r.cbot * r.mt; });
  return v.contracts.filter(c => c.consumed_mt > 0).map(c => Object.assign(c, {x: {mt: c.consumed_mt, cmt: (sav[c.id] || {}).mt || 0, sav: sav[c.id] ? sav[c.id].sav : null,
    amt: (cb[c.id] || {}).mt || 0, usd: (cb[c.id] || {}).usd || 0, avg: cb[c.id] ? cb[c.id].w / cb[c.id].mt : null}}));
}
function sortBy(rows, key, cols) {
  const st = S.sort[key]; if (!st) return rows; const col = cols[st.i];
  return rows.slice().sort((a, b) => { const x = col.v(a), y = col.v(b), nx = x == null || x === "", ny = y == null || y === "";
    if (nx && ny) return 0; if (nx) return 1; if (ny) return -1; return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * st.dir; });
}
function thead(key, cols) {
  const st = S.sort[key] || {};
  return "<thead><tr>" + cols.map((c, i) => `<th class="${c.n ? "n" : ""}" data-sort="${key}" data-i="${i}">${esc(c.h)}${st.i === i ? (st.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr></thead>";
}
function renderContracts(v) {
  let rows = contractRows(v);
  if (!S.sort.c) rows.sort((a, b) => (b.x.sav || -1e18) - (a.x.sav || -1e18)); else rows = sortBy(rows, "c", CCOLS);
  let s = thead("c", CCOLS) + "<tbody>";
  rows.forEach(c => {
    s += `<tr class="row" data-id="${esc(c.id)}" id="r-${esc(c.id)}">` + CCOLS.map(col => { const val = col.v(c);
      return col.n ? `<td class="n ${col.col ? sg(val) : ""}">${(col.f || f0)(val)}</td>` : `<td>${esc(val)}</td>`; }).join("") + "</tr>";
    if (S.open.has(c.id)) s += `<tr class="det"><td colspan="${CCOLS.length}">${detail(c, v)}</td></tr>`;
  });
  s += `<tr class="tot"><td colspan="4">Total · ${rows.length} contracts</td>${td(sum(rows, c => c.x.mt))}${td(sum(rows, c => c.x.sav), f0, 1)}<td></td><td></td><td></td><td></td>${td(sum(rows, c => c.x.amt ? c.x.usd : null), f0, 1)}<td></td><td></td></tr></tbody>`;
  $("tC").innerHTML = s;
}
const dl = p => "<dl>" + p.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${x}</dd>`).join("") + "</dl>";
function detail(c, v) {
  const h = c.hist, cb = c.cbot, f = c.fix, rows = v.cb.filter(r => r.contract_id === c.id);
  const ov = dl([["Contract", esc(c.contract)], ["Supplier", esc(c.supplier)], ["Commodity / origin", esc(c.commodity + " · " + (c.origin || "—"))],
    ["Quantity", f0(c.qty_mt) + " MT"], ["Delivery", esc(c.delivery_date) + `<br><span class="note">${esc(c.delivery_status)}</span>`],
    ["CIF USD/MT", f2(c.cif_usd_mt)], ["FX", fx(c.fx, 4) + ` <span class="note">${esc(c.fx_basis)}</span>`], ["Landed EGP/MT", f2(c.landed_egp_mt)], ["Source", esc(c.source_id)]]);
  const lo = dl([["Consumed", f0(c.consumed_mt) + " MT"], ["Compared vs local", f0(h.priced_mt) + " MT"], ["Period", esc((c.first_date || "—") + " → " + (c.last_date || "—"))],
    ["Wtd avg local EGP/MT", f2(h.local_wavg)], ["Savings EGP/MT", `<span class="${sg(h.saving_mt)}">${f2(h.saving_mt)}</span>`],
    ["Total savings", `<b class="${sg(h.saving)}">${money("EGP", h.saving)}</b>`], ["Basis", c.cif_final ? '<span class="tag act">Final CIF</span>' : '<span class="tag pot">Provisional CIF</span>']]);
  const cbx = f.fixed ? dl([["CBOT fixed", `<b>${f2(f.value)}</b> ${esc(f.unit)}`], ["Type", esc(f.status)], ["Pricing date", esc(f.pricing_date || "Not recorded")],
    ["Futures month", esc(c.contract_month ? c.contract_month.code + (c.contract_month.inferred ? " (year inferred)" : "") : c.futures_month || "—")],
    ["Premium / factor", f2(c.premium) + " / " + fx(f.factor, 4)], ["Avg CBOT, consumption days", f2(cb.avg_cbot)], ["Coverage", isN(cb.coverage) ? fx(cb.coverage * 100, 0) + "% of consumed MT" : "—"],
    ["Result", `<b class="${sg(cb.usd)}">${money("USD", cb.usd)}</b> · ${esc(cb.assessment)}`]])
    : `<p class="note">${esc(f.status || "No CBOT fixing")}${isN(f.indicative) ? ` — indicative ${f2(f.indicative)} ${esc(f.unit)} (not a final fixing)` : ""}</p>`;
  const op = dl([["Delivered", f0(c.delivered_mt) + " MT"], ["Consumed", f0(c.consumed_mt) + " MT"], ["Available stock", f0(c.available_mt) + " MT"], ["Outstanding", f0(c.outstanding_mt) + " MT"],
    ["Local today", f2(c.local_today) + ` <span class="note">${esc(c.local_today_key)} ${esc(c.local_today_date)}</span>`]]);
  return `<div class="panels"><div class="pn"><h4>Contract overview</h4>${ov}</div><div class="pn"><h4>Savings vs local market</h4>${lo}</div><div class="pn"><h4>CBOT pricing (benchmark)</h4>${cbx}</div><div class="pn"><h4>Open position</h4>${op}</div></div>
   <div class="grid2" style="margin-top:10px"><div class="pn"><h4>Savings waterfall — compared tonnes</h4>${waterfall(c)}<p class="note">The CBOT result is a separate benchmark and is not part of this saving.</p></div>
   <div class="pn"><h4>CBOT fixed vs consumption</h4>${f.fixed ? cbotChart(c, rows) : '<p class="note">Not applicable.</p>'}</div></div>
   <div class="assess"><b>Final assessment.</b> ${esc(c.assessment)}</div>`;
}

// ── CBOT tab ─────────────────────────────────────────────────────────
const CPC = [{h: "Contract", v: c => c.contract}, {h: "Supplier", v: c => c.supplier}, {h: "MT consumed", n: 1, v: c => c.y.mt},
  {h: "MT assessed", n: 1, v: c => c.y.amt}, {h: "Coverage %", n: 1, v: c => c.y.mt ? c.y.amt / c.y.mt * 100 : null, f: x => fx(x, 0)},
  {h: "CIF $/MT", n: 1, v: c => c.cif_usd_mt, f: f2}, {h: "Premium", n: 1, v: c => c.premium, f: f2}, {h: "CBOT fixed", n: 1, v: c => c.fix.value, f: f2},
  {h: "Avg CBOT in consumption", n: 1, v: c => c.y.avg, f: f2}, {h: "Difference", n: 1, v: c => isN(c.y.avg) ? c.y.avg - c.fix.value : null, f: f2, col: 1},
  {h: "Advantage USD", n: 1, v: c => c.y.adv, col: 1}, {h: "Missed USD", n: 1, v: c => c.y.miss, col: 1},
  {h: "Net USD", n: 1, v: c => c.y.amt ? c.y.usd : null, col: 1}, {h: "Net EGP", n: 1, v: c => c.y.amt ? c.y.egp : null, col: 1}, {h: "Assessment", v: c => c.y.res}];
function renderCbot(v) {
  const n = M.options.neutral_cbot, by = {};
  v.cb.forEach(r => { const s = by[r.contract_id] = by[r.contract_id] || {mt: 0, amt: 0, usd: 0, egp: 0, w: 0, adv: 0, miss: 0};
    s.mt += r.mt; if (r.assessable) { s.amt += r.mt; s.usd += r.usd; s.egp += r.egp || 0; s.w += r.cbot * r.mt; if (r.usd > 0) s.adv += r.usd; else s.miss += r.usd; } });
  let rows = v.contracts.filter(c => by[c.id]).map(c => { const s = by[c.id], avg = s.amt ? s.w / s.amt : null, d = isN(avg) ? avg - c.fix.value : null;
    return Object.assign(c, {y: Object.assign(s, {avg, res: !s.amt ? "Not assessable" : d >= n ? "Advantage" : d <= -n ? "Missed opportunity" : "Neutral"})}); });
  rows = S.sort.cp ? sortBy(rows, "cp", CPC) : rows.sort((a, b) => (a.y.amt ? a.y.usd : 1e18) - (b.y.amt ? b.y.usd : 1e18));
  $("tCP").innerHTML = thead("cp", CPC) + "<tbody>" + rows.map(c => `<tr class="row" data-goto="${esc(c.id)}">` + CPC.map(col => { const val = col.v(c);
    return col.n ? `<td class="n ${col.col ? sg(val) : ""}">${(col.f || f0)(val)}</td>` : `<td>${esc(val)}</td>`; }).join("") + "</tr>").join("") +
    `<tr class="tot"><td colspan="2">Total · ${rows.length}</td>${td(sum(rows, c => c.y.mt))}${td(sum(rows, c => c.y.amt))}<td colspan="6"></td>${td(sum(rows, c => c.y.adv), f0, 1)}${td(sum(rows, c => c.y.miss), f0, 1)}${td(sum(rows, c => c.y.usd), f0, 1)}${td(sum(rows, c => c.y.egp), f0, 1)}<td></td></tr></tbody>`;
  const choices = rows.slice().sort((a, b) => b.y.amt - a.y.amt);
  if (!choices.find(c => c.id === S.cb)) S.cb = choices.length ? choices[0].id : "";
  $("cbSel").innerHTML = choices.map(c => `<option value="${esc(c.id)}" ${c.id === S.cb ? "selected" : ""}>${esc(c.contract)} · ${esc(c.commodity)} · ${f0(c.y.amt)} of ${f0(c.y.mt)} MT with a stored CBOT</option>`).join("");
  const c = CI[S.cb];
  if (!c) { $("cbChart").innerHTML = '<p class="note">No fixed contract with consumption in this selection.</p>'; $("cbBars").innerHTML = ""; $("cbSum").innerHTML = ""; return; }
  const cr = v.cb.filter(r => r.contract_id === c.id), s = by[c.id];
  $("cbChart").innerHTML = cbotChart(c, cr);
  $("cbBars").innerHTML = dailyBars(cr);
  $("cbSum").innerHTML = `${esc(c.fix.status)} · fixed ${f2(c.fix.value)} ${esc(c.fix.unit)} · futures ${esc(c.contract_month ? c.contract_month.code : "—")} · CBOT on ${f0(s.amt)} of ${f0(s.mt)} MT consumed · advantage ${money("USD", s.adv)} · missed ${money("USD", s.miss)} · net <b class="${sg(s.usd)}">${money("USD", s.usd)}</b>`;
}

// ── open tab ─────────────────────────────────────────────────────────
const OCOLS = [{h: "Contract", v: r => r.contract}, {h: "Supplier", v: r => r.supplier}, {h: "Commodity", v: r => r.commodity},
  {h: "Total MT", n: 1, v: r => r.qty_mt}, {h: "Delivered MT", n: 1, v: r => r.delivered_mt}, {h: "Available MT", n: 1, v: r => r.available_mt},
  {h: "Outstanding MT", n: 1, v: r => r.outstanding_mt}, {h: "Pricing", v: r => r.pricing_status}, {h: "CIF USD/MT", n: 1, v: r => r.cif, f: f2},
  {h: "FX", n: 1, v: r => r.fx, f: x => fx(x, 4)}, {h: "Landed EGP/MT", n: 1, v: r => r.landed, f: f2}, {h: "Local today", n: 1, v: r => r.local, f: f2},
  {h: "Local date", v: r => r.local_date}, {h: "Savings EGP/MT", n: 1, v: r => r.saving_mt, f: f2, col: 1}, {h: "Potential EGP", n: 1, v: r => r.potential, col: 1},
  {h: "Class", v: r => r.class}, {h: "Delivery", v: r => r.delivery_status}];
function renderOpen(v) {
  const K = kpis(v), rows = S.sort.o ? sortBy(v.op, "o", OCOLS) : v.op.slice().sort((a, b) => (b.potential || -1e18) - (a.potential || -1e18));
  const latest = rows.map(r => r.local_date).filter(Boolean).sort().pop() || "—";
  const ranked = rows.filter(r => isN(r.saving_mt)).sort((a, b) => b.saving_mt - a.saving_mt);
  $("okpis").innerHTML = [
    kcard("Confirmed potential (fixed price)", K.open_fixed_potential_egp, money("EGP", K.open_fixed_potential_egp), '<span class="tag pot">Potential</span>', `${f0(K.open_fixed_mt)} MT not yet consumed`),
    kcard("Unpriced scenario (indicative)", K.open_indicative_potential_egp, money("EGP", K.open_indicative_potential_egp), '<span class="tag">Scenario</span>', `${f0(K.open_indicative_mt)} MT · CIF not final · not in the confirmed total`),
    kcard("Quantities", K.open_available_mt, `${f0(K.open_available_mt)} MT`, '<span class="tag">Position</span>', `in stock on open contracts · ${f0(K.open_outstanding_mt)} MT outstanding · ${f0(sum(rows, r => r.unconsumed_mt))} MT not yet consumed incl. closed-contract stock · latest local quote ${esc(latest)}`),
  ].join("") + (ranked.length ? kcard("Best / worst outstanding", ranked[0].saving_mt, esc(ranked[0].contract), "", `best ${f2(ranked[0].saving_mt)} EGP/MT · worst ${esc(ranked[ranked.length - 1].contract)} ${f2(ranked[ranked.length - 1].saving_mt)} EGP/MT`) : "");
  $("chOpen").innerHTML = dumbbell(rows.filter(r => r.unconsumed_mt > 0));
  $("tO").innerHTML = thead("o", OCOLS) + "<tbody>" + rows.map(r => `<tr class="row" data-goto="${esc(r.contract_id)}">` + OCOLS.map(col => { const val = col.v(r);
    return col.n ? `<td class="n ${col.col ? sg(val) : ""}">${(col.f || f0)(val)}</td>` : `<td>${esc(val)}</td>`; }).join("") + "</tr>").join("") +
    `<tr class="tot"><td colspan="3">Total · ${rows.length}</td>${td(sum(rows, r => r.qty_mt))}${td(sum(rows, r => r.delivered_mt))}${td(sum(rows, r => r.available_mt))}${td(sum(rows, r => r.outstanding_mt))}<td colspan="7"></td>${td(sum(rows.filter(r => r.class === "Fixed price"), r => r.potential), f0, 1)}<td>fixed only</td><td></td></tr></tbody>`;
}

// ── data quality tab ─────────────────────────────────────────────────
function renderQuality() {
  const q = M.quality, tiles = [
    ["", "Verified (actual) allocations", q.verified_allocations, "rows"], ["", "FIFO-estimated allocations", q.fifo_allocations, "rows"],
    ["Unsourced consumption", "Excluded unsourced", q.excluded_unsourced, `rows · ${f0(q.excluded_unsourced_mt)} MT`],
    ["missing-dates", "Fixed contracts without a pricing date", q.missing_pricing_dates, "fixing implied from CIF"],
    ["CBOT comparison not assessable", "Days without a stored CBOT", q.missing_cbot, `rows · ${f0(q.missing_cbot_mt)} MT`],
    ["No usable local price", "Missing local observations", q.missing_local, `rows · ${f0(q.missing_local_mt)} MT`],
    ["stale", "Stale local references (8–30 d)", q.stale_local, `rows · ${f0(q.stale_local_mt)} MT · used, flagged`],
    ["Logged entry not used", "Logged entries not used", M.excluded.filter(e => e.category === "Logged entry not used").length, "see reason"]];
  $("dqTiles").innerHTML = tiles.map(([k, l, val, sub]) => `<button data-dq="${esc(k)}" class="${S.dqTile === k && k ? "on" : ""}"><div class="v">${f0(val)}</div><div class="l">${esc(l)}<br>${esc(sub)}</div></button>`).join("");
  $("checks").innerHTML = `<p><span class="badge ${M.management_ready ? "ok" : "no"}">${M.management_ready ? "✔ Management-ready" : "✖ Not management-ready"}</span> <span class="note">checksum ${esc(M.checksum)} — the Excel workbook prints the same</span></p>` +
    M.validation.map(x => `<div class="check"><span class="r ${x.passed ? "pos" : "neg"}">${x.passed ? "✔ PASS" : "✖ FAIL"}</span><span><b>${esc(x.check)}</b><br><span class="note">${esc(x.detail)}</span></span></div>`).join("");
  $("tAudit").innerHTML = `<thead><tr><th>Commodity</th><th class="n">Total consumed MT</th><th class="n">Sourced allocated MT</th><th class="n">Excluded / unallocated MT</th><th class="n">Difference</th></tr></thead><tbody>` +
    M.audit.map(a => `<tr><td>${esc(a.base)}</td>${td(a.consumed_mt)}${td(a.allocated_mt)}${td(a.excluded_mt)}${td(a.difference_mt)}</tr>`).join("") + "</tbody>";
  let ex = M.excluded, title = "Excluded & missing data";
  if (S.dqTile === "missing-dates") { ex = C.filter(c => c.fix.fixed && !c.fix.pricing_date_known).map(c => ({category: "Pricing date not recorded", contract: c.contract, contract_id: c.id, commodity: c.base, reason: `CBOT fixing implied from CIF ${f2(c.cif_usd_mt)} ÷ ${c.fix.factor} − premium ${f2(c.premium)} = ${f2(c.fix.value)}; the date it was fixed is not stored.`, source: c.source_id})); title = "Fixed contracts without a pricing date"; }
  else if (S.dqTile === "stale") { ex = M.savings.filter(r => r.local_status.startsWith("Stale")).map(r => ({category: r.local_status, date: r.date, contract: r.contract, contract_id: r.contract_id, commodity: r.base, mt: r.mt, reason: `Local quote of ${r.local_date} (${r.local_age} days old) carried forward — used and flagged.`, source: r.local_source})); title = "Stale local references (used, flagged)"; }
  else if (S.dqTile) { ex = M.excluded.filter(e => e.category === S.dqTile); title = S.dqTile; }
  $("exTitle").textContent = title;
  $("exSub").textContent = `${ex.length} records${S.dqTile ? " · click the tile again to show all" : ""}. Nothing here is counted as zero or filled with an assumed value.`;
  const shown = ex.slice(0, 600);
  $("tEx").innerHTML = `<thead><tr><th>Category</th><th>Date</th><th>Contract</th><th>Commodity</th><th class="n">MT</th><th>Reason</th><th>Source</th></tr></thead><tbody>` +
    shown.map(e => `<tr><td>${esc(e.category)}</td><td>${esc(e.date)}</td><td>${esc(e.contract || e.contract_id)}</td><td>${esc(e.commodity)}</td>${td(e.mt)}<td>${esc(e.reason)}</td><td>${esc(e.source)}</td></tr>`).join("") +
    (ex.length > shown.length ? `<tr><td colspan="7" class="note">… ${ex.length - shown.length} more — all are in the Excel sheet Excluded & Missing Data.</td></tr>` : "") + "</tbody>";
  const src = M.sources || {}, o = M.options;
  $("src").innerHTML = `<p>Data as of ${esc(M.as_of)} · generated ${esc(M.generated)} · consumption: ${esc(M.walk_mode)} · rates ${esc(Object.entries(M.rates || {}).map(([k, x]) => k + " " + x).join(", "))} MT/day.</p>
   <p>CBOT: ${esc(src.cbot_source || "")}; ${esc(Object.entries(src.cbot || {}).map(([k, x]) => `${k} ${x[0]} → ${x[1]}`).join(" · "))}. Each consumption day is compared with the CBOT stored for that day (the contract's futures month is only the month its premium is quoted over); one-day spikes and prints older than ${o.cbot_max_age_days} days are not used. Advantage when CBOT − fixed ≥ ${o.neutral_cbot}, missed when ≤ −${o.neutral_cbot}, else neutral.</p>
   <p>Local: origin-matched delivered price (price + freight) observed on or before the day; ≤ ${o.carry_days} days carried forward, ≤ ${o.max_carry_days} days stale but used and flagged, older excluded. Latest quotes: ${esc(Object.entries(src.local_latest || {}).map(([k, x]) => k + " " + x).join(" · "))}.</p>
   <p>Landed cost: CIF × FX (Form 4 once entered, except SBM; else delivery FX) + discharge + clearance + inland freight. CBOT fixed: pricing lots, else CIF ÷ factor − premium (CORN 0.3937; SOYBEAN, WHEAT 0.36745; SBM 1.1023 with premium in $/short ton). Unpriced contracts are never shown as fixed.</p>`;
}

// ── export the filtered view to a real .xlsx (stored zip, no library) ─
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(b) { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function zip(files) {
  const enc = new TextEncoder(), parts = [], dir = []; let off = 0;
  const u16 = n => [n & 255, (n >>> 8) & 255], u32 = n => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255];
  files.forEach(([name, text]) => { const nb = enc.encode(name), db = enc.encode(text), crc = crc32(db);
    const head = new Uint8Array([...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(db.length), ...u32(db.length), ...u16(nb.length), ...u16(0)]);
    parts.push(head, nb, db);
    dir.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(db.length), ...u32(db.length), ...u16(nb.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(off)]), nb);
    off += head.length + nb.length + db.length; });
  const dlen = dir.reduce((a, p) => a + p.length, 0);
  const end = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(files.length), ...u16(files.length), ...u32(dlen), ...u32(off), ...u16(0)]);
  return new Blob([...parts, ...dir, end], {type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"});
}
function sheetXml(rows) {
  const x = s => String(s).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
  const colL = i => { let s = ""; i++; while (i) { const m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; };
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>` +
    rows.map((r, ri) => `<row r="${ri + 1}">` + r.map((v, ci) => { const ref = colL(ci) + (ri + 1);
      if (isN(v)) return `<c r="${ref}"><v>${v}</v></c>`; if (v == null || v === "") return "";
      return `<c r="${ref}" t="inlineStr"${ri === 0 ? ' s="1"' : ""}><is><t>${x(v)}</t></is></c>`; }).join("") + "</row>").join("") + "</sheetData></worksheet>";
}
function exportXlsx() {
  const v = view(), K = kpis(v), F_ = v.f;
  const sheets = [
    ["Summary", [["Procurement savings — filtered view"], ["Data as of", M.as_of], ["Checksum (unfiltered model)", M.checksum],
      ["Filters", Object.entries(F_).filter(([, x]) => x).map(([k, x]) => k + "=" + x).join("; ") || "none"], [],
      ["Measure", "Value"], ...Object.entries(K).map(([k, x]) => [k, x])]],
    ["Contracts", [["Contract ID", "Contract", "Supplier", "Commodity", "Origin", "Status", "Consumed MT", "Compared MT", "Savings EGP", "CBOT fixed", "Fixing type", "Avg CBOT consumption days", "CBOT net USD", "Assessment"],
      ...contractRows(v).map(c => [c.id, c.contract, c.supplier, c.commodity, c.origin, c.status, c.consumed_mt, c.x.cmt, c.x.sav, c.fix.value, c.fix.type, c.x.avg, c.x.amt ? c.x.usd : null, c.assessment])]],
    ["Savings vs Local", [["Date", "Contract", "Contract ID", "Commodity", "MT", "Landed EGP/MT", "Local EGP/MT", "Local date", "Quote age", "Savings EGP/MT", "Savings EGP", "Data quality", "Local record"],
      ...v.sav.map(r => [r.date, r.contract, r.contract_id, r.commodity, r.mt, r.cost, r.local, r.local_date, r.local_age, r.saving_mt, r.saving, r.quality, r.local_source])]],
    ["CBOT vs Consumption", [["Date", "Contract", "Contract ID", "MT", "CBOT fixed", "CBOT that day", "Price date", "Benchmark status", "Difference", "USD/MT", "USD", "EGP", "Result"],
      ...v.cb.map(r => [r.date, r.contract, r.contract_id, r.mt, r.fix, r.cbot, r.cbot_date, r.benchmark, r.diff, r.usd_mt, r.usd, r.egp, r.result])]],
    ["Open vs Local", [["Contract", "Contract ID", "Commodity", "Available MT", "Outstanding MT", "Landed EGP/MT", "Local EGP/MT", "Local date", "Savings EGP/MT", "Potential EGP", "Class", "Delivery"],
      ...v.op.map(r => [r.contract, r.contract_id, r.commodity, r.available_mt, r.outstanding_mt, r.landed, r.local, r.local_date, r.saving_mt, r.potential, r.class, r.delivery_status])]]];
  const files = [["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>` +
      sheets.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("") + "</Types>"],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>` +
      sheets.map(([n], i) => `<sheet name="${n}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("") + "</sheets></workbook>"],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
      sheets.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("") +
      `<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ["xl/styles.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`],
    ...sheets.map(([, rows], i) => [`xl/worksheets/sheet${i + 1}.xml`, sheetXml(rows)])];
  const blob = zip(files), a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `Procurement_Savings_view_${M.as_of}.xlsx`; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  window.__lastExport = files.map(f => f[0]);
}

// ── savings vs local tab ────────────────────────────────────────────
const SVC = [{h: "Contract", v: c => c.contract}, {h: "Supplier", v: c => c.supplier}, {h: "Commodity", v: c => c.commodity},
  {h: "Compared MT", n: 1, v: c => c.z.mt}, {h: "Landed EGP/MT", n: 1, v: c => c.z.cost, f: f2}, {h: "Wtd avg local EGP/MT", n: 1, v: c => c.z.local, f: f2},
  {h: "Savings EGP/MT", n: 1, v: c => c.z.per, f: f2, col: 1}, {h: "Total savings EGP", n: 1, v: c => c.z.sav, col: 1},
  {h: "Savings %", n: 1, v: c => c.z.pct, f: x => isN(x) ? fx(x, 1) + "%" : "—", col: 1}, {h: "First day", v: c => c.z.first}, {h: "Last day", v: c => c.z.last},
  {h: "CIF", v: c => c.cif_final ? "Final" : "Provisional"}, {h: "Local quotes", v: c => c.z.q}];
function svRows(v) {
  const by = {};
  v.sav.forEach(r => { const o = by[r.contract_id] = by[r.contract_id] || {mt: 0, sav: 0, c: 0, l: 0, first: r.date, last: r.date, rows: [], same: 0, carry: 0, stale: 0};
    o.mt += r.mt; o.sav += r.saving; o.c += r.cost * r.mt; o.l += r.local * r.mt; o.rows.push(r);
    if (r.date < o.first) o.first = r.date; if (r.date > o.last) o.last = r.date;
    if (r.local_status.startsWith("Same")) o.same += r.mt; else if (r.local_status.startsWith("Stale")) o.stale += r.mt; else o.carry += r.mt; });
  return Object.entries(by).map(([id, o]) => Object.assign(CI[id], {z: {mt: o.mt, sav: o.sav, cost: o.c / o.mt, local: o.l / o.mt, per: o.sav / o.mt,
    pct: o.l ? o.sav / o.l * 100 : null, first: o.first, last: o.last, rows: o.rows.sort((a, b) => a.date < b.date ? -1 : 1),
    q: [o.same && `${fx(o.same / o.mt * 100, 0)}% same day`, o.carry && `${fx(o.carry / o.mt * 100, 0)}% carried`, o.stale && `${fx(o.stale / o.mt * 100, 0)}% stale`].filter(Boolean).join(" · ")}}));
}
function renderSavings(v) {
  let rows = svRows(v);
  const tot = sum(rows, c => c.z.sav), mt = sum(rows, c => c.z.mt), win = rows.filter(c => c.z.sav >= 0), loss = rows.filter(c => c.z.sav < 0);
  const fin = sum(v.sav.filter(r => r.cif_basis === "Final CIF"), r => r.saving);
  $("svKpis").innerHTML = [
    kcard("Total savings vs local", tot, money("EGP", tot), '<span class="tag act">Actual · FIFO estimated</span>', `${f0(mt)} MT compared · ${mt ? f0(tot / mt) : "—"} EGP/MT · final CIF ${short(fin)}, provisional ${short(tot - fin)}`),
    kcard("Contracts cheaper than local", sum(win, c => c.z.sav), `${win.length} contracts`, '<span class="tag good">Saving</span>', `${money("EGP", sum(win, c => c.z.sav))} on ${f0(sum(win, c => c.z.mt))} MT`),
    kcard("Contracts dearer than local", sum(loss, c => c.z.sav), `${loss.length} contracts`, '<span class="tag bad">Loss</span>', `${money("EGP", sum(loss, c => c.z.sav))} on ${f0(sum(loss, c => c.z.mt))} MT`)].join("");
  const bases = [...new Set(rows.map(c => c.base))].sort();
  $("svCom").innerHTML = `<thead><tr><th>Commodity</th><th class="n">Contracts</th><th class="n">Compared MT</th><th class="n">Landed EGP/MT</th><th class="n">Local EGP/MT</th><th class="n">EGP/MT</th><th class="n">Savings EGP</th></tr></thead><tbody>` +
    bases.map(b => { const r = rows.filter(c => c.base === b), m = sum(r, c => c.z.mt), sv = sum(r, c => c.z.sav);
      return `<tr><td><b>${esc(b)}</b></td>${td(r.length)}${td(m)}${td(sum(r, c => c.z.cost * c.z.mt) / m, f2)}${td(sum(r, c => c.z.local * c.z.mt) / m, f2)}${td(sv / m, f0, 1)}${td(sv, f0, 1)}</tr>`; }).join("") +
    `<tr class="tot"><td>Total</td>${td(rows.length)}${td(mt)}<td></td><td></td>${td(mt ? tot / mt : null, f0, 1)}${td(tot, f0, 1)}</tr></tbody>`;
  const ranked = rows.slice().sort((a, b) => b.z.sav - a.z.sav);
  $("svChart").innerHTML = hbar(ranked.map(c => ({label: c.contract, value: c.z.sav, id: c.id,
    tip: `<b>${esc(c.contract)}</b> · ${esc(c.commodity)}<br>${money("EGP", c.z.sav)} on ${f0(c.z.mt)} MT (${f2(c.z.per)} EGP/MT)<br>landed ${f2(c.z.cost)} vs local ${f2(c.z.local)}`})), {aria: "Savings by contract", left: 170});
  rows = S.sort.sv ? sortBy(rows, "sv", SVC) : ranked;
  let h = thead("sv", SVC) + "<tbody>";
  rows.forEach(c => {
    h += `<tr class="row" data-sv="${esc(c.id)}" id="sv-${esc(c.id)}">` + SVC.map(col => { const val = col.v(c);
      return col.n ? `<td class="n ${col.col ? sg(val) : ""}">${(col.f || f0)(val)}</td>` : `<td>${esc(val)}</td>`; }).join("") + "</tr>";
    if (S.svOpen && S.svOpen.has(c.id)) h += `<tr class="det"><td colspan="${SVC.length}"><div class="detbox" style="width:auto"><table><thead><tr><th>Date</th><th class="n">MT</th><th class="n">Landed EGP/MT</th><th class="n">Local EGP/MT</th><th>Local quote of</th><th class="n">Age (days)</th><th class="n">Saving EGP/MT</th><th class="n">Saving EGP</th><th>Local record</th><th>Data quality</th></tr></thead><tbody>` +
      c.z.rows.map(r => `<tr><td>${esc(r.date)}</td>${td(r.mt)}${td(r.cost, f2)}${td(r.local, f2)}<td>${esc(r.local_date)} <span class="note">${esc(r.local_key)}</span></td>${td(r.local_age)}${td(r.saving_mt, f2, 1)}${td(r.saving, f0, 1)}<td>${esc(r.local_source)}</td><td class="note">${esc(r.quality)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total</td>${td(c.z.mt)}${td(c.z.cost, f2)}${td(c.z.local, f2)}<td></td><td></td>${td(c.z.per, f2, 1)}${td(c.z.sav, f0, 1)}<td></td><td></td></tr></tbody></table></div></td></tr>`;
  });
  h += `<tr class="tot"><td colspan="3">Total · ${rows.length} contracts</td>${td(mt)}<td></td><td></td>${td(mt ? tot / mt : null, f2, 1)}${td(tot, f0, 1)}<td colspan="5"></td></tr></tbody>`;
  $("svT").innerHTML = h;
}

// ── trends & breakdowns ─────────────────────────────────────────────
function vbars(items, o) {
  if (!items.length) return '<p class="note">Nothing to show for this selection.</p>';
  const W = 640, H = 230, L = 56, R = 10, T = 16, B = 30;
  const vals = items.map(i => i.value), mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), sp = (mx - mn) || 1;
  const Y = v => T + (mx - v) / sp * (H - T - B), slot = (W - L - R) / items.length, bw = Math.min(46, slot * 0.7);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria || "bar chart")}">`;
  [mx, (mx + mn) / 2, mn].forEach(v => { s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${short(v)}</text>`; });
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
  items.forEach((it, i) => { const x = L + i * slot + (slot - bw) / 2, y0 = Y(0), y1 = Y(it.value);
    const col = it.color || (it.value < 0 ? "var(--bad)" : "var(--s1)");
    s += `<g data-tip="${esc(it.tip || "")}"><rect x="${L + i * slot}" y="${T}" width="${slot}" height="${H - T - B}" fill="transparent"/>`;
    s += `<rect x="${x}" y="${Math.min(y0, y1)}" width="${bw}" height="${Math.max(Math.abs(y1 - y0), it.value ? 1 : 0)}" rx="4" fill="${col}"/></g>`;
    s += `<text class="lbl" x="${x + bw / 2}" y="${H - 12}" text-anchor="middle">${esc(it.label)}</text>`; });
  return s + "</svg>";
}
const monthName = m => { const [y, mm] = m.split("-"); return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mm - 1] + " " + y.slice(2); };
function lines2(rows, o) {
  if (rows.length < 2) return '<p class="note">Not enough consumption days for this selection.</p>';
  const W = 1200, H = 280, L = 60, R = 16, T = 14, B = 30;
  const ys = rows.flatMap(r => [r.a, r.b]), pad = (Math.max(...ys) - Math.min(...ys)) * 0.08 || 50;
  const lo = Math.min(...ys) - pad, hi = Math.max(...ys) + pad, t0 = Date.parse(rows[0].d), t1 = Date.parse(rows[rows.length - 1].d), sp = (t1 - t0) || 1;
  const X = d => L + (Date.parse(d) - t0) / sp * (W - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let s = `<div class="legend"><span><i style="background:var(--s1)"></i>${esc(o.a)}</span><span><i style="background:var(--s2)"></i>${esc(o.b)}</span></div><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria)}">`;
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fx(v, 0)}</text>`; }
  // A gap of more than 4 days without consumption breaks the line rather than bridging it.
  const path = key => rows.map((r, i) => ((i && Date.parse(r.d) - Date.parse(rows[i - 1].d) <= 4 * 864e5) ? "L" : "M")
    + X(r.d).toFixed(1) + "," + Y(r[key]).toFixed(1)).join(" ");
  s += `<path d="${path("b")}" fill="none" stroke="var(--s2)" stroke-width="2"/><path d="${path("a")}" fill="none" stroke="var(--s1)" stroke-width="2"/>`;
  const step = (W - L - R) / rows.length;
  rows.forEach(r => { s += `<rect x="${X(r.d) - step / 2}" y="${T}" width="${Math.max(step, 2)}" height="${H - T - B}" fill="transparent" data-tip="${esc(o.tip(r))}"/>`; });
  return s + `<text x="${L}" y="${H - 8}">${esc(rows[0].d)}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(rows[rows.length - 1].d)}</text></svg>`;
}
function cbotHistory(base, v) {
  const hist = (M.cbot_series || {})[base] || [];
  const segs = v.contracts.filter(c => c.base === base && c.fix.fixed && c.first_date && c.cbot.consumed_mt > 0);
  if (hist.length < 2) return '<p class="note">No stored CBOT history for this commodity.</p>';
  const W = 1200, H = 300, L = 56, R = 16, T = 14, B = 30;
  const ys = hist.map(h => h[1]).concat(segs.map(c => c.fix.value)), pad = (Math.max(...ys) - Math.min(...ys)) * 0.06 || 5;
  const lo = Math.min(...ys) - pad, hi = Math.max(...ys) + pad, t0 = Date.parse(hist[0][0]), t1 = Date.parse(hist[hist.length - 1][0]), sp = (t1 - t0) || 1;
  const X = d => L + Math.min(Math.max((Date.parse(d) - t0) / sp, 0), 1) * (W - L - R), Y = val => T + (1 - (val - lo) / (hi - lo)) * (H - T - B);
  let s = `<div class="legend"><span><i style="background:var(--s1)"></i>Stored CBOT (${esc(segs[0] ? segs[0].fix.unit : "")})</span><span><i style="background:var(--good)"></i>Our fixing — market was above it while consumed</span><span><i style="background:var(--bad)"></i>Our fixing — market was below it</span></div>`;
  s += `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="CBOT market vs fixings">`;
  for (let k = 0; k <= 4; k++) { const val = lo + (hi - lo) * k / 4; s += `<line x1="${L}" x2="${W - R}" y1="${Y(val)}" y2="${Y(val)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(val) + 4}" text-anchor="end">${fx(val, 0)}</text>`; }
  s += `<path d="${hist.map((h, i) => (i ? "L" : "M") + X(h[0]).toFixed(1) + "," + Y(h[1]).toFixed(1)).join(" ")}" fill="none" stroke="var(--s1)" stroke-width="1.5"/>`;
  segs.forEach(c => { const good = (c.cbot.usd || 0) >= 0, x0 = X(c.first_date), x1 = Math.max(X(c.last_date), x0 + 4), y = Y(c.fix.value);
    const t = `<b>${esc(c.contract)}</b> · ${esc(c.fix.type)}<br>Fixed ${f2(c.fix.value)} · consumed ${esc(c.first_date)} → ${esc(c.last_date)}<br>Avg CBOT while consumed ${f2(c.cbot.avg_cbot)} → <b class="${sg(c.cbot.usd)}">${money("USD", c.cbot.usd)}</b>`;
    s += `<g data-goto="${esc(c.id)}" style="cursor:pointer" data-tip="${esc(t)}"><rect x="${x0 - 3}" y="${y - 8}" width="${x1 - x0 + 6}" height="16" fill="transparent"/><line x1="${x0}" x2="${x1}" y1="${y}" y2="${y}" stroke="${good ? "var(--good)" : "var(--bad)"}" stroke-width="5" stroke-linecap="round"/></g>`; });
  return s + `<text x="${L}" y="${H - 8}">${esc(hist[0][0])}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(hist[hist.length - 1][0])}</text></svg>`;
}
function stacked100(rows) {
  const parts = [["Imports compared vs local", "var(--s1)"], ["Imports not compared", "#86b6ef"], ["Local purchases (own tab)", "var(--s2)"], ["Unsourced (excluded)", "var(--muted)"]];
  const W = 1200, L = 90, R = 16, rh = 30, T = 6, H = T + rows.length * rh + 6;
  let s = `<div class="legend">${parts.map(([l, c]) => `<span><i style="background:${c}"></i>${esc(l)}</span>`).join("")}</div><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Consumption by source">`;
  rows.forEach((r, i) => { const y = T + i * rh, tot = r.vals.reduce((a, b) => a + b, 0) || 1; let x = L;
    s += `<text class="lbl" x="${L - 8}" y="${y + 18}" text-anchor="end">${esc(r.base)}</text>`;
    r.vals.forEach((val, j) => { const w = val / tot * (W - L - R); if (w <= 0) return;
      s += `<rect x="${x}" y="${y + 4}" width="${Math.max(w - 2, 1)}" height="20" rx="3" fill="${parts[j][1]}" data-tip="${esc(`<b>${r.base}</b> · ${parts[j][0]}<br>${f0(val)} MT · ${fx(val / tot * 100, 0)}%`)}"/>`;
      if (w > 60) s += `<text x="${x + 6}" y="${y + 18}" style="fill:#fff">${fx(val / tot * 100, 0)}%</text>`;
      x += w; }); });
  return s + "</svg>";
}
function renderTrends(v) {
  const byM = {}, cbM = {};
  v.sav.forEach(r => { const m = r.date.slice(0, 7), o = byM[m] = byM[m] || {s: 0, mt: 0, fin: 0}; o.s += r.saving; o.mt += r.mt; if (r.cif_basis === "Final CIF") o.fin += r.saving; });
  v.cb.filter(r => r.assessable).forEach(r => { const m = r.date.slice(0, 7), o = cbM[m] = cbM[m] || {u: 0, mt: 0, adv: 0, mis: 0}; o.u += r.usd; o.mt += r.mt; if (r.usd > 0) o.adv += r.usd; else o.mis += r.usd; });
  $("trMonth").innerHTML = vbars(Object.keys(byM).sort().map(m => ({label: monthName(m), value: byM[m].s,
    tip: `<b>${monthName(m)}</b><br>${money("EGP", byM[m].s)} on ${f0(byM[m].mt)} MT (${f0(byM[m].s / byM[m].mt)} EGP/MT)<br>final CIF ${short(byM[m].fin)} · provisional ${short(byM[m].s - byM[m].fin)}`})), {aria: "Savings by month"});
  $("trCbotMonth").innerHTML = vbars(Object.keys(cbM).sort().map(m => ({label: monthName(m), value: cbM[m].u, color: cbM[m].u >= 0 ? "var(--good)" : "var(--bad)",
    tip: `<b>${monthName(m)}</b><br>Net ${money("USD", cbM[m].u)} on ${f0(cbM[m].mt)} MT<br>advantage ${money("USD", cbM[m].adv)} · missed ${money("USD", cbM[m].mis)}`})), {aria: "CBOT by month"});
  const bases = [...new Set(v.sav.map(r => r.base))].sort();
  const keep = (sel, list, pref) => { const cur = $(sel).value; $(sel).innerHTML = list.map(b => `<option>${esc(b)}</option>`).join(""); $(sel).value = list.includes(cur) ? cur : (list.includes(pref) ? pref : list[0] || ""); };
  keep("trLocBase", bases, "CORN");
  const lb = $("trLocBase").value, day = {};
  v.sav.filter(r => r.base === lb).forEach(r => { const o = day[r.date] = day[r.date] || {mt: 0, c: 0, l: 0}; o.mt += r.mt; o.c += r.cost * r.mt; o.l += r.local * r.mt; });
  $("trLocal").innerHTML = lines2(Object.keys(day).sort().map(d => ({d, a: day[d].c / day[d].mt, b: day[d].l / day[d].mt, mt: day[d].mt})),
    {a: "Our landed cost (tonnes consumed that day)", b: "Local delivered price that day", aria: "Local vs landed",
     tip: r => `<b>${r.d}</b> · ${f0(r.mt)} MT<br>Landed ${f2(r.a)} · local ${f2(r.b)}<br>Saving <b class="${sg(r.b - r.a)}">${f2(r.b - r.a)} EGP/MT</b>`});
  const cbBases = Object.keys(M.cbot_series || {}).filter(b => v.contracts.some(c => c.base === b && c.fix.fixed)).sort();
  keep("trCbBase", cbBases, "CORN");
  $("trCbot").innerHTML = $("trCbBase").value ? cbotHistory($("trCbBase").value, v) : '<p class="note">No fixed contracts in this selection.</p>';
  const agg = key => { const o = {}; v.sav.forEach(r => { const k = key(r) || "—", x = o[k] = o[k] || {s: 0, mt: 0}; x.s += r.saving; x.mt += r.mt; });
    return Object.entries(o).sort((a, b) => b[1].s - a[1].s); };
  const sup = agg(r => r.supplier).slice(0, 12);
  $("trSupplier").innerHTML = hbar(sup.map(([k, x]) => ({label: k, value: x.s, sup: k, tip: `<b>${esc(k)}</b><br>${money("EGP", x.s)} on ${f0(x.mt)} MT · ${f0(x.s / x.mt)} EGP/MT`})), {aria: "Savings by supplier"});
  const org = agg(r => (CI[r.contract_id] || {}).origin);
  $("trOrigin").innerHTML = hbar(org.map(([k, x]) => ({label: k, value: x.s, tip: `<b>${esc(k)}</b><br>${money("EGP", x.s)} on ${f0(x.mt)} MT · ${f0(x.s / x.mt)} EGP/MT`})), {aria: "Savings by origin"});
  const f = v.f;
  $("trSource").innerHTML = stacked100(M.commodities.filter(c => !f.base || c.base === f.base).map(c => ({base: c.base,
    vals: [c.priced_mt, Math.max(c.allocated_import_mt - c.priced_mt, 0), c.allocated_local_mt, c.excluded_mt]})));
}

// ── wiring ───────────────────────────────────────────────────────────
function render() {
  const v = view(), K = kpis(v);
  renderOverview(v, K); renderSavings(v); renderContracts(v); renderCbot(v); renderOpen(v); renderTrends(v);
}
function showTab(p) { S.tab = p; document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.p === p));
  document.querySelectorAll(".panel").forEach(x => x.classList.toggle("on", x.id === "p-" + p)); }
function openContract(id) {
  const c = CI[id]; if (!c) return;
  if (!(c.consumed_mt > 0)) { showTab("open"); return; }
  ["fBase", "fOrigin", "fSupplier", "fQ", "fFix", "fOpen"].forEach(k => { if ($(k).value && !contractOk(c, F())) $(k).value = ""; });
  S.open.add(id); showTab("contracts"); render();
  const el = $("r-" + id); if (el) el.scrollIntoView({behavior: "smooth", block: "center"});
}
$("ttl").textContent = M.title;
$("meta").textContent = `Data as of ${M.as_of} · generated ${M.generated} · ${C.length} contracts · checksum ${M.checksum}`;
$("badges").innerHTML = `<button class="badge ${M.management_ready ? "ok" : "no"}" id="bReady">${M.management_ready ? "✔ Management-ready — all " + M.validation.length + " checks passed" : "✖ Not management-ready — " + M.validation.filter(x => !x.passed).length + " check(s) failed"}</button>` +
  `<span class="tag act">Actual = consumed (FIFO estimated)</span><span class="tag pot">Potential = not yet consumed</span><span class="tag ben">Benchmark = CBOT comparison</span>`;
$("bReady").addEventListener("click", () => { if (!document.body.classList.contains("mgmt")) showTab("quality"); });
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.p)));
["fBase", "fOrigin", "fSupplier", "fFrom", "fTo", "fOpen", "fFix", "fDQ"].forEach(id => $(id).addEventListener("change", render));
$("fQ").addEventListener("input", render);
$("fPreset").addEventListener("change", e => { const v = e.target.value, end = M.as_of; let start = "";
  if (v === "ytd") start = end.slice(0, 4) + "-01-01"; else if (v) { const d = new Date(end); d.setDate(d.getDate() - +v); start = d.toISOString().slice(0, 10); }
  $("fFrom").value = start; $("fTo").value = v ? end : ""; render(); });
$("bReset").addEventListener("click", () => { ["fBase", "fOrigin", "fSupplier", "fQ", "fFrom", "fTo", "fPreset", "fOpen", "fFix", "fDQ"].forEach(id => $(id).value = ""); render(); });
$("cbSel").addEventListener("change", e => { S.cb = e.target.value; renderCbot(view()); });
$("trLocBase").addEventListener("change", () => renderTrends(view()));
$("trCbBase").addEventListener("change", () => renderTrends(view()));
$("trSupplier").addEventListener("click", e => { const g = e.target.closest("g[data-tip]"); if (!g) return;
  const name = (g.getAttribute("data-tip").match(/<b>(.*?)<\/b>/) || [])[1]; if (!name) return;
  const tmp = document.createElement("textarea"); tmp.innerHTML = name; $("fSupplier").value = tmp.value; showTab("contracts"); render(); });
$("bMgmt").addEventListener("click", () => { const on = document.body.classList.toggle("mgmt"); $("bMgmt").textContent = on ? "Analyst View" : "Management View";
  if (on) { $("bReset").click(); showTab("overview"); } });
$("bTheme").addEventListener("click", () => { const r = document.documentElement, dark = r.getAttribute("data-theme") === "dark" ||
  (!r.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches); r.setAttribute("data-theme", dark ? "light" : "dark"); });
$("bXlsx").addEventListener("click", exportXlsx);
$("dqTiles").addEventListener("click", e => { const b = e.target.closest("button[data-dq]"); if (!b || !b.dataset.dq) return;
  S.dqTile = S.dqTile === b.dataset.dq ? "" : b.dataset.dq; renderQuality(); });
document.addEventListener("click", e => {
  const th = e.target.closest("th[data-sort]");
  if (th) { const k = th.dataset.sort, i = +th.dataset.i, cur = S.sort[k]; S.sort[k] = {i, dir: cur && cur.i === i ? -cur.dir : -1}; render(); return; }
  const g = e.target.closest("[data-goto]"); if (g) { openContract(g.getAttribute("data-goto")); return; }
  const svr = e.target.closest("tr.row[data-sv]");
  if (svr) { S.svOpen = S.svOpen || new Set(); const id = svr.dataset.sv; S.svOpen.has(id) ? S.svOpen.delete(id) : S.svOpen.add(id); renderSavings(view()); return; }
  const row = e.target.closest("tr.row[data-id]");
  if (row) { const id = row.dataset.id; S.open.has(id) ? S.open.delete(id) : S.open.add(id); renderContracts(view()); }
});
renderQuality();
render();
</script>
</body>
</html>
"""
