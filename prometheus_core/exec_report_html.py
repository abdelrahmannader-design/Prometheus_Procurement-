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
--warn:#fab219;--warn-ink:#8a5a00;--chip:#eef1f5;--good-bg:rgba(12,163,12,.10);--bad-bg:rgba(208,59,59,.10);--warn-bg:rgba(250,178,25,.16);--hover:#f1f5fb;--s1l:#9cc3f0;--badl:#eba3a3;--stale-bg:#ffe3b3;--stale-ink:#8a4b00}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--line:rgba(255,255,255,.10);--navy:#9cc3f5;--s1:#3987e5;--s2:#d95926;--good-ink:#0ca30c;--bad-ink:#e66767;--warn-ink:#fab219;
--chip:#26262a;--hover:#22252b;--s1l:#2f5f99;--badl:#7d3434;--stale-bg:rgba(255,150,40,.24);--stale-ink:#ffb35c}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--line:rgba(255,255,255,.10);--navy:#9cc3f5;--s1:#3987e5;--s2:#d95926;--good-ink:#0ca30c;--bad-ink:#e66767;--warn-ink:#fab219;--chip:#26262a;--hover:#22252b;--s1l:#2f5f99;--badl:#7d3434;--stale-bg:rgba(255,150,40,.24);--stale-ink:#ffb35c}
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
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:10px}
.pn dl{grid-template-columns:minmax(80px,max-content) minmax(0,1fr)!important}.pn dd{overflow-wrap:anywhere}.pn .stale,.pn .tag{white-space:normal}
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
.txbar{max-width:1440px;margin:10px auto 0;padding:0 24px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
@media(max-width:640px){.txbar{padding-left:16px;padding-right:16px}}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg button{border:0;background:transparent;color:var(--ink2);padding:6px 12px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer}
.seg button.on{background:var(--navy);color:var(--surface)}
.stale{display:inline-block;border-radius:6px;padding:1px 7px;font-size:11px;font-weight:700;background:var(--stale-bg);color:var(--stale-ink);white-space:nowrap}
tr.stl>td{background:var(--stale-bg)}
.nr{color:var(--warn-ink);font-weight:700}
.nm{font-size:11px;white-space:normal}
.kpi .v2{display:flex;flex-wrap:wrap;gap:4px 18px;margin:6px 0 2px}
.kpi .v2 div{display:flex;flex-direction:column}.kpi .v2 small{font-size:11px;color:var(--ink2);font-weight:600}.kpi .v2 span{font-size:21px;font-weight:700}
tr.rs>td:first-child{box-shadow:inset 4px 0 var(--good)}tr.rd>td:first-child{box-shadow:inset 4px 0 var(--bad)}
tr.rp>td:first-child{box-shadow:inset 4px 0 var(--warn)}tr.rx>td:first-child{box-shadow:inset 4px 0 var(--muted)}
tr.rd>td{background:var(--bad-bg)}tr.rx>td{color:var(--ink2)}
.ofl{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin:0 0 10px;font-size:12px;color:var(--ink2)}
.ofl label{display:flex;flex-direction:column;gap:3px}
.warnbox{border-left-color:var(--warn)}
#tO td{white-space:nowrap}
.detwrap{position:sticky;left:0;width:calc(100vw - 110px);max-width:1370px;white-space:normal}
@media(max-width:640px){.detwrap{width:calc(100vw - 64px)}}
.wf{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px}
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
<div class="txbar" id="txbar">
 <span class="note"><b>Transport basis</b></span>
 <div class="seg" id="txSeg" role="group" aria-label="Transport scenario"><button data-tx="side" class="on">Side-by-side</button><button data-tx="incl">Including transportation</button><button data-tx="excl">Excluding transportation</button></div>
 <span class="note" id="txNote"></span>
</div>
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
 <label>Data quality<select id="fDQ"><option value="">All supported rows</option><option value="final">Final CIF only</option><option value="prov">Provisional CIF only</option><option value="same">Same-day local quote</option><option value="carry">Last local price in force</option></select></label>
 <label>Local quote age<select id="fAge"><option value="">Any age</option><option value="stale-c">Contracts using quotes &gt; 5 days old</option><option value="stale-d">Only days on quotes &gt; 5 days old</option><option value="fresh">Only quotes 0–5 days old</option></select></label>
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
  <p class="sub">Daily saving = (local price − our landed cost) × tonnes consumed that day, including transport (local quote + local transport vs landed cost with inland freight) and excluding it (local quote vs landed cost without inland freight). Quotes more than 5 days old are shown <span class="stale">STALE</span>. Click a contract to see its days, the local quote used and its date.</p>
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
 <div class="card"><h2>Imported cost vs the latest local price</h2><p class="sub">Per contract with tonnes not yet consumed · EGP/MT · green = cheaper than local, red = dearer · hollow markers = excluding transport</p><div id="chOpen"></div></div>
 <div class="card"><h2>Open contracts vs local — decision table</h2><p class="sub">Every contract with tonnes not yet consumed. Confirmed = fixed price with Form 4; indicative / provisional (unpriced CBOT, provisional FX, not yet received) is totalled separately; rows missing a source input show N/A and are left out of both totals. Click a column to sort, a row to open the contract.</p>
  <div class="ofl"><label>Valuation<select class="ctl" id="oBucket"><option value="">All</option><option value="c">Confirmed</option><option value="i">Indicative / provisional</option><option value="x">Excluded — missing source data</option></select></label>
   <label>Result<select class="ctl" id="oRes"><option value="">All</option><option value="save">Saving vs local</option><option value="dear">Dearer than local</option><option value="na">Not assessable</option></select></label>
   <label>Tonnes<select class="ctl" id="oRem"><option value="">All rows</option><option value="rem">Only rows with tonnes remaining</option></select></label>
   <span class="legend" style="margin:0"><span><i style="background:var(--good)"></i>Saving (confirmed)</span><span><i style="background:var(--warn)"></i>Provisional / indicative</span><span><i style="background:var(--bad)"></i>Dearer than local</span><span><i style="background:var(--muted)"></i>Not assessable</span></span></div>
  <div class="tw"><table id="tO"></table></div></div>
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
const S = {tab: "overview", sort: {}, open: new Set(), dqTile: "", cb: "", tx: "side"};
const MATCHED = "Consumption-day CBOT";

// ── filters ──────────────────────────────────────────────────────────
function opts(sel, vals, all) { $(sel).innerHTML = `<option value="">${all}</option>` + vals.map(v => `<option>${esc(v)}</option>`).join(""); }
opts("fBase", [...new Set(C.map(c => c.base))].sort(), "All commodities");
opts("fOrigin", [...new Set(C.map(c => c.origin || "—"))].sort(), "All origins");
opts("fSupplier", [...new Set(C.map(c => c.supplier || "—"))].sort(), "All suppliers");
$("dlC").innerHTML = C.map(c => `<option value="${esc(c.contract)}">${esc(c.id)}</option>`).join("");
function F() {
  return {base: $("fBase").value, origin: $("fOrigin").value, supplier: $("fSupplier").value, q: $("fQ").value.trim().toLowerCase(),
          from: $("fFrom").value, to: $("fTo").value, open: $("fOpen").value, fix: $("fFix").value, dq: $("fDQ").value, age: $("fAge").value};
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
  if (f.dq === "carry") return !r.local_status.startsWith("Same");
  return true;
}
const CD = () => M.options.carry_days;
const ageOk = (r, f) => f.age === "stale-d" ? !!r.local_stale : f.age === "fresh" ? !r.local_stale && isN(r.local_age) : true;
const STALE_IDS = new Set(M.savings.filter(r => r.local_stale).map(r => r.contract_id).concat(M.open.filter(r => r.local_stale).map(r => r.contract_id)));
function view() {
  const f = F(), ids = new Set(C.filter(c => contractOk(c, f) && (f.age !== "stale-c" || STALE_IDS.has(c.id))).map(c => c.id));
  const sav = M.savings.filter(r => ids.has(r.contract_id) && inDates(r.date, f) && dqOk(r, f) && ageOk(r, f));
  const cb = M.cbot.filter(r => ids.has(r.contract_id) && inDates(r.date, f));
  const op = M.open.filter(r => ids.has(r.contract_id) && ageOk(r, f));
  return {f, ids, sav, cb, op, contracts: C.filter(c => ids.has(c.id)), filtered: Object.values(f).some(Boolean)};
}
// Transport scenarios: each side uses its own recorded transport; a row without the
// input a scenario needs is left out of that scenario's totals (never counted as zero).
const SCN = {
  incl: {k: "incl", l: "Incl. transport", s: "incl. transport", h: "incl.", sav: r => r.saving, cost: r => r.cost, local: r => r.local, per: r => r.saving_mt,
         ocost: o => o.cost_incl, olocal: o => o.local_incl, oper: o => o.saving_mt, pot: o => o.potential,
         hs: "historical_saving_egp", hmt: "historical_mt", hpm: "historical_saving_egp_mt", of: "open_fixed_potential_egp", oi: "open_indicative_potential_egp", fin: "historical_final_egp", prov: "historical_provisional_egp"},
  excl: {k: "excl", l: "Excl. transport", s: "excl. transport", h: "excl.", sav: r => r.saving_excl, cost: r => r.cost_excl, local: r => r.local_excl, per: r => r.saving_excl_mt,
         ocost: o => o.cost_excl, olocal: o => o.local_excl, oper: o => o.saving_excl_mt, pot: o => o.potential_excl,
         hs: "historical_saving_excl_egp", hmt: "historical_mt_excl", hpm: "historical_saving_excl_egp_mt", of: "open_fixed_potential_excl_egp", oi: "open_indicative_potential_excl_egp", fin: "historical_final_excl_egp", prov: "historical_provisional_excl_egp"}};
const scs = () => S.tx === "side" ? [SCN.incl, SCN.excl] : [SCN[S.tx]];
const PS = () => SCN[S.tx === "excl" ? "excl" : "incl"];
function aggS(rows, sc) {
  const r = rows.filter(x => isN(sc.sav(x))), mt = sum(r, x => x.mt), sv = sum(r, sc.sav);
  return {mt, sav: r.length ? sv : null, per: mt ? sv / mt : null, cost: mt ? sum(r, x => sc.cost(x) * x.mt) / mt : null,
          local: mt ? sum(r, x => sc.local(x) * x.mt) / mt : null, n: r.length};
}
const obucket = r => r.class === "Fixed price" ? "c" : (r.class === "Not assessable" || r.class.includes("incomplete")) ? "x" : "i";
function kpis(v) {
  const ass = v.cb.filter(r => r.assessable), fixed = v.op.filter(r => obucket(r) === "c"), ind = v.op.filter(r => obucket(r) === "i");
  const openC = v.contracts.filter(c => c.is_open), mt = sum(v.sav, r => r.mt), hs = sum(v.sav, r => r.saving);
  const X = aggS(v.sav, SCN.excl), fin = v.sav.filter(r => r.cif_basis === "Final CIF"), prov = v.sav.filter(r => r.cif_basis !== "Final CIF");
  const fixedMt = sum(v.cb, r => r.mt), aMt = sum(ass, r => r.mt);
  return {historical_saving_egp: hs, historical_mt: mt, historical_saving_egp_mt: mt ? hs / mt : null,
    historical_final_egp: sum(fin, r => r.saving), historical_provisional_egp: sum(prov, r => r.saving),
    historical_saving_excl_egp: X.sav || 0, historical_mt_excl: X.mt, historical_saving_excl_egp_mt: X.per,
    historical_final_excl_egp: sum(fin, r => r.saving_excl), historical_provisional_excl_egp: sum(prov, r => r.saving_excl),
    open_fixed_potential_egp: sum(fixed, r => r.potential), open_fixed_potential_excl_egp: sum(fixed, r => r.potential_excl), open_fixed_mt: sum(fixed, r => r.unconsumed_mt),
    open_indicative_potential_egp: sum(ind, r => r.potential), open_indicative_potential_excl_egp: sum(ind, r => r.potential_excl), open_indicative_mt: sum(ind, r => r.unconsumed_mt),
    open_not_received_mt: sum(v.op.filter(r => !r.received), r => r.unconsumed_mt),
    open_outstanding_mt: sum(openC.filter(c => c.delivery_verified), c => c.outstanding_mt),
    open_available_mt: sum(openC, c => c.available_mt), open_contracts: openC.length,
    cbot_advantage_usd: sum(ass.filter(r => r.usd > 0), r => r.usd), cbot_missed_usd: sum(ass.filter(r => r.usd < 0), r => r.usd),
    cbot_net_usd: sum(ass, r => r.usd), cbot_net_egp: sum(ass, r => r.egp), cbot_assessed_mt: aMt,
    cbot_fixed_consumed_mt: fixedMt, cbot_coverage: fixedMt ? aMt / fixedMt : null, contracts: v.contracts.length,
    stale_rows: v.sav.filter(r => r.local_stale).length, stale_mt: sum(v.sav.filter(r => r.local_stale), r => r.mt)};
}

// ── cells shared by the tables ───────────────────────────────────────
const NA_ = '<span class="na nm">N/A — Missing Source Data</span>';
const flatC = pc => pc === "Flat-priced" || pc === "Not CBOT-based";
function ageBadge(age) {
  if (!isN(age)) return '<span class="tag bad">No local quote — missing data</span>';
  if (age > CD()) return `<span class="stale">Local Market Price — ${age} Days Old — STALE</span>`;
  return `<span class="note">${age === 0 ? "Same day" : age + (age === 1 ? " day old" : " days old")}</span>`;
}
function receiptTag(rs) {
  rs = rs || "";
  if (rs.startsWith("Confirmed")) return '<span class="tag good" title="Receipt logged">Receipt confirmed</span>';
  if (rs.startsWith("Storage start")) return '<span class="tag act" title="Storage start recorded; no receipt logged">Storage date recorded</span>';
  if (rs.startsWith("Not yet")) return `<span class="tag pot">${esc(rs)}</span>`;
  return `<span class="tag bad" title="${esc(rs)}">Unverified — not received</span>`;
}
const storageCell = x => (x.storage_start ? esc(x.storage_start) : '<span class="nr">Not recorded</span>') + "<br>" + receiptTag(x.receipt_status);
function pTag(pc) {
  const cls = {"Fixed": "good", "Partially fixed": "pot", "Unpriced": "pot", "Flat-priced": "act"}[pc] || "";
  return `<span class="tag ${cls}">${esc(pc || "—")}</span>`;
}
const futCode = c => c.contract_month ? c.contract_month.code + (c.contract_month.inferred ? " (year inferred)" : "") : (c.futures_month || "—");
function fixCell(c) {
  const f = c.fix;
  if (f.fixed && isN(f.value)) {
    const lab = f.type === "Implied" ? "Implied CBOT Fixing" : f.type === "Recorded" ? "Recorded fixing (lots)" : f.type;
    return `${f2(f.value)} <span class="note">${esc(f.unit)}</span><br><span class="tag ${f.type === "Implied" ? "pot" : "act"}" title="${esc(f.status || "")}">${esc(lab)}</span>`;
  }
  if (flatC(c.pricing_class)) return '<span class="note">— flat price</span>';
  return `<span class="tag pot">Not fixed</span>${isN(f.indicative) ? `<br><span class="note">indicative ${f2(f.indicative)}</span>` : ""}`;
}
function cifCell(c) {
  if (!isN(c.cif_usd_mt)) return NA_;
  const f = c.fix, t = f.fixed && isN(f.value) && isN(c.premium) && isN(f.factor) ? `Final CIF = (CBOT ${f2(f.value)} + premium ${f2(c.premium)}) × ${f.factor} = ${f2((f.value + c.premium) * f.factor)}` : (c.cif_final ? "Contract CIF" : "Provisional CIF");
  return `<span title="${esc(t)}">${f2(c.cif_usd_mt)}</span><br>${c.cif_final ? '<span class="tag good">Final CIF</span>' : '<span class="tag pot">Provisional CIF</span>'}`;
}
const premCell = (prem, unit, pc) => flatC(pc) ? '<span class="note">— flat price</span>' : isN(prem) ? `${f2(prem)} <span class="note">${esc(unit || "")}</span>` : NA_;
const pdate = c => c.fix.pricing_date || c.pricing_date || "";
const COL = {
  storage: {h: "Storage start", v: c => c.storage_start || "", html: storageCell},
  premium: {h: "Premium", n: 1, v: c => flatC(c.pricing_class) ? null : c.premium, html: c => premCell(c.premium, c.fix.unit || c.premium_label, c.pricing_class)},
  futures: {h: "Futures month", v: futCode},
  fixing: {h: "CBOT fixing", n: 1, v: c => c.fix.value, html: fixCell},
  cif: {h: "Final CIF $/MT", n: 1, v: c => c.cif_usd_mt, html: cifCell},
  pdate: {h: "Pricing / fixing date", v: pdate, html: c => pdate(c) ? esc(pdate(c)) : (c.fix.fixed ? '<span class="note">Not recorded</span>' : "—")},
  pstatus: {h: "Pricing status", v: c => c.pricing_class, html: c => pTag(c.pricing_class)}};
function cell(col, r) {
  const val = col.v(r);
  if (col.html) return `<td class="${col.n ? "n" : ""}">${col.html(r, val)}</td>`;
  if (col.n) return `<td class="n ${col.col ? sg(val) : ""}">${!isN(val) && col.na ? NA_ : (col.f || f0)(val)}</td>`;
  return `<td>${esc(val)}</td>`;
}
function totRow(cols, rows, label) {
  return `<tr class="tot">` + cols.map((c, i) => i === 0 ? `<td>${label}</td>` : c.tot ? td(c.tot(rows), c.tf || f0, c.col) : "<td></td>").join("") + "</tr>";
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
  // value2 (when present) is the excluding-transport bar drawn under the including one.
  const two = items.some(i => isN(i.value2));
  const W = 640, L = o.left || 150, R = 70, bh = two ? 12 : 18, gap = 8, T = 6, rowH = two ? bh * 2 + 3 : bh;
  const H = T + items.length * (rowH + gap) + 18;
  const vals = items.flatMap(i => isN(i.value2) ? [i.value, i.value2] : [i.value]), mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), sp = (mx - mn) || 1;
  const X = v => L + (v - mn) / sp * (W - L - R);
  const bar = (val, y, col, inner) => { const x0 = X(Math.min(0, val)), w = Math.max(Math.abs(X(val) - X(0)), val ? 2 : 0), by = y + bh - (two ? 2 : 5);
    let t = `<rect x="${x0}" y="${y}" width="${w}" height="${bh}" rx="${two ? 3 : 4}" fill="${col}"/>`;
    const txt = esc(o.fmt ? o.fmt(val) : short(val));
    if (val >= 0) t += `<text class="lbl" x="${X(val) + 5}" y="${by}">${txt}</text>`;
    else if (w > 56) t += `<text x="${x0 + 6}" y="${by}" style="fill:${inner}">${txt}</text>`;
    else t += `<text class="lbl" x="${X(0) + 5}" y="${by}">${txt}</text>`;
    return t; };
  let s = two ? `<div class="legend"><span><i style="background:var(--s1)"></i>Incl. transport</span><span><i style="background:var(--s1l)"></i>Excl. transport</span></div>` : "";
  s += `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria || "bar chart")}">`;
  s += `<line x1="${X(0)}" x2="${X(0)}" y1="${T - 2}" y2="${H - 16}" stroke="var(--axis)"/>`;
  items.forEach((it, i) => {
    const y = T + i * (rowH + gap);
    const col = it.color || (it.value < 0 ? "var(--bad)" : "var(--s1)");
    const lab = it.label.length > 24 ? it.label.slice(0, 23) + "…" : it.label;
    s += `<text class="lbl" x="${L - 8}" y="${y + rowH / 2 + 4}" text-anchor="end">${esc(lab)}</text>`;
    s += `<g ${it.id ? `data-goto="${esc(it.id)}" style="cursor:pointer"` : ""} data-tip="${esc(it.tip || "")}">`;
    s += `<rect x="${L - 4}" y="${y - 2}" width="${W - L}" height="${rowH + 4}" fill="transparent"/>`;
    s += bar(it.value, y, col, "#fff");
    if (isN(it.value2)) s += bar(it.value2, y + bh + 3, it.value2 < 0 ? "var(--badl)" : "var(--s1l)", "var(--ink)");
    s += "</g>";
  });
  return s + "</svg>";
}
// Chart items for grouped rows, one bar per transport scenario shown.
function scItem(label, rows, extra) {
  const L_ = scs(), A = L_.map(sc => aggS(rows, sc));
  return Object.assign({label, value: A[0].sav || 0, value2: A[1] ? (A[1].sav || 0) : undefined,
    tip: `<b>${esc(label)}</b><br>` + L_.map((sc, i) => `${sc.l}: ${money("EGP", A[i].sav)} on ${f0(A[i].mt)} MT (${isN(A[i].per) ? f0(A[i].per) : "—"} EGP/MT)`).join("<br>")}, extra || {});
}
function groupBy(rows, key) { const o = {}; rows.forEach(r => { const k = key(r) || "—"; (o[k] = o[k] || []).push(r); }); return o; }

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

function waterfall(rows, sc) {
  const A = aggS(rows, sc);
  if (!isN(A.sav) || !A.mt) return `<p class="note">No supported comparison against local (${esc(sc.s)}) for this contract.</p>`;
  const landed = A.cost * A.mt, local = A.local * A.mt, sav = A.sav;
  const bars = [["Imported landed cost", 0, landed, "var(--s1)"], [sav >= 0 ? "Local savings" : "Loss vs local", landed, landed + sav, sav >= 0 ? "var(--good)" : "var(--bad)"], ["Comparable local cost", 0, local, "var(--muted)"]];
  const W = 520, H = 190, L = 56, T = 12, B = 34, mx = Math.max(landed, local) * 1.06, bw = 90;
  const Y = v => T + (1 - v / mx) * (H - T - B);
  let s = `<p class="note" style="margin:0">${esc(sc.l)}</p><svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:560px" role="img" aria-label="Savings waterfall ${esc(sc.s)}">`;
  [0, mx / 2, mx].forEach(v => { s += `<line x1="${L}" x2="${W - 10}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${short(v)}</text>`; });
  bars.forEach(([lab, a, b2, col], i) => { const x = L + 24 + i * (bw + 50), y = Y(Math.max(a, b2)), hh = Math.max(Math.abs(Y(a) - Y(b2)), 1);
    s += `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" rx="4" fill="${col}" data-tip="${esc(`<b>${lab}</b> · ${sc.s}<br>EGP ${f0(b2 - a)}<br>${f0(A.mt)} MT compared`)}"/>`;
    s += `<text class="lbl" x="${x + bw / 2}" y="${H - 18}" text-anchor="middle">${esc(lab)}</text><text class="lbl" x="${x + bw / 2}" y="${y - 4}" text-anchor="middle">${short(b2 - a)}</text>`; });
  return s + "</svg>";
}

function dumbbell(rows) {
  const L_ = scs(), P_ = PS();
  rows = rows.filter(r => L_.some(sc => isN(sc.ocost(r)) && isN(sc.olocal(r))));
  if (!rows.length) return '<p class="note">No open contract has both an imported cost and a local price.</p>';
  const W = 1200, L = 250, R = 150, rh = L_.length === 2 ? 40 : 30, T = 18, H = T + rows.length * rh + 22;
  const vals = rows.flatMap(r => L_.flatMap(sc => [sc.ocost(r), sc.olocal(r)])).filter(isN), lo = Math.min(...vals) * 0.98, hi = Math.max(...vals) * 1.02;
  const X = v => L + (v - lo) / (hi - lo) * (W - L - R);
  let s = `<div class="legend"><span><i style="background:var(--s1)"></i>Our imported cost</span><span><i style="background:var(--muted)"></i>Latest local price</span>${L_.length === 2 ? '<span><i style="background:transparent;border:2px solid var(--muted)"></i>Hollow = excluding transport</span>' : ""}</div><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Imported cost vs local">`;
  rows.forEach((r, i) => { const y0 = T + i * rh + 8;
    s += `<text class="lbl" x="${L - 10}" y="${y0 + (L_.length === 2 ? 9 : 4)}" text-anchor="end">${esc((r.contract + " · " + r.class).slice(0, 36))}</text>`;
    L_.forEach((sc, j) => { const a = sc.ocost(r), b = sc.olocal(r); if (!isN(a) || !isN(b)) return;
      const y = y0 + j * 16, good = b >= a, hollow = sc.k === "excl" && L_.length === 2;
      s += `<g data-tip="${esc(`<b>${r.contract}</b> (${r.class}) · ${sc.s}<br>Imported ${f2(a)} vs local ${f2(b)} (${r.local_date || "no date"})<br>${f2(sc.oper(r))} EGP/MT × ${f0(r.unconsumed_mt)} MT = <b>${money("EGP", sc.pot(r))}</b><br>${esc(r.cif_basis)} · ${esc(r.fx_basis)}`)}">`;
      s += `<rect x="${L}" y="${y - 8}" width="${W - L - R}" height="16" fill="transparent"/>`;
      s += `<line x1="${X(a)}" x2="${X(b)}" y1="${y}" y2="${y}" stroke="${good ? "var(--good)" : "var(--bad)"}" stroke-width="3"/>`;
      s += `<circle cx="${X(a)}" cy="${y}" r="6" fill="${hollow ? "var(--surface)" : "var(--s1)"}" stroke="${hollow ? "var(--s1)" : "var(--surface)"}" stroke-width="2"/><circle cx="${X(b)}" cy="${y}" r="6" fill="${hollow ? "var(--surface)" : "var(--muted)"}" stroke="${hollow ? "var(--muted)" : "var(--surface)"}" stroke-width="2"/></g>`; });
    s += `<text class="lbl" x="${W - R + 8}" y="${y0 + (L_.length === 2 ? 9 : 4)}">${L_.map(sc => short(sc.pot(r))).join(" / ")}${obucket(r) === "c" ? "" : " · prov."}</text>`; });
  return s + `<text x="${L}" y="${H - 4}">${f0(lo)}</text><text x="${W - R}" y="${H - 4}" text-anchor="end">${f0(hi)} EGP/MT</text></svg>`;
}

// ── overview ─────────────────────────────────────────────────────────
function kcard(label, val, txt, tag, sub) {
  return `<div class="kpi"><div class="l"><span>${esc(label)}</span>${tag}</div><div class="v ${sg(val)}">${txt}</div><div class="s">${sub}</div></div>`;
}
// One card, one figure per transport scenario shown.
function kcardS(label, f, tag, sub) {
  const L_ = scs();
  if (L_.length === 1) { const [val, txt] = f(L_[0]); return kcard(`${label} · ${L_[0].s}`, val, txt, tag, sub); }
  return `<div class="kpi"><div class="l"><span>${esc(label)}</span>${tag}</div><div class="v2">${L_.map(sc => { const [val, txt] = f(sc);
    return `<div><small>${esc(sc.l)}</small><span class="${sg(val)}">${txt}</span></div>`; }).join("")}</div><div class="s">${sub}</div></div>`;
}
function renderOverview(v, K) {
  window.__K = K;
  const A = '<span class="tag act">Actual · FIFO estimated</span>', P = '<span class="tag pot">Potential</span>', B = '<span class="tag ben">Benchmark</span>', L_ = scs(), P_ = PS();
  $("kpis").innerHTML = [
    kcardS("Historical savings vs local", sc => [K[sc.hs], money("EGP", K[sc.hs])], A,
      L_.map(sc => `${sc.h} ${f0(K[sc.hmt])} MT · ${isN(K[sc.hpm]) ? f0(K[sc.hpm]) : "—"} EGP/MT`).join(" · ") + ` · final CIF ${short(K[P_.fin])}, provisional ${short(K[P_.prov])}`),
    kcardS("Open potential vs local — confirmed", sc => [K[sc.of], money("EGP", K[sc.of])], P,
      `Fixed price with Form 4 · ${f0(K.open_fixed_mt)} MT · indicative / provisional ${L_.map(sc => sc.h + " " + money("EGP", K[sc.oi])).join(" / ")} kept separate`),
    kcard("Open contract outstanding", K.open_outstanding_mt, f0(K.open_outstanding_mt) + " MT", '<span class="tag">Position</span>',
      `Not yet delivered · ${f0(K.open_available_mt)} MT delivered and in stock · ${K.open_contracts} open contracts · ${f0(K.open_not_received_mt)} MT not confirmed received`),
    kcard("Total CBOT pricing advantage", K.cbot_advantage_usd, money("USD", K.cbot_advantage_usd), B, "Consumption days the CBOT was above our fixing · independent of transport"),
    kcard("Total CBOT missed opportunity", K.cbot_missed_usd, money("USD", K.cbot_missed_usd), B, "Consumption days the CBOT was below our fixing · independent of transport"),
    kcard("Net CBOT pricing difference", K.cbot_net_usd, money("USD", K.cbot_net_usd), B,
      `${money("EGP", K.cbot_net_egp)} · ${isN(K.cbot_coverage) ? fx(K.cbot_coverage * 100, 0) : "—"}% of fixed-contract tonnes with a stored CBOT · never added to savings`),
  ].join("");
  const q = M.quality, negs = Object.values(groupBy(v.sav, r => r.contract_id)).filter(r => { const a = aggS(r, P_).sav; return isN(a) && a < 0; });
  const lines = [
    `Savings from importing instead of buying locally: ${L_.map(sc => `<b class="${sg(K[sc.hs])}">${money("EGP", K[sc.hs])}</b> ${sc.s} (${isN(K[sc.hpm]) ? f0(K[sc.hpm]) : "—"} EGP/MT)`).join(" and ")} on ${f0(K.historical_mt)} MT consumed, each tonne against the local price in force on its day.`,
    `Fixed-price tonnes not yet consumed would save ${L_.map(sc => `<b class="${sg(K[sc.of])}">${money("EGP", K[sc.of])}</b> ${sc.s}`).join(" / ")} at the latest local price; unpriced or provisional contracts add an indicative ${L_.map(sc => money("EGP", K[sc.oi]) + " " + sc.h).join(" / ")}, kept separate.`,
    `Against the CBOT on the consumption days our fixings gained ${money("USD", K.cbot_advantage_usd)} and missed ${money("USD", Math.abs(K.cbot_missed_usd))} — net <b class="${sg(K.cbot_net_usd)}">${money("USD", K.cbot_net_usd)}</b>, a historical benchmark already inside the savings above, never added to them.`,
    negs.length ? `${negs.length} contract${negs.length > 1 ? "s" : ""} cost more than local on the days consumed (${P_.s}).` : `No contract cost more than local on the days consumed (${P_.s}).`,
    K.stale_rows ? `${f0(K.stale_rows)} consumption day-rows (${f0(K.stale_mt)} MT) were compared with a local quote more than ${CD()} days old — marked <span class="stale">STALE</span>; the last quote stays in force until a new one is entered.` : `Every local quote used was at most ${CD()} days old.`,
  ];
  if (!v.filtered) lines.push(`Kept out of these figures: ${f0(q.excluded_unsourced_mt)} MT of unsourced consumption and ${f0(q.missing_cbot_mt)} MT without a stored CBOT for the day — see Data quality.`);
  $("says").innerHTML = lines.map(l => `<li>${l}</li>`).join("");
  $("mgmtNote").innerHTML = `<b>${M.management_ready ? "✔ All validation checks passed" : "✖ Validation failed — not management-ready"}</b> · checksum ${esc(M.checksum)} · data as of ${esc(M.as_of)} · transport basis: ${S.tx === "side" ? "side-by-side (incl. and excl.)" : esc(SCN[S.tx].s)}. Actual = consumption already made (FIFO estimated); Potential = not yet consumed at the latest local price; Benchmark = CBOT comparison, separate from savings.`;
  const bases = [...new Set(v.contracts.map(c => c.base))].sort(), byB = groupBy(v.sav, r => r.base);
  $("chCom").innerHTML = hbar(bases.filter(b => byB[b]).map(b => scItem(b, byB[b])).filter(i => i.value || i.value2), {left: 90, aria: "Savings by commodity"});
  $("chComCbot").innerHTML = hbar(bases.map(b => { const r = v.cb.filter(x => x.base === b && x.assessable), val = sum(r, x => x.usd);
    return {label: b, value: val, color: val >= 0 ? "var(--good)" : "var(--bad)", tip: `<b>${b}</b><br>${money("USD", val)} net on ${f0(sum(r, x => x.mt))} MT`}; }).filter(i => i.value), {left: 90, aria: "CBOT by commodity"});
  const byC = groupBy(v.sav, r => r.contract_id);
  const top = Object.entries(byC).map(([id, r]) => [id, r, aggS(r, P_).sav]).filter(x => isN(x[2]) && x[2] > 0).sort((a, b) => b[2] - a[2]).slice(0, 10);
  $("chTop").innerHTML = hbar(top.map(([id, r]) => scItem(CI[id].contract, r, {id})), {aria: "Top savings"});
  const pc = {};
  v.cb.filter(r => r.assessable).forEach(r => { pc[r.contract_id] = (pc[r.contract_id] || 0) + r.usd; });
  const miss = Object.entries(pc).filter(([, x]) => x < 0).sort((a, b) => a[1] - b[1]).slice(0, 10);
  $("chMiss").innerHTML = hbar(miss.map(([id, x]) => ({label: CI[id].contract, value: Math.abs(x), id, color: "var(--bad)", tip: `<b>${esc(CI[id].contract)}</b><br>Missed ${money("USD", Math.abs(x))} vs CBOT on its consumption days`})), {aria: "Top missed", fmt: x => "−" + short(x)});
}

// ── contracts tab ────────────────────────────────────────────────────
function ccols() {
  const L_ = scs();
  return [{h: "Contract", v: c => c.contract}, {h: "Supplier", v: c => c.supplier}, {h: "Commodity", v: c => c.commodity},
    {h: "Status", v: c => c.status}, COL.storage, {h: "Consumed MT", n: 1, v: c => c.x.mt, tot: rs => sum(rs, c => c.x.mt)},
    ...L_.flatMap(sc => [{h: `Savings ${sc.h} EGP`, n: 1, na: 1, v: c => c.x[sc.k].sav, col: 1, tot: rs => sum(rs, c => c.x[sc.k].sav)},
      {h: `EGP/MT ${sc.h}`, n: 1, na: 1, v: c => c.x[sc.k].per, col: 1}]),
    COL.premium, COL.futures, COL.fixing, COL.cif, COL.pdate, COL.pstatus,
    {h: "Avg CBOT in consumption", n: 1, v: c => c.x.avg, f: f2},
    {h: "Difference", n: 1, v: c => isN(c.x.avg) && isN(c.fix.value) ? c.x.avg - c.fix.value : null, f: f2, col: 1},
    {h: "CBOT result USD", n: 1, v: c => c.x.amt ? c.x.usd : null, col: 1, tot: rs => sum(rs, c => c.x.amt ? c.x.usd : null)},
    {h: "Oldest local quote", n: 1, v: c => c.x.maxAge, html: c => ageBadge(c.x.maxAge)}];
}
function contractRows(v) {
  const g = groupBy(v.sav, r => r.contract_id), cb = {};
  v.cb.forEach(r => { if (!r.assessable) return; const s = cb[r.contract_id] = cb[r.contract_id] || {mt: 0, usd: 0, w: 0}; s.mt += r.mt; s.usd += r.usd; s.w += r.cbot * r.mt; });
  return v.contracts.filter(c => c.consumed_mt > 0).map(c => { const r = g[c.id] || [], ages = r.map(x => x.local_age).filter(isN);
    return Object.assign(c, {x: {mt: c.consumed_mt, incl: aggS(r, SCN.incl), excl: aggS(r, SCN.excl), rows: r,
      maxAge: ages.length ? Math.max(...ages) : null, staleMt: sum(r.filter(x => x.local_stale), x => x.mt),
      amt: (cb[c.id] || {}).mt || 0, usd: (cb[c.id] || {}).usd || 0, avg: cb[c.id] ? cb[c.id].w / cb[c.id].mt : null}}); });
}
function sortBy(rows, key, cols) {
  const st = S.sort[key]; if (!st || !cols[st.i]) return rows; const col = cols[st.i];
  return rows.slice().sort((a, b) => { const x = col.v(a), y = col.v(b), nx = x == null || x === "", ny = y == null || y === "";
    if (nx && ny) return 0; if (nx) return 1; if (ny) return -1; return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * st.dir; });
}
function thead(key, cols) {
  const st = S.sort[key] || {};
  return "<thead><tr>" + cols.map((c, i) => `<th class="${c.n ? "n" : ""}" data-sort="${key}" data-i="${i}">${esc(c.h)}${st.i === i ? (st.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr></thead>";
}
function renderContracts(v) {
  const cols = ccols(), P_ = PS();
  let rows = contractRows(v);
  if (!S.sort.c) rows.sort((a, b) => (isN(b.x[P_.k].sav) ? b.x[P_.k].sav : -1e18) - (isN(a.x[P_.k].sav) ? a.x[P_.k].sav : -1e18)); else rows = sortBy(rows, "c", cols);
  let s = thead("c", cols) + "<tbody>";
  rows.forEach(c => {
    s += `<tr class="row" data-id="${esc(c.id)}" id="r-${esc(c.id)}">` + cols.map(col => cell(col, c)).join("") + "</tr>";
    if (S.open.has(c.id)) s += `<tr class="det"><td colspan="${cols.length}">${detail(c, v)}</td></tr>`;
  });
  s += totRow(cols, rows, `Total · ${rows.length} contracts`) + "</tbody>";
  $("tC").innerHTML = s;
}
const dl = p => "<dl>" + p.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${x}</dd>`).join("") + "</dl>";
function detail(c, v) {
  const h = c.hist, cb = c.cbot, f = c.fix, rows = v.cb.filter(r => r.contract_id === c.id), srows = v.sav.filter(r => r.contract_id === c.id), L_ = scs();
  const o = M.open.find(r => r.contract_id === c.id), ages = srows.map(r => r.local_age).filter(isN);
  const ov = dl([["Contract", esc(c.contract)], ["Supplier", esc(c.supplier)], ["Commodity / origin", esc(c.commodity + " · " + (c.origin || "—"))],
    ["Quantity", f0(c.qty_mt) + " MT"], ["Delivery", esc(c.delivery_date || "—") + `<br><span class="note">${esc(c.delivery_status)}</span>`],
    ["Storage start", storageCell(c)], ["Receipt", esc(c.receipt_status)], ["Source", esc(c.source_id)]]);
  const fxLine = fx(c.fx, 4) + ` <span class="note">${esc(c.fx_basis)}</span>` + (c.form4_fx ? `<br><span class="note">Form 4 ${fx(c.form4_fx, 4)} · ${esc(c.form4_date || "date not recorded")}</span>` : (c.is_open ? '<br><span class="note">Form 4: Pending / Not recorded</span>' : ""));
  const pr = dl([["Pricing status", pTag(c.pricing_class)], ["Premium", premCell(c.premium, f.unit || c.premium_label, c.pricing_class)], ["Futures month", esc(futCode(c))],
    ["CBOT fixing", fixCell(c)], ["Pricing / fixing date", pdate(c) ? esc(pdate(c)) : '<span class="note">Not recorded</span>'], ["CIF USD/MT", cifCell(c)], ["FX EGP/USD", fxLine],
    ["Landed EGP/MT", f2(c.landed_egp_mt) + ` <span class="note">incl. transport</span>`],
    ["Import inland transport", isN(c.freight_egp_mt) ? f2(c.freight_egp_mt) + " EGP/MT" : NA_]]);
  const lo = dl([["Consumed", f0(c.consumed_mt) + " MT"], ["Compared vs local", f0(sum(srows, r => r.mt)) + " MT"], ["Period", esc((c.first_date || "—") + " → " + (c.last_date || "—"))],
    ...L_.flatMap(sc => { const A = aggS(srows, sc); return [[`Wtd avg local ${sc.h}`, f2(A.local)], [`Landed ${sc.h}`, f2(A.cost)],
      [`Savings EGP/MT ${sc.h}`, `<span class="${sg(A.per)}">${isN(A.per) ? f2(A.per) : "N/A"}</span>`], [`Total savings ${sc.h}`, `<b class="${sg(A.sav)}">${isN(A.sav) ? money("EGP", A.sav) : "N/A — Missing Source Data"}</b>`]]; }),
    ["Oldest local quote used", ageBadge(ages.length ? Math.max(...ages) : null)], ["MT on quotes > " + CD() + " days", f0(sum(srows.filter(r => r.local_stale), r => r.mt))],
    ["Basis", c.cif_final ? '<span class="tag act">Final CIF</span>' : '<span class="tag pot">Provisional CIF</span>']]);
  const cbx = f.fixed ? dl([["CBOT fixed", `<b>${f2(f.value)}</b> ${esc(f.unit)}`], ["Type", esc(f.status)], ["Pricing date", esc(f.pricing_date || "Not recorded")],
    ["Futures month", esc(futCode(c))], ["Premium / factor", f2(c.premium) + " / " + fx(f.factor, 4)], ["Avg CBOT, consumption days", f2(cb.avg_cbot)], ["Coverage", isN(cb.coverage) ? fx(cb.coverage * 100, 0) + "% of consumed MT" : "—"],
    ["Result", `<b class="${sg(cb.usd)}">${money("USD", cb.usd)}</b> · ${esc(cb.assessment)}`]])
    : `<p class="note">${esc(f.status || "No CBOT fixing")}${isN(f.indicative) ? ` — indicative ${f2(f.indicative)} ${esc(f.unit)} (not a final fixing)` : ""}</p>`;
  const op = o ? dl([["Delivered", f0(c.delivered_mt) + " MT"], ["Consumed", f0(c.consumed_mt) + " MT"], ["Available stock", f0(c.available_mt) + " MT"], ["Outstanding", f0(c.outstanding_mt) + " MT"],
      ["Remaining (unconsumed)", `<b>${f0(o.unconsumed_mt)} MT</b>`], ["Valuation", valTag(o)], ["CIF basis", esc(o.cif_basis)], ["FX basis", esc(o.fx_basis) + (o.fx_date ? ` · ${esc(o.fx_date)}` : "")],
      ...L_.flatMap(sc => [[`Imported ${sc.h}`, isN(sc.ocost(o)) ? f2(sc.ocost(o)) : NA_], [`Local ${sc.h}`, isN(sc.olocal(o)) ? f2(sc.olocal(o)) : NA_], [`Potential ${sc.h}`, isN(sc.pot(o)) ? `<b class="${sg(sc.pot(o))}">${money("EGP", sc.pot(o))}</b>` : NA_]]),
      ["Latest local quote", esc(o.local_date || "—") + "<br>" + ageBadge(o.local_age)]])
    : dl([["Delivered", f0(c.delivered_mt) + " MT"], ["Consumed", f0(c.consumed_mt) + " MT"], ["Available stock", f0(c.available_mt) + " MT"], ["Outstanding", f0(c.outstanding_mt) + " MT"]]);
  const flags = (c.flags || []).length ? `<div class="assess warnbox"><b>Reconciliation flags.</b> ${c.flags.map(esc).join(" · ")} — kept as recorded, not deleted or reclassified.</div>` : "";
  return `<div class="detwrap"><div class="panels"><div class="pn"><h4>Contract overview</h4>${ov}</div><div class="pn"><h4>Pricing &amp; landed cost</h4>${pr}</div><div class="pn"><h4>Savings vs local market</h4>${lo}</div><div class="pn"><h4>CBOT pricing (benchmark)</h4>${cbx}</div><div class="pn"><h4>${o ? "Current valuation" : "Position"}</h4>${op}</div></div>
   <div class="grid2" style="margin-top:10px"><div class="pn"><h4>Savings waterfall — compared tonnes</h4><div class="wf">${L_.map(sc => `<div>${waterfall(srows, sc)}</div>`).join("")}</div><p class="note">The CBOT result is a separate benchmark and is not part of this saving.</p></div>
   <div class="pn"><h4>CBOT fixed vs consumption</h4>${f.fixed ? cbotChart(c, rows) : '<p class="note">Not applicable.</p>'}</div></div>
   ${flags}<div class="assess"><b>Final assessment.</b> ${esc(c.assessment)}</div></div>`;
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
function cbotCellO(r) {
  if (flatC(r.pricing_class)) return '<span class="note">— flat price</span>';
  const a = isN(r.fixed_cbot) ? `${f2(r.fixed_cbot)} <span class="tag ${r.fix_type === "Implied" ? "pot" : "act"}">${r.fix_type === "Implied" ? "Implied CBOT Fixing" : "Fixed"}</span>` : '<span class="tag pot">Not fixed</span>';
  const b = isN(r.latest_cbot) ? `<br><span class="note">latest ${f2(r.latest_cbot)} · ${esc(r.latest_cbot_date)}</span>` : "";
  const px = /proxy/i.test(r.cbot_note || "") ? `<br><span class="tag pot" title="${esc(r.cbot_note)}">Proxy series</span>` : "";
  return a + b + px;
}
function cifCellO(r) {
  if (!isN(r.cif)) return NA_;
  const b = r.cif_basis || "", lab = b.startsWith("Final") ? "Final CIF" : b.startsWith("Contract") ? "Contract CIF (flat)" : b.startsWith("Indicative") ? "Indicative CIF" : "Provisional CIF";
  return `${f2(r.cif)}<br><span class="tag ${/^(Final|Contract)/.test(b) ? "good" : "pot"}" title="${esc(b)}">${lab}</span>`;
}
function fxCellO(r) {
  if (!isN(r.fx)) return NA_;
  const f4 = r.form4_status === "Recorded", lat = (r.fx_basis || "").startsWith("Latest");
  return `${fx(r.fx, 4)}<br><span class="tag ${f4 ? "good" : "pot"}" title="${esc(r.fx_basis)}">${f4 ? "Form 4" : lat ? "Latest Market FX — Provisional" : esc(r.fx_basis)}</span>` +
    `<br><span class="note">${esc(r.fx_date || "")}${f4 ? "" : " · Form 4: " + esc(r.form4_status)}</span>`;
}
function valTag(r) {
  const b = obucket(r);
  if (b === "c") return '<span class="tag good">Confirmed — fixed price</span>';
  if (b === "i") return `<span class="tag pot">${esc(r.class)}</span>`;
  return `<span class="tag bad">${esc(r.class)}</span>${r.issues && r.issues.length ? `<br><span class="note">${esc(r.issues.join("; "))}</span>` : ""}`;
}
function oresult(r) { const p = PS().oper(r); return !isN(p) ? "na" : p < 0 ? "dear" : "save"; }
function resultTag(r) {
  const L_ = scs(), parts = L_.map(sc => { const p = sc.oper(r); return [sc, !isN(p) ? "na" : p < 0 ? "dear" : "save"]; });
  const lab = {save: '<span class="tag good">Saving</span>', dear: '<span class="tag bad">Dearer than local</span>', na: '<span class="tag">Not assessable</span>'};
  let t = parts.every(x => x[1] === parts[0][1]) ? lab[parts[0][1]] : parts.map(([sc, k]) => lab[k] + ` <span class="note">${sc.h}</span>`).join("<br>");
  if (obucket(r) === "i") t += '<br><span class="tag pot">Provisional</span>';
  return t;
}
const orow = r => { const b = obucket(r), k = oresult(r); return b === "x" || k === "na" ? "rx" : k === "dear" ? "rd" : b === "i" ? "rp" : "rs"; };
function ocols() {
  const L_ = scs();
  return [
    {h: "Contract / Supplier", v: r => r.contract, html: r => `<b>${esc(r.contract)}</b><br><span class="note">${esc(r.supplier)} · ${esc(r.contract_id)}</span>`},
    {h: "Commodity / Origin", v: r => r.commodity, html: r => `${esc(r.commodity)}<br><span class="note">${esc(r.origin || "—")}</span>`},
    {h: "Qty MT", n: 1, v: r => r.qty_mt, tot: rs => sum(rs, r => r.qty_mt)},
    {h: "Remaining MT", n: 1, v: r => r.unconsumed_mt, html: r => `<b>${f0(r.unconsumed_mt)}</b><br><span class="note">stock ${f0(r.available_mt)} · outstanding ${f0(r.outstanding_mt)}</span>`, tot: rs => sum(rs, r => r.unconsumed_mt)},
    {h: "Storage start", v: r => r.storage_start, html: storageCell},
    {h: "Premium / Futures", n: 1, v: r => r.premium, html: r => flatC(r.pricing_class) ? '<span class="note">— flat price</span>' : `${premCell(r.premium, r.unit, r.pricing_class)}<br><span class="note">${esc(r.futures || "—")}</span>`},
    {h: "Fixed / Latest CBOT", n: 1, v: r => isN(r.fixed_cbot) ? r.fixed_cbot : r.latest_cbot, html: cbotCellO},
    {h: "Final / Indicative CIF $/MT", n: 1, v: r => r.cif, html: cifCellO},
    {h: "Form 4 / Latest FX", n: 1, v: r => r.fx, html: fxCellO},
    ...L_.flatMap(sc => [{h: `Imported cost ${sc.h}`, n: 1, na: 1, v: sc.ocost, f: f2}, {h: `Local ${sc.h}`, n: 1, na: 1, v: sc.olocal, f: f2}]),
    {h: "Local date / age", v: r => r.local_age, html: r => (r.local_date ? esc(r.local_date) + "<br>" : "") + ageBadge(r.local_age)},
    ...L_.map(sc => ({h: `Savings/MT ${sc.h}`, n: 1, na: 1, v: sc.oper, f: f2, col: 1})),
    ...L_.map(sc => ({h: `Total potential ${sc.h}`, n: 1, na: 1, v: sc.pot, col: 1, tot: rs => sum(rs, sc.pot)})),
    {h: "Result", v: r => oresult(r), html: resultTag},
    {h: "Pricing status", v: r => r.pricing_class, html: r => pTag(r.pricing_class)},
    {h: "Valuation status", v: r => obucket(r) + r.class, html: valTag}];
}
function renderOpen(v) {
  const K = kpis(v), cols = ocols(), L_ = scs(), P_ = PS();
  const fb = $("oBucket").value, fr = $("oRes").value, rem = $("oRem").value;
  let rows = v.op.filter(r => (!fb || obucket(r) === fb) && (!fr || oresult(r) === fr) && (!rem || r.unconsumed_mt > 0));
  rows = S.sort.o ? sortBy(rows, "o", cols) : rows.slice().sort((a, b) => (isN(P_.pot(b)) ? P_.pot(b) : -1e18) - (isN(P_.pot(a)) ? P_.pot(a) : -1e18));
  const latest = v.op.map(r => r.local_date).filter(Boolean).sort().pop() || "—";
  const ranked = v.op.filter(r => isN(P_.oper(r)) && r.unconsumed_mt > 0).sort((a, b) => P_.oper(b) - P_.oper(a));
  const provFx = v.op.filter(r => (r.fx_basis || "").startsWith("Latest")).length, stale = v.op.filter(r => r.local_stale).length;
  $("okpis").innerHTML = [
    kcardS("Confirmed potential (fixed price)", sc => [K[sc.of], money("EGP", K[sc.of])], '<span class="tag pot">Potential</span>', `${f0(K.open_fixed_mt)} MT not yet consumed · fixed CIF with Form 4`),
    kcardS("Indicative / provisional", sc => [K[sc.oi], money("EGP", K[sc.oi])], '<span class="tag">Scenario</span>', `${f0(K.open_indicative_mt)} MT · unpriced CBOT, provisional FX or not yet received · not in the confirmed total`),
    kcard("Quantities", K.open_available_mt, `${f0(K.open_available_mt)} MT`, '<span class="tag">Position</span>', `in stock on open contracts · ${f0(K.open_outstanding_mt)} MT outstanding · ${f0(sum(v.op, r => r.unconsumed_mt))} MT not yet consumed incl. closed-contract stock · ${f0(K.open_not_received_mt)} MT not confirmed received · latest local quote ${esc(latest)}`),
    kcard("Valuation inputs", null, `${provFx} provisional FX`, '<span class="tag">Inputs</span>', `${provFx} contract${provFx === 1 ? "" : "s"} on the latest market FX (Form 4 pending) · ${stale} on a local quote more than ${CD()} days old · ${v.op.filter(r => obucket(r) === "x").length} not assessable`),
  ].join("") + (ranked.length ? kcard(`Best / worst remaining · ${P_.s}`, P_.oper(ranked[0]), esc(ranked[0].contract), "", `best ${f2(P_.oper(ranked[0]))} EGP/MT · worst ${esc(ranked[ranked.length - 1].contract)} ${f2(P_.oper(ranked[ranked.length - 1]))} EGP/MT`) : "");
  $("chOpen").innerHTML = dumbbell(v.op.filter(r => r.unconsumed_mt > 0));
  const conf = rows.filter(r => obucket(r) === "c"), ind = rows.filter(r => obucket(r) === "i"), exc = rows.filter(r => obucket(r) === "x");
  $("tO").innerHTML = thead("o", cols) + "<tbody>" + rows.map(r => `<tr class="row ${orow(r)}" data-goto="${esc(r.contract_id)}">` + cols.map(col => cell(col, r)).join("") + "</tr>").join("") +
    totRow(cols, conf, `Confirmed total · ${conf.length}`) + totRow(cols, ind, `Indicative / provisional · ${ind.length} (separate)`) +
    (exc.length ? `<tr><td colspan="${cols.length}" class="note">${exc.length} row${exc.length > 1 ? "s" : ""} not assessable (N/A — Missing Source Data) — left out of both totals: ${exc.map(r => esc(r.contract) + " (" + esc((r.issues || []).join("; ") || r.class) + ")").join(", ")}.</td></tr>` : "") + "</tbody>";
}

// ── data quality tab ─────────────────────────────────────────────────
function renderQuality() {
  const q = M.quality, tiles = [
    ["", "Verified (actual) allocations", q.verified_allocations, "rows"], ["", "FIFO-estimated allocations", q.fifo_allocations, "rows"],
    ["Unsourced consumption", "Excluded unsourced", q.excluded_unsourced, `rows · ${f0(q.excluded_unsourced_mt)} MT`],
    ["missing-dates", "Fixed contracts without a pricing date", q.missing_pricing_dates, "fixing implied from CIF"],
    ["CBOT comparison not assessable", "Days without a stored CBOT", q.missing_cbot, `rows · ${f0(q.missing_cbot_mt)} MT`],
    ["No usable local price", "Missing local observations", q.missing_local, `rows · ${f0(q.missing_local_mt)} MT`],
    ["stale", "Days on the last local price in force", q.carried_local, `rows · ${f0(q.carried_local_mt || 0)} MT · no new quote = no change`],
    ["stale5", `Days on local quotes > ${CD()} days old (STALE)`, q.stale_local, `rows · ${f0(q.stale_local_mt || 0)} MT · still used, flagged orange`],
    ["missing-storage", "Contracts without a storage start", q.missing_storage, "shown as Not recorded · never assumed"],
    ["Reconciliation flag", "Reconciliation flags", q.reconciliation_flags, "kept as recorded, not deleted"],
    ["prov-fx", "Open contracts on provisional FX", q.provisional_fx_open, "latest market FX · Form 4 pending"],
    ["not-received", "Open contracts not confirmed received", q.not_received_open, "current market valuation"],
    ["Logged entry not used", "Logged entries not used", M.excluded.filter(e => e.category === "Logged entry not used").length, "see reason"]];
  $("dqTiles").innerHTML = tiles.map(([k, l, val, sub]) => `<button data-dq="${esc(k)}" class="${S.dqTile === k && k ? "on" : ""}"><div class="v">${f0(val)}</div><div class="l">${esc(l)}<br>${esc(sub)}</div></button>`).join("");
  $("checks").innerHTML = `<p><span class="badge ${M.management_ready ? "ok" : "no"}">${M.management_ready ? "✔ Management-ready" : "✖ Not management-ready"}</span> <span class="note">checksum ${esc(M.checksum)} — the Excel workbook prints the same</span></p>` +
    M.validation.map(x => `<div class="check"><span class="r ${x.passed ? "pos" : "neg"}">${x.passed ? "✔ PASS" : "✖ FAIL"}</span><span><b>${esc(x.check)}</b><br><span class="note">${esc(x.detail)}</span></span></div>`).join("");
  $("tAudit").innerHTML = `<thead><tr><th>Commodity</th><th class="n">Total consumed MT</th><th class="n">Sourced allocated MT</th><th class="n">Excluded / unallocated MT</th><th class="n">Difference</th></tr></thead><tbody>` +
    M.audit.map(a => `<tr><td>${esc(a.base)}</td>${td(a.consumed_mt)}${td(a.allocated_mt)}${td(a.excluded_mt)}${td(a.difference_mt)}</tr>`).join("") + "</tbody>";
  let ex = M.excluded, title = "Excluded & missing data";
  if (S.dqTile === "missing-dates") { ex = C.filter(c => c.fix.fixed && !c.fix.pricing_date_known).map(c => ({category: "Pricing date not recorded", contract: c.contract, contract_id: c.id, commodity: c.base, reason: `CBOT fixing implied from CIF ${f2(c.cif_usd_mt)} ÷ ${c.fix.factor} − premium ${f2(c.premium)} = ${f2(c.fix.value)}; the date it was fixed is not stored.`, source: c.source_id})); title = "Fixed contracts without a pricing date"; }
  else if (S.dqTile === "stale5") { ex = M.savings.filter(r => r.local_stale).map(r => ({category: `Local Market Price — ${r.local_age} Days Old — STALE`, date: r.date, contract: r.contract, contract_id: r.contract_id, commodity: r.base, mt: r.mt, reason: `Local quote of ${r.local_date} (${r.local_key}) used ${r.local_age} days later; no newer quote was entered, so it stays in force.`, source: r.local_source})); title = `Days on local quotes more than ${CD()} days old`; }
  else if (S.dqTile === "missing-storage") { ex = C.filter(c => !c.storage_start && (c.consumed_mt > 0 || c.is_open)).map(c => ({category: "Storage start not recorded", contract: c.contract, contract_id: c.id, commodity: c.base, mt: c.qty_mt, reason: `${c.receipt_status}. Delivery date ${c.delivery_date || "—"} is not used as the storage date.`, source: c.source_id})); title = "Contracts without a storage start"; }
  else if (S.dqTile === "prov-fx") { ex = M.open.filter(r => (r.fx_basis || "").startsWith("Latest")).map(r => ({category: "Latest market FX — provisional", date: r.fx_date, contract: r.contract, contract_id: r.contract_id, commodity: r.base, mt: r.unconsumed_mt, reason: `FX ${fx(r.fx, 4)} from the daily FX of ${r.fx_date}; Form 4 ${r.form4_status}. Switches to Form 4 automatically once entered.`, source: "fx_history"})); title = "Open contracts on provisional FX"; }
  else if (S.dqTile === "not-received") { ex = M.open.filter(r => !r.received).map(r => ({category: r.receipt_status, contract: r.contract, contract_id: r.contract_id, commodity: r.base, mt: r.unconsumed_mt, reason: `${r.class}: valued at the latest local price, FX and CBOT.`, source: ""})); title = "Open contracts not confirmed received"; }
  else if (S.dqTile === "stale") { ex = M.savings.filter(r => !r.local_status.startsWith("Same")).map(r => ({category: r.local_status, date: r.date, contract: r.contract, contract_id: r.contract_id, commodity: r.base, mt: r.mt, reason: `Local price set on ${r.local_date} still in force (${r.local_age} days, no new price entered = no change).`, source: r.local_source})); title = "Days on the last local price in force"; }
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
   <p>Local: origin-matched local market quote observed on or before the day; the last quote entered stays in force until the next one (no new quote = no change), shown with its date and age. A quote more than ${CD()} days old is marked <span class="stale">Local Market Price — N Days Old — STALE</span> but still used; days with no earlier quote are excluded as missing. Latest quotes: ${esc(Object.entries(src.local_latest || {}).map(([k, x]) => k + " " + x).join(" · "))}.</p>
   <p>Transport scenarios: including = landed cost with inland freight vs local quote + local transport; excluding = landed cost without inland freight vs the local quote itself. Each side uses its own recorded transport; ocean freight stays in CIF. Missing transport is shown as N/A — Missing Source Data, never as zero, and left out of that scenario's totals.</p>
   <p>Landed cost: CIF × FX + discharge + clearance (+ inland freight when including transport). FX: Form 4 once entered (all commodities except SBM); historical rows keep their recorded basis; open contracts without Form 4 use the latest daily market FX ("Latest Market FX — Provisional") and switch automatically once Form 4 is entered. CBOT fixed: pricing lots, else Implied CBOT Fixing = CIF ÷ factor − premium (CORN 0.3937; SOYBEAN, WHEAT 0.36745; SBM 1.1023 with premium in $/short ton), so Final CIF = (fixed CBOT + premium) × factor. Unpriced contracts are never shown as fixed: their open tonnes are valued at (latest stored CBOT + premium) × factor, labelled a proxy when that series is not the contract's own futures month. Flat-priced contracts keep their contract CIF.</p>
   <p>Storage start dates are shown as recorded (Not recorded when absent) and never taken from the delivery date. A contract with no storage start and no receipt is not treated as received: it gets a current market valuation and stays out of the FIFO stock; consumption already allocated to one is flagged for reconciliation, not deleted. Historical savings, current open potential and the CBOT benchmark are separate measures and are never added together.</p>`;
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
  const v = view(), K = kpis(v), F_ = v.f, L_ = scs(), NA = "N/A — Missing Source Data", nv = x => isN(x) ? x : NA;
  const ageTxt = a => !isN(a) ? "No local quote — missing data" : a > CD() ? `Local Market Price — ${a} Days Old — STALE` : a === 0 ? "Same day" : a + " days old";
  const sheets = [
    ["Summary", [["Procurement savings — filtered view"], ["Data as of", M.as_of], ["Checksum (unfiltered model)", M.checksum],
      ["Filters", Object.entries(F_).filter(([, x]) => x).map(([k, x]) => k + "=" + x).join("; ") || "none"],
      ["Transport scenario", S.tx === "side" ? "Side-by-side (including and excluding transport)" : SCN[S.tx].l], [],
      ["Measure", "Value"], ...Object.entries(K).map(([k, x]) => [k, x])]],
    ["Contracts", [["Contract ID", "Contract", "Supplier", "Commodity", "Origin", "Status", "Storage Start", "Receipt Status", "Consumed MT",
        ...L_.flatMap(sc => [`Compared MT ${sc.h}`, `Savings EGP ${sc.h}`, `Savings EGP/MT ${sc.h}`]),
        "Premium", "Premium Unit", "Futures Month", "CBOT Fixing", "Fixing Type", "Final CIF USD/MT", "CIF Basis", "Pricing / Fixing Date", "Pricing Status",
        "FX", "FX Basis", "Form 4 Date", "Avg CBOT consumption days", "CBOT net USD", "Oldest Local Quote (days)", "MT on Quotes > 5 Days", "Reconciliation Flags", "Assessment"],
      ...contractRows(v).map(c => [c.id, c.contract, c.supplier, c.commodity, c.origin, c.status, c.storage_start || "Not recorded", c.receipt_status, c.consumed_mt,
        ...L_.flatMap(sc => [c.x[sc.k].mt, nv(c.x[sc.k].sav), nv(c.x[sc.k].per)]),
        flatC(c.pricing_class) ? "flat price" : nv(c.premium), c.fix.unit || c.premium_label, futCode(c), c.fix.fixed ? c.fix.value : (flatC(c.pricing_class) ? "flat price" : "Not fixed"),
        c.fix.type === "Implied" ? "Implied CBOT Fixing" : c.fix.type === "Recorded" ? "Recorded fixing (lots)" : c.fix.type, nv(c.cif_usd_mt), c.cif_final ? "Final CIF" : "Provisional CIF",
        pdate(c) || "Not recorded", c.pricing_class, nv(c.fx), c.fx_basis, c.form4_date || "", c.x.avg, c.x.amt ? c.x.usd : null, c.x.maxAge, c.x.staleMt, (c.flags || []).join("; "), c.assessment])]],
    ["Savings vs Local", [["Date", "Contract", "Contract ID", "Commodity", "MT", "Storage Start",
        ...L_.flatMap(sc => [`Landed EGP/MT ${sc.h}`, `Local EGP/MT ${sc.h}`, `Savings EGP/MT ${sc.h}`, `Savings EGP ${sc.h}`]),
        "Import Inland Transport EGP/MT", "Local Transport EGP/MT", "Local date", "Quote age (days)", "Local Price Age Status", "Data quality", "Local record"],
      ...v.sav.map(r => [r.date, r.contract, r.contract_id, r.commodity, r.mt, r.storage_start || "Not recorded",
        ...L_.flatMap(sc => [nv(sc.cost(r)), nv(sc.local(r)), nv(sc.per(r)), nv(sc.sav(r))]),
        nv(r.freight), nv(r.local_transport), r.local_date, r.local_age, ageTxt(r.local_age), r.quality, r.local_source])]],
    ["CBOT vs Consumption", [["Date", "Contract", "Contract ID", "MT", "CBOT fixed", "CBOT that day", "Price date", "Benchmark status", "Difference", "USD/MT", "USD", "EGP", "Result"],
      ...v.cb.map(r => [r.date, r.contract, r.contract_id, r.mt, r.fix, r.cbot, r.cbot_date, r.benchmark, r.diff, r.usd_mt, r.usd, r.egp, r.result])]],
    ["Open vs Local", [["Contract", "Contract ID", "Supplier", "Commodity", "Origin", "Qty MT", "Available MT", "Outstanding MT", "Remaining MT", "Storage Start", "Receipt Status",
        "Premium", "Premium Unit", "Futures Month", "Fixed CBOT", "Latest CBOT", "Latest CBOT Date", "CBOT Note", "CIF USD/MT", "CIF Basis", "FX", "FX Basis", "FX Date", "Form 4 Status",
        "Discharge EGP/MT", "Clearance EGP/MT", "Import Inland Transport EGP/MT", ...L_.flatMap(sc => [`Imported Cost ${sc.h}`, `Local ${sc.h}`]), "Local Date", "Local Age (days)", "Local Price Age Status",
        ...L_.flatMap(sc => [`Savings/MT ${sc.h}`, `Total Potential ${sc.h}`]), "Pricing Status", "Valuation Class", "Totals Bucket", "Issues"],
      ...v.op.map(r => [r.contract, r.contract_id, r.supplier, r.commodity, r.origin, r.qty_mt, r.available_mt, r.outstanding_mt, r.unconsumed_mt, r.storage_start || "Not recorded", r.receipt_status,
        flatC(r.pricing_class) ? "flat price" : nv(r.premium), r.unit, r.futures, isN(r.fixed_cbot) ? r.fixed_cbot : (flatC(r.pricing_class) ? "" : "Not fixed"), r.latest_cbot, r.latest_cbot_date, r.cbot_note,
        nv(r.cif), r.cif_basis, nv(r.fx), r.fx_basis, r.fx_date, r.form4_status,
        r.disc_missing ? "Not recorded" : r.discharge, r.clr_missing ? "Not recorded" : r.clearance, nv(r.freight), ...L_.flatMap(sc => [nv(sc.ocost(r)), nv(sc.olocal(r))]), r.local_date || NA, r.local_age, ageTxt(r.local_age),
        ...L_.flatMap(sc => [nv(sc.oper(r)), nv(sc.pot(r))]), r.pricing_class, r.class,
        {c: "Confirmed", i: "Indicative / provisional", x: "Excluded — missing source data"}[obucket(r)], (r.issues || []).concat(r.notes || []).join("; ")])]]];
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
function svcols() {
  const L_ = scs(), P_ = PS();
  return [{h: "Contract", v: c => c.contract}, {h: "Supplier", v: c => c.supplier}, {h: "Commodity", v: c => c.commodity}, COL.storage,
    COL.premium, COL.futures, COL.fixing, COL.cif, COL.pstatus,
    {h: "Compared MT", n: 1, v: c => c.z.incl.mt, tot: rs => sum(rs, c => c.z.incl.mt)},
    ...L_.flatMap(sc => [{h: `Landed ${sc.h} EGP/MT`, n: 1, na: 1, v: c => c.z[sc.k].cost, f: f2},
      {h: `Wtd avg local ${sc.h} EGP/MT`, n: 1, na: 1, v: c => c.z[sc.k].local, f: f2},
      {h: `Savings ${sc.h} EGP/MT`, n: 1, na: 1, v: c => c.z[sc.k].per, f: f2, col: 1, tf: f2, tot: rs => { const m = sum(rs, c => isN(c.z[sc.k].sav) ? c.z[sc.k].mt : null); return m ? sum(rs, c => c.z[sc.k].sav) / m : null; }},
      {h: `Total savings ${sc.h} EGP`, n: 1, na: 1, v: c => c.z[sc.k].sav, col: 1, tot: rs => sum(rs, c => c.z[sc.k].sav)}]),
    {h: `Savings % ${P_.h}`, n: 1, v: c => isN(c.z[P_.k].sav) && c.z[P_.k].local ? c.z[P_.k].sav / (c.z[P_.k].local * c.z[P_.k].mt) * 100 : null, f: x => isN(x) ? fx(x, 1) + "%" : "—", col: 1},
    {h: "First day", v: c => c.z.first}, {h: "Last day", v: c => c.z.last},
    {h: "Oldest local quote", n: 1, v: c => c.z.maxAge, html: c => ageBadge(c.z.maxAge)},
    {h: `MT on quotes > ${CD()} days`, n: 1, v: c => c.z.staleMt, html: c => c.z.staleMt ? `<span class="stale">${f0(c.z.staleMt)}</span>` : "0", tot: rs => sum(rs, c => c.z.staleMt)},
    {h: "Local quotes", v: c => c.z.q}];
}
function svRows(v) {
  return Object.entries(groupBy(v.sav, r => r.contract_id)).map(([id, rows]) => {
    rows = rows.slice().sort((a, b) => a.date < b.date ? -1 : 1);
    const mt = sum(rows, r => r.mt), same = sum(rows.filter(r => r.local_status.startsWith("Same")), r => r.mt), stale = sum(rows.filter(r => r.local_stale), r => r.mt), ages = rows.map(r => r.local_age).filter(isN);
    return Object.assign(CI[id], {z: {incl: aggS(rows, SCN.incl), excl: aggS(rows, SCN.excl), first: rows[0].date, last: rows[rows.length - 1].date, rows,
      maxAge: ages.length ? Math.max(...ages) : null, staleMt: stale,
      q: [same && `${fx(same / mt * 100, 0)}% same day`, (mt - same - stale) > 0.5 && `${fx((mt - same - stale) / mt * 100, 0)}% last quote ≤ ${CD()} d`, stale && `${fx(stale / mt * 100, 0)}% STALE > ${CD()} d`].filter(Boolean).join(" · ")}});
  });
}
// Local equivalent premium: what the local price that day comes to as a CIF
// premium over that day's CBOT, comparable with the contract's own premium.
function premTip(r) {
  if (!isN(r.eq_premium)) return "";
  return `Local ${f2(r.local_excl)} − port costs ${f2(r.port_costs)} = ${f2(r.local_excl - r.port_costs)} EGP/MT ÷ FX ${fx(r.day_fx, 4)} (${r.day_fx_date}) = ` +
    `${f2((r.local_excl - r.port_costs) / r.day_fx)} $/MT ÷ ${r.premium_factor} = ${f2((r.local_excl - r.port_costs) / r.day_fx / r.premium_factor)} − CBOT ${f2(r.day_cbot)} (${r.day_cbot_date}) = ${f2(r.eq_premium)} ${r.premium_unit}` +
    ` · without removing port costs: ${f2(r.eq_premium_gross)} ${r.premium_unit}`;
}
function premCells(r) {
  if (!r.premium_factor) return '<td class="n na" colspan="5">no CBOT for this commodity</td>';
  const u = ` <span class="note">${esc(r.premium_unit)}</span>`, na = '<td class="n na" title="N/A — Missing Source Data">N/A</td>';
  return (isN(r.day_cbot) ? `<td class="n" title="${esc(r.day_cbot_date)}">${f2(r.day_cbot)}</td>` : na) +
    (isN(r.day_fx) ? `<td class="n" title="${esc(r.day_fx_date)}">${fx(r.day_fx, 4)}</td>` : na) +
    (isN(r.eq_premium) ? `<td class="n" title="${esc(premTip(r))}"><b>${f2(r.eq_premium)}</b>${u}</td>` : na) +
    (isN(r.contract_premium) ? `<td class="n">${f2(r.contract_premium)}${u}</td>` : '<td class="n note">flat price</td>') +
    (isN(r.premium_gap) ? `<td class="n ${sg(r.premium_gap)}">${f2(r.premium_gap)}</td>` : '<td class="n na">—</td>');
}
function premAvg(rows) {
  const w = rows.filter(r => isN(r.eq_premium)), mt = sum(w, r => r.mt), g = w.filter(r => isN(r.premium_gap)), gm = sum(g, r => r.mt);
  return `<td></td><td></td>${mt ? td(sum(w, r => r.eq_premium * r.mt) / mt, f2) : "<td></td>"}<td></td>${gm ? td(sum(g, r => r.premium_gap * r.mt) / gm, f2, 1) : "<td></td>"}`;
}
function renderSavings(v) {
  const cols = svcols(), L_ = scs(), P_ = PS();
  let rows = svRows(v);
  const pv = c => c.z[P_.k].sav, win = rows.filter(c => isN(pv(c)) && pv(c) >= 0), loss = rows.filter(c => isN(pv(c)) && pv(c) < 0);
  const fin = v.sav.filter(r => r.cif_basis === "Final CIF"), st = v.sav.filter(r => r.local_stale);
  $("svKpis").innerHTML = [
    kcardS("Total savings vs local", sc => { const A = aggS(v.sav, sc); return [A.sav, money("EGP", A.sav)]; }, '<span class="tag act">Actual · FIFO estimated</span>',
      L_.map(sc => { const A = aggS(v.sav, sc); return `${sc.h} ${f0(A.mt)} MT · ${isN(A.per) ? f0(A.per) : "—"} EGP/MT`; }).join(" · ") + ` · final CIF ${short(sum(fin, P_.sav))}, provisional ${short(aggS(v.sav, P_).sav - sum(fin, P_.sav))} (${P_.h})`),
    kcard(`Contracts cheaper than local · ${P_.s}`, sum(win, pv), `${win.length} contracts`, '<span class="tag good">Saving</span>', `${money("EGP", sum(win, pv))} on ${f0(sum(win, c => c.z[P_.k].mt))} MT`),
    kcard(`Contracts dearer than local · ${P_.s}`, sum(loss, pv), `${loss.length} contracts`, '<span class="tag bad">Loss</span>', `${money("EGP", sum(loss, pv))} on ${f0(sum(loss, c => c.z[P_.k].mt))} MT`),
    kcard(`Days on local quotes > ${CD()} days old`, null, `${f0(st.length)} day-rows`, '<span class="stale">STALE</span>', `${f0(sum(st, r => r.mt))} MT · ${L_.map(sc => sc.h + " " + money("EGP", aggS(st, sc).sav)).join(" / ")} of the savings · use the Local quote age filter to isolate them`)].join("");
  const bases = [...new Set(rows.map(c => c.base))].sort(), byB = groupBy(v.sav, r => r.base);
  $("svCom").innerHTML = `<thead><tr><th>Commodity</th><th class="n">Contracts</th><th class="n">Compared MT</th>${L_.map(sc => `<th class="n">Landed ${sc.h}</th><th class="n">Local ${sc.h}</th><th class="n">EGP/MT ${sc.h}</th><th class="n">Savings ${sc.h} EGP</th>`).join("")}</tr></thead><tbody>` +
    bases.map(b => { const A = L_.map(sc => aggS(byB[b] || [], sc));
      return `<tr><td><b>${esc(b)}</b></td>${td(rows.filter(c => c.base === b).length)}${td(sum(byB[b] || [], r => r.mt))}${A.map(a => td(a.cost, f2) + td(a.local, f2) + td(a.per, f0, 1) + td(a.sav, f0, 1)).join("")}</tr>`; }).join("") +
    `<tr class="tot"><td>Total</td>${td(rows.length)}${td(sum(v.sav, r => r.mt))}${L_.map(sc => { const a = aggS(v.sav, sc); return td(a.cost, f2) + td(a.local, f2) + td(a.per, f0, 1) + td(a.sav, f0, 1); }).join("")}</tr></tbody>`;
  const ranked = rows.slice().sort((a, b) => (isN(pv(b)) ? pv(b) : -1e18) - (isN(pv(a)) ? pv(a) : -1e18));
  $("svChart").innerHTML = hbar(ranked.map(c => scItem(c.contract, c.z.rows, {id: c.id})), {aria: "Savings by contract", left: 170});
  rows = S.sort.sv ? sortBy(rows, "sv", cols) : ranked;
  let h = thead("sv", cols) + "<tbody>";
  rows.forEach(c => {
    h += `<tr class="row" data-sv="${esc(c.id)}" id="sv-${esc(c.id)}">` + cols.map(col => cell(col, c)).join("") + "</tr>";
    // The daily consumption table keeps its original layout (including transport, age in days).
    if (S.svOpen && S.svOpen.has(c.id)) h += `<tr class="det"><td colspan="${cols.length}"><div class="detwrap" style="overflow-x:auto"><table><thead><tr><th>Date</th><th class="n">MT</th><th class="n">Landed EGP/MT</th><th class="n">Local EGP/MT</th><th>Local quote of</th><th class="n">Age (days)</th><th class="n">Saving EGP/MT</th><th class="n">Saving EGP</th><th class="n">CBOT that day</th><th class="n">FX that day</th><th class="n">Local equiv. premium</th><th class="n">Contract premium</th><th class="n">Premium gap</th><th>Local record</th><th>Data quality</th></tr></thead><tbody>` +
      c.z.rows.map(r => `<tr><td>${esc(r.date)}</td>${td(r.mt)}${td(r.cost, f2)}${td(r.local, f2)}<td>${esc(r.local_date)} <span class="note">${esc(r.local_key)}</span></td>${td(r.local_age)}${td(r.saving_mt, f2, 1)}${td(r.saving, f0, 1)}${premCells(r)}<td>${esc(r.local_source)}</td><td class="note">${esc(r.quality)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total</td>${td(c.z.incl.mt)}${td(c.z.incl.cost, f2)}${td(c.z.incl.local, f2)}<td></td><td></td>${td(c.z.incl.per, f2, 1)}${td(c.z.incl.sav, f0, 1)}${premAvg(c.z.rows)}<td></td><td></td></tr></tbody></table></div></td></tr>`;
  });
  h += totRow(cols, rows, `Total · ${rows.length} contracts`) + "</tbody>";
  $("svT").innerHTML = h;
}

// ── trends & breakdowns ─────────────────────────────────────────────
function vbars(items, o) {
  if (!items.length) return '<p class="note">Nothing to show for this selection.</p>';
  const two = items.some(i => isN(i.value2));
  const W = 640, H = 230, L = 56, R = 10, T = 16, B = 30;
  const vals = items.flatMap(i => isN(i.value2) ? [i.value, i.value2] : [i.value]), mx = Math.max(0, ...vals), mn = Math.min(0, ...vals), sp = (mx - mn) || 1;
  const Y = v => T + (mx - v) / sp * (H - T - B), slot = (W - L - R) / items.length, bw = Math.min(46, slot * 0.7);
  let s = two ? `<div class="legend"><span><i style="background:var(--s1)"></i>Incl. transport</span><span><i style="background:var(--s1l)"></i>Excl. transport</span></div>` : "";
  s += `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria || "bar chart")}">`;
  [mx, (mx + mn) / 2, mn].forEach(v => { s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${short(v)}</text>`; });
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
  items.forEach((it, i) => { const x = L + i * slot + (slot - bw) / 2, y0 = Y(0);
    const col = it.color || (it.value < 0 ? "var(--bad)" : "var(--s1)");
    s += `<g data-tip="${esc(it.tip || "")}"><rect x="${L + i * slot}" y="${T}" width="${slot}" height="${H - T - B}" fill="transparent"/>`;
    const one = (val, xx, w, c) => `<rect x="${xx}" y="${Math.min(y0, Y(val))}" width="${w}" height="${Math.max(Math.abs(Y(val) - y0), val ? 1 : 0)}" rx="3" fill="${c}"/>`;
    if (isN(it.value2)) s += one(it.value, x, bw / 2 - 1, col) + one(it.value2, x + bw / 2 + 1, bw / 2 - 1, it.value2 < 0 ? "var(--badl)" : "var(--s1l)");
    else s += one(it.value, x, bw, col);
    s += "</g>";
    s += `<text class="lbl" x="${x + bw / 2}" y="${H - 12}" text-anchor="middle">${esc(it.label)}</text>`; });
  return s + "</svg>";
}
const monthName = m => { const [y, mm] = m.split("-"); return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mm - 1] + " " + y.slice(2); };
function lines2(rows, o) {
  if (rows.length < 2) return '<p class="note">Not enough consumption days for this selection.</p>';
  // a/b = first scenario (solid); a2/b2 = excluding transport when shown side by side (dashed).
  const two = rows.some(r => isN(r.a2));
  const W = 1200, H = 280, L = 60, R = 16, T = 14, B = 30;
  const ys = rows.flatMap(r => [r.a, r.b, r.a2, r.b2]).filter(isN), pad = (Math.max(...ys) - Math.min(...ys)) * 0.08 || 50;
  const lo = Math.min(...ys) - pad, hi = Math.max(...ys) + pad, t0 = Date.parse(rows[0].d), t1 = Date.parse(rows[rows.length - 1].d), sp = (t1 - t0) || 1;
  const X = d => L + (Date.parse(d) - t0) / sp * (W - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let s = `<div class="legend"><span><i style="background:var(--s1)"></i>${esc(o.a)}</span><span><i style="background:var(--s2)"></i>${esc(o.b)}</span>${two ? `<span><i style="background:transparent;border-top:2px dashed var(--ink2);height:0;border-radius:0"></i>Dashed = excluding transport</span>` : ""}</div><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(o.aria)}">`;
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fx(v, 0)}</text>`; }
  // A gap of more than 4 days without consumption breaks the line rather than bridging it.
  const path = key => { let prev = null; return rows.map(r => { if (!isN(r[key])) { prev = null; return ""; }
    const seg = (prev && Date.parse(r.d) - Date.parse(prev.d) <= 4 * 864e5 ? "L" : "M") + X(r.d).toFixed(1) + "," + Y(r[key]).toFixed(1); prev = r; return seg; }).join(" "); };
  if (two) s += `<path d="${path("b2")}" fill="none" stroke="var(--s2)" stroke-width="1.5" stroke-dasharray="5 4"/><path d="${path("a2")}" fill="none" stroke="var(--s1)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
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
  const L_ = scs(), cbM = {}, byM = groupBy(v.sav, r => r.date.slice(0, 7));
  v.cb.filter(r => r.assessable).forEach(r => { const m = r.date.slice(0, 7), o = cbM[m] = cbM[m] || {u: 0, mt: 0, adv: 0, mis: 0}; o.u += r.usd; o.mt += r.mt; if (r.usd > 0) o.adv += r.usd; else o.mis += r.usd; });
  $("trMonth").innerHTML = vbars(Object.keys(byM).sort().map(m => { const it = scItem(monthName(m), byM[m]); it.label = monthName(m);
    const fin = byM[m].filter(r => r.cif_basis === "Final CIF"); it.tip += `<br>final CIF ${short(sum(fin, PS().sav))} · provisional ${short(aggS(byM[m], PS()).sav - sum(fin, PS().sav))} (${PS().h})`; return it; }), {aria: "Savings by month"});
  $("trCbotMonth").innerHTML = vbars(Object.keys(cbM).sort().map(m => ({label: monthName(m), value: cbM[m].u, color: cbM[m].u >= 0 ? "var(--good)" : "var(--bad)",
    tip: `<b>${monthName(m)}</b><br>Net ${money("USD", cbM[m].u)} on ${f0(cbM[m].mt)} MT<br>advantage ${money("USD", cbM[m].adv)} · missed ${money("USD", cbM[m].mis)}`})), {aria: "CBOT by month"});
  const bases = [...new Set(v.sav.map(r => r.base))].sort();
  const keep = (sel, list, pref) => { const cur = $(sel).value; $(sel).innerHTML = list.map(b => `<option>${esc(b)}</option>`).join(""); $(sel).value = list.includes(cur) ? cur : (list.includes(pref) ? pref : list[0] || ""); };
  keep("trLocBase", bases, "CORN");
  const lb = $("trLocBase").value, day = groupBy(v.sav.filter(r => r.base === lb), r => r.date);
  const dRows = Object.keys(day).sort().map(d => { const A = L_.map(sc => aggS(day[d], sc)); return {d, a: A[0].cost, b: A[0].local, a2: A[1] ? A[1].cost : undefined, b2: A[1] ? A[1].local : undefined, A, mt: sum(day[d], r => r.mt)}; }).filter(r => isN(r.a) && isN(r.b));
  $("trLocal").innerHTML = lines2(dRows,
    {a: `Our landed cost (${L_[0].s})`, b: `Local price that day (${L_[0].s})`, aria: "Local vs landed",
     tip: r => `<b>${r.d}</b> · ${f0(r.mt)} MT<br>` + L_.map((sc, i) => `${sc.l}: landed ${f2(r.A[i].cost)} · local ${f2(r.A[i].local)} · saving <b class="${sg(r.A[i].per)}">${f2(r.A[i].per)} EGP/MT</b>`).join("<br>")});
  const cbBases = Object.keys(M.cbot_series || {}).filter(b => v.contracts.some(c => c.base === b && c.fix.fixed)).sort();
  keep("trCbBase", cbBases, "CORN");
  $("trCbot").innerHTML = $("trCbBase").value ? cbotHistory($("trCbBase").value, v) : '<p class="note">No fixed contracts in this selection.</p>';
  const P_ = PS(), rank = g => Object.entries(g).sort((a, b) => (aggS(b[1], P_).sav || 0) - (aggS(a[1], P_).sav || 0));
  const sup = rank(groupBy(v.sav, r => r.supplier)).slice(0, 12);
  $("trSupplier").innerHTML = hbar(sup.map(([k, r]) => scItem(k, r)), {aria: "Savings by supplier"});
  const org = rank(groupBy(v.sav, r => (CI[r.contract_id] || {}).origin));
  $("trOrigin").innerHTML = hbar(org.map(([k, r]) => scItem(k, r)), {aria: "Savings by origin"});
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
["fBase", "fOrigin", "fSupplier", "fFrom", "fTo", "fOpen", "fFix", "fDQ", "fAge"].forEach(id => $(id).addEventListener("change", render));
["oBucket", "oRes", "oRem"].forEach(id => $(id).addEventListener("change", () => renderOpen(view())));
const TXN = {side: "Side-by-side: including transport = inland transport on both sides; excluding = without it. Ocean freight stays in CIF.",
  incl: "Including transportation: landed cost with inland freight vs local quote + local transport.", excl: "Excluding transportation: landed cost without inland freight vs the local quote itself."};
$("txNote").textContent = TXN.side;
$("txSeg").addEventListener("click", e => { const b = e.target.closest("button[data-tx]"); if (!b) return;
  S.tx = b.dataset.tx; S.sort = {}; document.querySelectorAll("#txSeg button").forEach(x => x.classList.toggle("on", x === b)); $("txNote").textContent = TXN[S.tx]; render(); });
$("fQ").addEventListener("input", render);
$("fPreset").addEventListener("change", e => { const v = e.target.value, end = M.as_of; let start = "";
  if (v === "ytd") start = end.slice(0, 4) + "-01-01"; else if (v) { const d = new Date(end); d.setDate(d.getDate() - +v); start = d.toISOString().slice(0, 10); }
  $("fFrom").value = start; $("fTo").value = v ? end : ""; render(); });
$("bReset").addEventListener("click", () => { ["fBase", "fOrigin", "fSupplier", "fQ", "fFrom", "fTo", "fPreset", "fOpen", "fFix", "fDQ", "fAge", "oBucket", "oRes", "oRem"].forEach(id => $(id).value = ""); render(); });
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
