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
/* A horizontal scrollbar pinned to the bottom of the screen for every wide table (and a second one,
   just above it, for an opened contract's day table), kept in step with the table it belongs to. */
.hbar{position:sticky;bottom:0;left:0;overflow-x:auto;overflow-y:hidden;height:17px;z-index:6;background:var(--card);
  border-top:1px solid var(--line);box-shadow:0 -2px 6px rgba(0,0,0,.06)}
.hbar.inner{position:fixed;bottom:18px;z-index:7;display:none}
.hbar>div{height:1px}
.hbar{scrollbar-width:auto;scrollbar-color:var(--accent,#2f6db5) var(--card)}
.hbar::-webkit-scrollbar{height:14px}.hbar::-webkit-scrollbar-track{background:var(--card)}
.hbar::-webkit-scrollbar-thumb{background:var(--accent,#2f6db5);border-radius:7px;border:3px solid var(--card)}
.hasbar{scrollbar-width:none}.hasbar::-webkit-scrollbar{height:0}
@media print{.hbar{display:none}}
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
#cbSel{max-width:100%}label.note:has(#cbSel){display:block;max-width:100%}
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
 <button class="tab" data-p="actions">Actions &amp; alerts</button>
 <button class="tab" data-p="transport">Transport map</button>
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
 <span class="note" style="margin-left:14px"><b>Port costs</b></span>
 <div class="seg" id="pcSeg" role="group" aria-label="Port costs basis"><button data-pc="actual" class="on">Actual per contract</button><button data-pc="avg">Average for all</button></div>
 <label class="note" style="display:inline-flex;align-items:center;gap:4px">discharge + clearance <input id="pcAvg" type="number" min="0" step="10" value="500" style="width:78px" class="ctl"> EGP/MT</label>
</div>
<div class="filters" id="filters">
 <label>Commodity<select id="fBase"></select></label>
 <label>Origin<select id="fOrigin"></select></label>
 <label>Supplier<select id="fSupplier"></select></label>
 <label>Loading region<select id="fRegion"></select></label>
 <label>Loading place<select id="fPlace"></select></label>
 <label>Contract<input id="fQ" list="dlC" placeholder="number or ID"><datalist id="dlC"></datalist></label>
 <label>From<input type="date" id="fFrom"></label>
 <label>To<input type="date" id="fTo"></label>
 <label>Period<select id="fPreset"><option value="">All dates</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="ytd">Year to date</option></select></label>
 <label>Status<select id="fOpen"><option value="">Open &amp; closed</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
 <label>CBOT fixing<select id="fFix"><option value="">All</option><option value="Recorded">Fixed — recorded lots</option><option value="Implied">Fixed — implied</option><option value="Not fixed">Not fixed (unpriced)</option><option value="other">Flat / not eligible</option></select></label>
 <label>Data quality<select id="fDQ"><option value="">All supported rows</option><option value="final">Final CIF only</option><option value="prov">Provisional CIF only</option><option value="same">Same-day local quote</option><option value="carry">Last local price in force</option></select></label>
 <label>Local quote age<select id="fAge"><option value="">Any age</option><option value="stale-c">Contracts using quotes &gt; 5 days old</option><option value="stale-d">Only days on quotes &gt; 5 days old</option><option value="fresh">Only quotes 0–5 days old</option></select></label>
 <label>Order<select id="fOrder"><option value="">By value (default)</option><option value="new">Newest first</option><option value="old">Oldest first</option></select></label>
 <button class="btn" id="bReset">Reset</button>
</div>
<main>
<div class="card warnbox" id="manBanner" style="display:none;margin-top:10px"></div>
<div class="card warnbox" id="pcBanner" style="display:none;margin-top:10px"></div>
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
 <div class="card"><h2>Not yet consumed — position against local today</h2><p class="sub">Open contracts with tonnes still to consume (including ones not received yet or without a delivery date): what they cost at the CBOT they are valued at (their fixing, else today's CBOT + premium) against the latest local price. <b>Break-even CBOT</b> = the CBOT at which the import would cost the same as local; <b>headroom</b> = how far the CBOT can still rise before local is cheaper — a guide for when to fix. Indicative until priced; not part of the historical savings.</p><div class="tw"><table id="svOpenT"></table></div></div>
</section>

<section class="panel" id="p-contracts">
 <div class="card"><h2>Contract comparison</h2><p class="sub">Consumed contracts. CBOT fixed and the tonne-weighted CBOT on its consumption days side by side. Click a row for the full contract analysis.</p>
 <div class="tw"><table id="tC"></table></div></div>
</section>

<section class="panel" id="p-cbot">
 <div class="kpis" id="cbK"></div>
 <div class="card"><h2>CBOT fixed vs consumption</h2>
  <p class="sub">Our fixed CBOT (reference line) against the stored CBOT on each day the contract was consumed. Green = market above our fixing (advantage), red = below (missed opportunity). Each point is the CBOT stored for that consumption day; hover for the difference, tonnes and USD impact.</p>
  <label class="note">Contract <select class="ctl" id="cbSel"></select></label>
  <div id="cbChart"></div><div id="cbBars"></div><div id="cbSum" class="note"></div><div class="tw" style="margin-top:10px"><table id="cbDays"></table></div>
 </div>
 <div class="card"><h2>Open contracts — premium over CBOT, not yet compared</h2><p class="sub">Open CBOT contracts (including ones not yet received or with no delivery or storage date) have no consumption days to compare yet. Each is shown at the app's live CBOT (the same quote the app uses; the last stored close when the app has no live quote) with the CIF it gives — (CBOT + premium) × factor, final for fixed contracts, indicative for unpriced ones — against today's local price, with the <b>break-even CBOT</b> (where the import would cost the same as local) and the <b>headroom</b> (how far the CBOT can rise before local is cheaper). Click a row for the full valuation.</p><div class="tw"><table id="tCbOpen"></table></div></div>
 <div class="card"><h2>Contract by contract — fixed CBOT vs CBOT on each consumption day</h2><p class="sub">One row per fixed contract: tonne-weighted average CBOT on its consumption days against its fixing. Click a contract to break it down by consumption date and quantity. Saving per day = (CBOT that day − CBOT fixed) × factor × MT; positive = we fixed below the market on the day the tonnes were used (advantage), negative = missed opportunity. A benchmark, never added to the savings vs local.</p><div class="tw"><table id="tCP"></table></div></div>
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

<section class="panel" id="p-actions">
 <div class="kpis" id="akpis"></div>
 <div class="card"><h2>Pricing alerts</h2><p class="sub">Targets set in the app (Pricing alerts…) on contracts not priced yet, checked against the live CBOT and the headroom against today's local price. Triggered first. Click a row to open the contract.</p><div class="tw"><table id="tAl"></table></div></div>
 <div class="card"><h2>Price exposure — tonnes whose cost is not fixed yet</h2><p class="sub">EGP change in import cost for a 10 ¢/bu CBOT move (10 $/short ton for SBM) on tonnes not priced, and for a 1 EGP move in the FX on contracts still without Form 4. A rise makes the import dearer by this amount; a fall saves it.</p><div class="grid2"><div class="tw"><table id="tExC"></table></div><div class="tw"><table id="tExF"></table></div></div></div>
 <div class="card"><h2>Since the last report</h2><p class="sub" id="slSub"></p><div class="tw"><table id="tSl"></table></div></div>
 <div class="card"><h2>Data to fix</h2><p class="sub">Every missing or doubtful input, most important first — fix it on the contract, the freight table or the local prices. Click a row to open the contract.</p><div class="tw"><table id="tFix"></table></div></div>
</section>

<section class="panel" id="p-transport">
 <div class="kpis" id="tmK"></div>
 <div class="card"><h2>Transportation costs map</h2><p class="sub">Inland freight from each loading place to the plants (النوبارية · الصف), from the freight approval in the app (EGP/MT; previous rates apply to deliveries before the effective date). Positions are approximate. Click a loading place to show only its contracts in every tab.</p>
  <div class="ofl"><label>Commodity<select class="ctl" id="tmComm"></select></label>
   <label>Plant<select class="ctl" id="tmDest"><option value="">Both plants</option><option>النوبارية</option><option>الصف</option></select></label>
   <label>Rates<select class="ctl" id="tmVat"><option value="incl">incl. VAT (as used in landed cost)</option><option value="ex">excl. VAT (as in the approval)</option></select></label></div>
  <div id="tmMap"></div></div>
 <div class="grid2">
  <div class="card"><h2>Freight rates</h2><p class="sub" id="tmRatesSub"></p><div class="tw"><table id="tmRates"></table></div></div>
  <div class="card"><h2>Manual transport cost</h2><p class="sub">The report never uses an average: each contract takes its own route freight, and contracts without a route show "add manually". To test a figure, enter it here — an average for all contracts, or one per contract in the table below. Manual entries are a what-if in this page only (kept in this browser); enter the real freight on the contract in the app to make it permanent.</p>
   <div class="ofl"><label>Manual average inland freight, EGP/MT incl. VAT<input class="ctl" type="number" step="0.01" min="0" id="manAvg" placeholder="e.g. 350"></label>
    <label>Apply to<select class="ctl" id="manScope"><option value="missing">Only contracts without route freight</option><option value="all">All contracts (what-if)</option></select></label></div>
   <div class="ofl"><button class="btn primary" id="manApply">Apply</button><button class="btn" id="manClear">Clear manual entries</button><button class="btn" id="manCsv">Download manual freight list (CSV)</button></div>
   <div id="manNote" class="note"></div></div>
 </div>
 <div class="card"><h2>Contracts by loading place</h2><p class="sub">Every contract grouped by where the commodity is taken from, with the freight the report uses and where it comes from. <b>Route table</b> = the approval rate for its commodity, loading place and plant on its delivery date, + VAT; <b>Contract route entry</b> = freight entered on the contract with its route; <b>No route — add manually</b> = no rate can be matched, so its including-transport comparison is left out. "App value" is the freight the app had stored.</p><div class="tw"><table id="tmContracts"></table></div></div>
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
// Loading places (Arabic names as recorded) with approximate positions and their region.
const PLACE_GEO = {"الدخيلة": [31.13, 29.80, "Alexandria · الإسكندرية"], "برج العرب": [30.90, 29.58, "Alexandria · الإسكندرية"],
  "أبو قير": [31.32, 30.07, "Alexandria · الإسكندرية"], "دمياط (ميدسوفتس + A3C)": [31.47, 31.81, "Damietta · دمياط"], "دمياط": [31.22, 31.55, "Damietta · دمياط"],
  "مخازن السلام - مخازن النيل": [30.12, 31.36, "Cairo / Giza · القاهرة والجيزة"], "اكما (مدينة السلام)": [30.19, 31.45, "Cairo / Giza · القاهرة والجيزة"],
  "مدينة السادس من أكتوبر": [29.96, 30.93, "Cairo / Giza · القاهرة والجيزة"], "أبو رواش": [30.05, 31.08, "Cairo / Giza · القاهرة والجيزة"],
  "السادات": [30.37, 30.53, "Sadat · المنوفية"], "النوبارية": [30.67, 30.06, "Beheira · البحيرة"]};
const DEST_GEO = {"النوبارية": [30.67, 30.06], "الصف": [29.57, 31.28]};
const placeOf = c => c.loading_place_map || c.loading_place || "";
const regionOf = p => p ? (PLACE_GEO[p] || [0, 0, "Other"])[2] : "Not recorded";
opts("fRegion", [...new Set(C.map(c => regionOf(placeOf(c))))].sort(), "All regions");
opts("fPlace", [...new Set(C.map(c => placeOf(c) || "Not recorded"))].sort(), "All loading places");
$("dlC").innerHTML = C.map(c => `<option value="${esc(c.contract)}">${esc(c.id)}</option>`).join("");
function F() {
  return {base: $("fBase").value, origin: $("fOrigin").value, supplier: $("fSupplier").value, q: $("fQ").value.trim().toLowerCase(),
          from: $("fFrom").value, to: $("fTo").value, open: $("fOpen").value, fix: $("fFix").value, dq: $("fDQ").value, age: $("fAge").value, order: $("fOrder").value, region: $("fRegion").value, place: $("fPlace").value};
}
function contractOk(c, f) {
  if (f.region && regionOf(placeOf(c)) !== f.region) return false;
  if (f.place && (placeOf(c) || "Not recorded") !== f.place) return false;
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
const SVI = {}; M.savings.forEach(r => { SVI[r.contract_id + "|" + r.date] = r; });
// Local price and equivalent premium of a consumption day, from Savings vs local.
const svOf = r => SVI[r.contract_id + "|" + r.date] || {};
function eqAvg(rows) {
  const w = rows.map(r => [r, svOf(r)]), wt = (k) => { const x = w.filter(([, s]) => isN(s[k])), m = sum(x, ([r]) => r.mt); return m ? sum(x, ([r, s]) => s[k] * r.mt) / m : null; };
  return {local: wt("local"), local_excl: wt("local_excl"), eq: wt("eq_premium"), gap: wt("premium_gap"), eqc: wt("eq_cbot"), eqd: wt("eq_cbot_diff"),
          prem: (w.find(([, s]) => isN(s.contract_premium)) || [{}, {}])[1].contract_premium, unit: (w.find(([, s]) => s.premium_unit) || [{}, {}])[1].premium_unit || ""};
}
const LOCAL_TH = `<th class="n">Local price excl.</th><th class="n">Local price incl.</th><th class="n">Local equiv. premium</th><th class="n">Contract premium</th><th class="n">Premium gap</th><th class="n">Local equiv. CBOT</th><th class="n">Local equiv. CBOT − fixed</th>`;
// Local-equivalent CBOT: the CBOT at which the contract, at its own premium, would have cost the
// same as the local price that day = (local excl. − discharge − clearance) ÷ FX that day ÷ factor − contract premium.
function eqcTip(r) {
  if (!isN(r.eq_cbot)) return "";
  return `Local ${f2(r.local_excl)} − port costs ${f2(r.port_costs)} = ${f2(r.local_excl - r.port_costs)} EGP/MT ÷ FX ${fx(r.day_fx, 4)} = ${f2((r.local_excl - r.port_costs) / r.day_fx)} $/MT ÷ ${r.premium_factor} = ` +
    `${f2((r.local_excl - r.port_costs) / r.day_fx / r.premium_factor)} − contract premium ${f2(r.contract_premium)} = ${f2(r.eq_cbot)} ${r.premium_unit}` + (isN(r.fixed_cbot) ? ` · vs CBOT fixed ${f2(r.fixed_cbot)}: ${r.eq_cbot_diff >= 0 ? "+" : ""}${f2(r.eq_cbot_diff)} (positive = local was dearer than our fixing)` : "");
}
const eqcTds = s => (isN(s.eq_cbot) ? `<td class="n" title="${esc(eqcTip(s))}"><b>${f2(s.eq_cbot)}</b></td>` : '<td class="n na">—</td>') + td(s.eq_cbot_diff, f2, 1);
function localTds(r) {
  const s = svOf(r), u = s.premium_unit ? ` <span class="note">${esc(s.premium_unit)}</span>` : "";
  if (!s.date) return '<td class="na" colspan="7">No Savings vs local row for this day</td>';
  return `${td(s.local_excl, f2)}${td(s.local, f2)}` + (isN(s.eq_premium) ? `<td class="n" title="${esc(premTip(s))}"><b>${f2(s.eq_premium)}</b>${u}</td>` : '<td class="n na">N/A</td>') +
    (isN(s.contract_premium) ? `<td class="n">${f2(s.contract_premium)}${u}</td>` : '<td class="n note">—</td>') + td(s.premium_gap, f2, 1) + eqcTds(s);
}
const localTot = e => `${td(e.local_excl, f2)}${td(e.local, f2)}${td(e.eq, f2)}${td(e.prem, f2)}${td(e.gap, f2, 1)}${td(e.eqc, f2)}${td(e.eqd, f2, 1)}`;
// Cost build-up of one consumption day (a Savings vs local row): CIF × FX + discharge + clearance (+ freight).
const BD_TH = `<th class="n">CIF $/MT</th><th class="n">× FX</th><th class="n">= CIF EGP/MT</th><th class="n">+ Discharge</th><th class="n">+ Clearance</th><th class="n">= Landed excl. transport</th><th class="n">+ Inland freight</th><th class="n">= Landed incl. transport</th>`;
const BD_TH_NOCIF = BD_TH.replace('<th class="n">CIF $/MT</th>', "");
function bdTds(s, noCif) {
  if (!s || !s.date) return `<td class="na" colspan="${noCif ? 7 : 8}">No Savings vs local row for this day</td>`;
  const fee = (v, b, m) => m ? `<td class="n stale" title="Not recorded — cost excludes it">0.00 <span class="note">not recorded</span></td>` : `<td class="n" title="${esc(b || "")}">${f2(v)}</td>`;
  const frB = s.man ? manualFor(CI[s.contract_id] || {})[1] : s.freight_basis;
  const pa = s.port_avg;
  return `${noCif ? "" : td(s.cif_used, f2)}${td(s.fx_used, x => fx(x, 4))}${td(s.cif_egp, f2)}${fee(s.discharge, pa ? "Average discharge + clearance (what-if)" : s.disc_basis, pa ? false : s.disc_missing)}` +
    `${fee(s.clearance, pa ? "included in the average" : s.clr_basis, pa ? false : s.clr_missing)}` +
    `<td class="n"><b>${isN(s.cost_excl) ? f2(s.cost_excl) : "N/A"}</b></td>` +
    (isN(s.freight) ? `<td class="n" title="${esc(frB || "")}">${f2(s.freight)}${s.man ? ' <span class="tag pot">manual</span>' : ""}</td>` : '<td class="n na" title="No route in the freight table — add it manually">N/A</td>') +
    `<td class="n"><b>${isN(s.cost) ? f2(s.cost) : "N/A"}</b></td>`;
}
function bdTot(rows, noCif) {
  const w = (k, rs) => { const x = rs.filter(r => isN(r[k])), m = sum(x, r => r.mt); return m ? sum(x, r => r[k] * r.mt) / m : null; };
  return `${noCif ? "" : td(w("cif_used", rows), f2)}${td(w("fx_used", rows), x => fx(x, 4))}${td(w("cif_egp", rows), f2)}${td(w("discharge", rows), f2)}${td(w("clearance", rows), f2)}${td(w("cost_excl", rows), f2)}${td(w("freight", rows), f2)}${td(w("cost", rows), f2)}`;
}
const STALE_IDS = new Set(M.savings.filter(r => r.local_stale).map(r => r.contract_id).concat(M.open.filter(r => r.local_stale).map(r => r.contract_id)));
// Order filter: newest or oldest first by date; empty = each table's own default (by value).
const ORD = () => $("fOrder").value;
function byOrder(rows, key) {
  const o = ORD(); if (!o) return null; const d = o === "new" ? -1 : 1;
  return rows.slice().sort((a, b) => { const x = key(a) || "", y = key(b) || "";
    if (!x && !y) return 0; if (!x) return 1; if (!y) return -1; return (x < y ? -1 : x > y ? 1 : 0) * d; });
}
const dayOrder = rows => rows.slice().sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0) * (ORD() === "new" ? -1 : 1));
function view() {
  const f = F(), ids = new Set(C.filter(c => contractOk(c, f) && (f.age !== "stale-c" || STALE_IDS.has(c.id))).map(c => c.id));
  const sav = M.savings.filter(r => ids.has(r.contract_id) && inDates(r.date, f) && dqOk(r, f) && ageOk(r, f));
  const cb = M.cbot.filter(r => ids.has(r.contract_id) && inDates(r.date, f));
  const cu = (M.cbot_unfixed || []).filter(r => ids.has(r.contract_id) && inDates(r.date, f));
  const op = M.open.filter(r => ids.has(r.contract_id) && ageOk(r, f));
  return {f, ids, sav, cb, cu, op, contracts: C.filter(c => ids.has(c.id)), filtered: Object.entries(f).some(([k, x]) => k !== "order" && x)};
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
  const openC = v.contracts.filter(c => c.is_open), mt = sum(v.sav.filter(r => isN(r.saving)), r => r.mt), hs = sum(v.sav, r => r.saving);
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
    cbot_win_advantage_usd: sum(v.cb.filter(r => r.win_usd > 0), r => r.win_usd), cbot_win_missed_usd: sum(v.cb.filter(r => r.win_usd < 0), r => r.win_usd),
    cbot_win_net_usd: sum(v.cb, r => r.win_usd), cbot_win_net_egp: sum(v.cb, r => r.win_egp), cbot_win_mt: sum(v.cb.filter(r => isN(r.win_usd)), r => r.mt),
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
  const win = (rows.find(r => isN(r.win_cbot)) || {}).win_cbot;
  const ys = rows.map(r => r.cbot).concat([fix], isN(win) ? [win] : []), pad = (Math.max(...ys) - Math.min(...ys)) * 0.12 || 5;
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
  if (isN(win)) s += `<line x1="${L}" x2="${W - R}" y1="${Y(win)}" y2="${Y(win)}" stroke="var(--s2)" stroke-width="1.5" stroke-dasharray="6 4"/><text class="lbl" x="${L + 4}" y="${Y(win) - 6}">Average CBOT storage date → last consumption ${f2(win)}</text>`;
  s += `<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="${rows.map(r => X(r.date).toFixed(1) + "," + Y(r.cbot).toFixed(1)).join(" ")}"/>`;
  rows.forEach(r => {
    const t = `<b>${esc(r.date)}</b> · ${f0(r.mt)} MT consumed<br>CBOT ${f2(r.cbot)} (price of ${esc(r.cbot_date)}) vs fixed ${f2(fix)}<br>` +
      (r.assessable ? `Difference ${f2(r.diff)} → <b class="${sg(r.usd)}">${money("USD", r.usd)}</b> (${esc(r.result)})` : `Not compared: ${esc(r.benchmark)}`);
    s += `<circle cx="${X(r.date)}" cy="${Y(r.cbot)}" r="${r.assessable ? 4 : 3}" fill="${r.assessable ? "var(--s1)" : "var(--surface)"}" stroke="${r.assessable ? "var(--surface)" : "var(--muted)"}" stroke-width="2" data-tip="${esc(t)}"/>`;
  });
  s += `<text x="${L}" y="${H - 8}">${esc(rows[0].date)}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(rows[rows.length - 1].date)}</text></svg>`;
  return `<div class="legend"><span><i style="background:var(--s1)"></i>Stored CBOT on consumption days</span><span><i style="background:var(--ink)"></i>Our fixed CBOT</span><span><i style="background:var(--s2)"></i>Average from storage date (dashed)</span><span><i style="background:var(--good);opacity:.5"></i>Above fixing (advantage)</span><span><i style="background:var(--bad);opacity:.5"></i>Below fixing (missed)</span></div>` + s;
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
      `${money("EGP", K.cbot_net_egp)} · ${isN(K.cbot_coverage) ? fx(K.cbot_coverage * 100, 0) : "—"}% of fixed-contract tonnes with a stored CBOT · never added to savings<br>Average CBOT storage date → last consumption: <b class="${sg(K.cbot_win_net_usd)}">${money("USD", K.cbot_win_net_usd)}</b> (does not depend on estimated consumption days)`),
  ].join("");
  const q = M.quality, negs = Object.values(groupBy(v.sav, r => r.contract_id)).filter(r => { const a = aggS(r, P_).sav; return isN(a) && a < 0; });
  const lines = [
    `Savings from importing instead of buying locally: ${L_.map(sc => `<b class="${sg(K[sc.hs])}">${money("EGP", K[sc.hs])}</b> ${sc.s} (${isN(K[sc.hpm]) ? f0(K[sc.hpm]) : "—"} EGP/MT)`).join(" and ")} on ${f0(K.historical_mt)} MT consumed, each tonne against the local price in force on its day.`,
    `Fixed-price tonnes not yet consumed would save ${L_.map(sc => `<b class="${sg(K[sc.of])}">${money("EGP", K[sc.of])}</b> ${sc.s}`).join(" / ")} at the latest local price; unpriced or provisional contracts add an indicative ${L_.map(sc => money("EGP", K[sc.oi]) + " " + sc.h).join(" / ")}, kept separate.`,
    `Against the CBOT on the consumption days our fixings gained ${money("USD", K.cbot_advantage_usd)} and missed ${money("USD", Math.abs(K.cbot_missed_usd))} — net <b class="${sg(K.cbot_net_usd)}">${money("USD", K.cbot_net_usd)}</b>; against the average CBOT from each storage date to the last consumption day, net <b class="${sg(K.cbot_win_net_usd)}">${money("USD", K.cbot_win_net_usd)}</b>. A historical benchmark already inside the savings above, never added to them.`,
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
    {h: "① Avg CBOT on consumption days", n: 1, v: c => c.x.avg, html: c => isN(c.x.avg) ? `${f2(c.x.avg)}<br><span class="note">${f0(c.x.amt)} MT with CBOT that day</span>` : "—"},
    {h: "① Difference (vs fixed)", n: 1, v: c => isN(c.x.avg) && isN(c.fix.value) ? c.x.avg - c.fix.value : null, f: f2, col: 1},
    {h: "② Avg CBOT storage → last consumption", n: 1, v: c => c.x.win, html: c => isN(c.x.win) ? `${f2(c.x.win)}<br><span class="note">${esc(c.x.wstart)} → ${esc(c.x.wend)}</span>` : "—"},
    {h: "② Difference (vs fixed)", n: 1, v: c => isN(c.x.win) && isN(c.fix.value) ? c.x.win - c.fix.value : null, f: f2, col: 1},
    {h: "Avg local equiv. CBOT", n: 1, v: c => c.x.eq.eqc, html: c => isN(c.x.eq.eqc) ? `<b>${f2(c.x.eq.eqc)}</b> <span class="note">${esc(c.x.eq.unit)}</span>` : "—"},
    {h: "Local equiv. CBOT − fixed", n: 1, v: c => c.x.eq.eqd, f: f2, col: 1},
    {h: "CBOT result USD", n: 1, v: c => c.x.amt ? c.x.usd : null, col: 1, tot: rs => sum(rs, c => c.x.amt ? c.x.usd : null)},
    {h: "Oldest local quote", n: 1, v: c => c.x.maxAge, html: c => ageBadge(c.x.maxAge)}];
}
function contractRows(v) {
  const g = groupBy(v.sav, r => r.contract_id), cb = {};
  const wn = {};
  v.cb.forEach(r => { if (isN(r.win_cbot) && !wn[r.contract_id]) wn[r.contract_id] = r;
    if (!r.assessable) return; const s = cb[r.contract_id] = cb[r.contract_id] || {mt: 0, usd: 0, w: 0}; s.mt += r.mt; s.usd += r.usd; s.w += r.cbot * r.mt; });
  return v.contracts.filter(c => c.consumed_mt > 0).map(c => { const r = g[c.id] || [], ages = r.map(x => x.local_age).filter(isN);
    return Object.assign(c, {x: {mt: c.consumed_mt, incl: aggS(r, SCN.incl), excl: aggS(r, SCN.excl), rows: r,
      maxAge: ages.length ? Math.max(...ages) : null, staleMt: sum(r.filter(x => x.local_stale), x => x.mt),
      amt: (cb[c.id] || {}).mt || 0, usd: (cb[c.id] || {}).usd || 0, avg: cb[c.id] ? cb[c.id].w / cb[c.id].mt : null,
      win: (wn[c.id] || {}).win_cbot, wstart: (wn[c.id] || {}).win_start, wend: (wn[c.id] || {}).win_end, eq: eqAvg(r)}}); });
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
  if (S.sort.c) rows = sortBy(rows, "c", cols);
  else rows = byOrder(rows, c => c.x.rows.length ? c.x.rows.reduce((m, r) => r.date > m ? r.date : m, "") : (c.last_date || c.first_date))
    || rows.sort((a, b) => (isN(b.x[P_.k].sav) ? b.x[P_.k].sav : -1e18) - (isN(a.x[P_.k].sav) ? a.x[P_.k].sav : -1e18));
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
    ["Landed EGP/MT", f2(isN(gCon(c).incl) ? gCon(c).incl : c.landed_egp_mt) + ` <span class="note">incl. transport${pcOn() ? " · average port costs" : ""}</span>`],
    ["Import inland transport", isN(c.freight_egp_mt) ? f2(c.freight_egp_mt) + " EGP/MT" : NA_]]);
  const lo = dl([["Consumed", f0(c.consumed_mt) + " MT"], ["Compared vs local", f0(sum(srows, r => r.mt)) + " MT"], ["Period", esc((c.first_date || "—") + " → " + (c.last_date || "—"))],
    ...L_.flatMap(sc => { const A = aggS(srows, sc); return [[`Wtd avg local ${sc.h}`, f2(A.local)], [`Landed ${sc.h}`, f2(A.cost)],
      [`Savings EGP/MT ${sc.h}`, `<span class="${sg(A.per)}">${isN(A.per) ? f2(A.per) : "N/A"}</span>`], [`Total savings ${sc.h}`, `<b class="${sg(A.sav)}">${isN(A.sav) ? money("EGP", A.sav) : "N/A — Missing Source Data"}</b>`]]; }),
    ["Oldest local quote used", ageBadge(ages.length ? Math.max(...ages) : null)], ["MT on quotes > " + CD() + " days", f0(sum(srows.filter(r => r.local_stale), r => r.mt))],
    ["Basis", c.cif_final ? '<span class="tag act">Final CIF</span>' : '<span class="tag pot">Provisional CIF</span>']]);
  const cbx = f.fixed ? dl([["CBOT fixed", `<b>${f2(f.value)}</b> ${esc(f.unit)}`], ["Type", esc(f.status)], ["Pricing date", esc(f.pricing_date || "Not recorded")],
    ["Futures month", esc(futCode(c))], ["Premium / factor", f2(c.premium) + " / " + fx(f.factor, 4)], ["① Avg CBOT, consumption days", f2(cb.avg_cbot)],
    ["② Avg CBOT, storage → last consumption", isN(c.x && c.x.win) ? `${f2(c.x.win)} <span class="note">${esc(c.x.wstart)} → ${esc(c.x.wend)}</span>` : "—"],
    ["Avg local equiv. CBOT", c.x && isN(c.x.eq.eqc) ? `<b>${f2(c.x.eq.eqc)}</b> <span class="note">vs fixed ${f2(f.value)}: <span class="${sg(c.x.eq.eqd)}">${c.x.eq.eqd >= 0 ? "+" : ""}${f2(c.x.eq.eqd)}</span></span>` : "—"], ["Coverage", isN(cb.coverage) ? fx(cb.coverage * 100, 0) + "% of consumed MT" : "—"],
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
const fxCell = c => isN(c.fx) ? `${fx(c.fx, 4)} <span class="tag ${c.fx_basis === "Form 4" ? "good" : (c.fx_basis || "").startsWith("Latest") ? "pot" : ""}" title="${esc(c.fx_basis)}${c.form4_date ? " · " + esc(c.form4_date) : ""}">${c.fx_basis === "Form 4" ? "Form 4" : esc(c.fx_basis || "—")}</span>` : NA_;
const cifTip = c => isN(c.fix.value) && isN(c.premium) && isN(c.fix.factor)
  ? `CIF = (CBOT fixed ${f2(c.fix.value)} + premium ${f2(c.premium)}) × ${c.fix.factor} = ${f2((c.fix.value + c.premium) * c.fix.factor)} $/MT` : "Contract CIF as recorded";
const agreeOf = c => c.y.unfixed || !c.y.amt || !c.y.wmt ? "" : Math.sign(c.y.usd) === Math.sign(c.y.wusd) ? "Yes" : "No";
const CPC = [{h: "Contract", v: c => c.contract, html: c => `<b>${esc(c.contract)}</b> <span class="note">${esc(c.id)} ▸</span><br><span class="note">${esc(c.supplier)} · ${esc(c.commodity)}</span>`},
  {h: "CBOT fixed", n: 1, v: c => c.fix.value, html: c => c.y.unfixed ? '<span class="tag pot">Not fixed yet</span>' : f2(c.fix.value)},
  {h: "Premium", n: 1, v: c => c.premium, html: c => isN(c.premium) ? `${f2(c.premium)} <span class="note">${esc(c.fix.unit || "")}</span>` : "—"},
  {h: "CIF $/MT", n: 1, v: c => c.cif_usd_mt, html: c => isN(c.cif_usd_mt) ? `<span title="${esc(cifTip(c))}">${f2(c.cif_usd_mt)}</span><br><span class="note">${c.cif_final ? "final" : c.y.unfixed ? "indicative" : "provisional"}</span>` : "—"},
  {h: "MT consumed", n: 1, v: c => c.y.mt, tot: rs => sum(rs, c => c.y.mt)},
  {h: "Avg local equiv. CBOT", n: 1, v: c => c.y.eq.eqc, html: c => isN(c.y.eq.eqc) ? `<b>${f2(c.y.eq.eqc)}</b> <span class="note">${esc(c.y.eq.unit)}</span>` : "—"},
  {h: "Local equiv. CBOT − fixed", n: 1, v: c => c.y.eq.eqd, f: f2, col: 1},
  {h: "① Avg CBOT on consumption days", n: 1, v: c => c.y.avg, f: f2},
  {h: "② Avg CBOT storage date → last consumption", n: 1, v: c => c.y.win, html: c => isN(c.y.win) ? `${f2(c.y.win)}<br><span class="note">${esc(c.y.wstart)} → ${esc(c.y.wend)}${c.y.wfs ? "" : " · no storage date"}</span>` : "—"},
  {h: "① Net USD", n: 1, v: c => c.y.amt ? c.y.usd : null, col: 1, tot: rs => sum(rs, c => c.y.amt ? c.y.usd : null)},
  {h: "② Net USD", n: 1, v: c => c.y.wmt ? c.y.wusd : null, col: 1, tot: rs => sum(rs, c => c.y.wmt ? c.y.wusd : null)},
  {h: "② − ① USD/MT", n: 1, v: c => c.y.amt && c.y.wmt ? c.y.wusd / c.y.wmt - c.y.usd / c.y.amt : null, f: f2, col: 1},
  {h: "Both agree?", v: agreeOf, html: c => !agreeOf(c) ? "" : agreeOf(c) === "Yes" ? '<span class="tag good">Same direction</span>' : '<span class="tag pot" title="The result depends on the estimated consumption days — check them">Differs — check dates</span>'},
  {h: "Avg local equiv. premium", n: 1, v: c => c.y.eq.eq, html: c => isN(c.y.eq.eq) ? `<b>${f2(c.y.eq.eq)}</b> <span class="note">${esc(c.y.eq.unit)}</span>` : "—"},
  {h: "Contract premium", n: 1, v: c => c.y.eq.prem, f: f2},
  {h: "Avg premium gap", n: 1, v: c => c.y.eq.gap, f: f2, col: 1},
  {h: "Avg local price incl.", n: 1, v: c => c.y.eq.local, f: f2},
  ...["cifE", "disc", "clr", "fr"].map((k, i) => ({h: ["CIF × FX EGP/MT", "+ Discharge", "+ Clearance", "+ Inland freight"][i], n: 1, v: c => gCon(c)[k],
    html: c => { const p = gCon(c), b = [null, p.discB, p.clrB, p.frB][i], miss = [false, p.discMiss, p.clrMiss, false][i];
      return miss ? '<span class="stale">0.00</span> <span class="note">not recorded</span>' : isN(p[k]) ? `<span title="${esc(b || "")}">${f2(p[k])}</span>` : (k === "fr" ? '<span class="na">add manually</span>' : "—"); }})),
  {h: "= Landed incl. EGP/MT", n: 1, v: c => gCon(c).incl, html: c => { const p = gCon(c); return isN(p.incl) ? `<b data-tip="${esc(bdTip(p, "incl"))}">${f2(p.incl)}</b>` : NA_; }},
  {h: "① Difference", n: 1, v: c => isN(c.y.avg) && isN(c.fix.value) ? c.y.avg - c.fix.value : null, f: f2, col: 1},
  {h: "② Difference", n: 1, v: c => isN(c.y.win) && isN(c.fix.value) ? c.y.win - c.fix.value : null, f: f2, col: 1},
  {h: "① USD/MT", n: 1, v: c => c.y.amt ? c.y.usd / c.y.amt : null, f: f2, col: 1},
  {h: "② USD/MT", n: 1, v: c => c.y.wmt ? c.y.wusd / c.y.wmt : null, f: f2, col: 1},
  {h: "① Net EGP", n: 1, v: c => c.y.amt ? c.y.egp : null, col: 1, tot: rs => sum(rs, c => c.y.amt ? c.y.egp : null)},
  {h: "② Net EGP", n: 1, v: c => c.y.wmt ? c.y.wegp : null, col: 1, tot: rs => sum(rs, c => c.y.wmt ? c.y.wegp : null)},
  {h: "① Advantage USD", n: 1, v: c => c.y.adv, col: 1, tot: rs => sum(rs, c => c.y.adv)}, {h: "① Missed USD", n: 1, v: c => c.y.miss, col: 1, tot: rs => sum(rs, c => c.y.miss)},
  {h: "Fixing type", v: c => c.fix.type === "Implied" ? "Implied CBOT Fixing" : c.fix.type === "Recorded" ? "Recorded fixing (lots)" : c.fix.type},
  {h: "Futures month", v: c => futCode(c)}, {h: "Pricing date", v: c => pdate(c) || (c.y && c.y.unfixed ? "Not priced yet" : "Not recorded")},
  {h: "MT with CBOT that day", n: 1, v: c => c.y.unfixed ? c.y.wm : c.y.amt, tot: rs => sum(rs, c => c.y.unfixed ? c.y.wm : c.y.amt)},
  {h: "FX (Form 4 / basis)", n: 1, v: c => c.fx, html: fxCell},
  {h: "Indicative USD if fixed at latest CBOT (not fixed yet)", n: 1, v: c => c.y.unfixed ? c.y.ind : null, col: 1, html: c => c.y.unfixed && isN(c.y.ind) ? `<span class="${sg(c.y.ind)}" title="Not in the CBOT totals">${f0(c.y.ind)}</span> <span class="tag pot">indicative</span>` : ""},
  {h: "Assessment", v: c => c.y.res}];
// Consumption days of a contract that is not priced yet: the CBOT that day, and
// an indicative difference against the latest stored CBOT (as if fixed today).
function cbotDaysU(c, rows) {
  rows = dayOrder(rows);
  const mt = sum(rows, r => r.mt), w = rows.filter(r => isN(r.cbot)), wm = sum(w, r => r.mt), i = rows.filter(r => isN(r.ind_diff)), im = sum(i, r => r.mt);
  const avg = wm ? sum(w, r => r.cbot * r.mt) / wm : null, lat = rows.find(r => isN(r.latest_cbot)) || {};
  return `<thead><tr><th>Consumption date</th><th class="n">Consumed MT</th><th class="n">CBOT fixed</th><th class="n">Premium</th><th class="n">Indicative CIF $/MT</th>${BD_TH_NOCIF}<th class="n">CBOT that day</th><th>Price date</th><th class="n">Avg CBOT storage → last consumption</th>${LOCAL_TH}<th class="n">Live CBOT</th><th class="n">Indicative difference</th><th class="n">Indicative USD/MT</th><th class="n">Indicative USD</th><th class="n">FX</th><th class="n">Indicative EGP</th><th>Result</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.date)}</td>${td(r.mt)}<td class="n"><span class="tag pot">Not fixed yet</span></td>${td(r.premium, f2)}<td class="n" title="(latest CBOT + premium) × factor — indicative until priced">${isN(r.latest_cbot) && isN(r.premium) ? f2((r.latest_cbot + r.premium) * r.factor) : "—"}</td>${bdTds(svOf(r), true)}${td(r.cbot, f2)}<td>${esc(r.cbot_date || "—")}</td>${td(r.win_cbot, f2)}${localTds(r)}<td class="n">${f2(r.latest_cbot)} <span class="note">${r.latest_cbot_live ? "live · " : ""}${esc(liveTime(r))}</span></td>` +
      `${td(r.ind_diff, f2, 1)}${td(r.ind_usd_mt, f2, 1)}${td(r.ind_usd, f0, 1)}${td(r.fx, x => fx(x, 4))}${td(r.ind_egp, f0, 1)}<td><span class="tag pot">${esc(r.result)}</span></td></tr>`).join("") +
    `<tr class="tot"><td>Total / average · ${rows.length} days</td>${td(mt)}<td class="n note">premium ${f2(c.premium)} ${esc((rows[0] || {}).unit || "")} over ${esc((rows[0] || {}).futures || "—")}</td><td></td><td></td>${bdTot(rows.map(r => Object.assign({}, svOf(r), {mt: r.mt})), true)}${td(avg, f2)}<td class="note">tonne-weighted</td>${td((rows.find(r => isN(r.win_cbot)) || {}).win_cbot, f2)}${localTot(eqAvg(rows))}${td(lat.latest_cbot, f2)}` +
    `${td(im ? sum(i, r => r.ind_diff * r.mt) / im : null, f2, 1)}${td(im ? sum(i, r => r.ind_usd) / im : null, f2, 1)}${td(sum(i, r => r.ind_usd), f0, 1)}<td></td>${td(sum(i, r => r.ind_egp), f0, 1)}<td class="note">Indicative — not in the CBOT totals</td></tr></tbody>` +
    `<tfoot><tr><td colspan="30" class="note">Not priced yet: the result is fixed only when the contract is priced. Indicative = (CBOT that day − live CBOT) × factor × MT, i.e. as if it were fixed at today's CBOT.</td></tr></tfoot>`;
}
// Each consumption date of one contract: the tonnes, the CBOT that day vs the fixing, and what it was worth.
function cbotDays(c, rows) {
  rows = dayOrder(rows);
  const a = rows.filter(r => r.assessable), mt = sum(rows, r => r.mt), amt = sum(a, r => r.mt);
  const avg = amt ? sum(a, r => r.cbot * r.mt) / amt : null, usd = sum(a, r => r.usd), egp = sum(a, r => r.egp);
  const n = M.options.neutral_cbot, d = isN(avg) ? avg - c.fix.value : null, wr = rows.find(r => isN(r.win_cbot)) || {};
  const tag = (u, res) => `<span class="tag ${u > 0 ? "good" : u < 0 ? "bad" : ""}">${esc(res)}</span>`;
  return `<thead><tr><th>Consumption date</th><th class="n">Consumed MT</th><th class="n">CBOT fixed</th><th class="n">Premium</th><th class="n">CIF $/MT</th>${BD_TH_NOCIF}<th class="n">① CBOT that day</th><th class="n">② Avg CBOT storage → last consumption</th>` +
    `<th class="n">① Saving USD</th><th class="n">② Saving USD</th><th>① Result</th>${LOCAL_TH}<th class="n">① Difference</th><th class="n">② Difference</th><th class="n">① USD/MT</th><th class="n">② USD/MT</th>` +
    `<th>① Price date</th><th class="n">FX</th><th class="n">① Saving EGP</th><th class="n">② Saving EGP</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.date)}</td>${td(r.mt)}${td(r.fix, f2)}${td(r.premium, f2)}<td class="n" title="${esc(cifTip(c))}">${f2(r.cif)}</td>${bdTds(svOf(r), true)}${td(r.cbot, f2)}${td(r.win_cbot, f2)}` +
      (r.assessable ? `${td(r.usd, f0, 1)}${td(r.win_usd, f0, 1)}<td>${tag(r.usd, r.result)}</td>${localTds(r)}${td(r.diff, f2, 1)}${td(r.win_diff, f2, 1)}${td(r.usd_mt, f2, 1)}${td(r.win_usd_mt, f2, 1)}`
                    : `<td class="na">—</td>${td(r.win_usd, f0, 1)}<td class="na">Not compared: ${esc(r.benchmark)}</td>${localTds(r)}<td class="na">—</td>${td(r.win_diff, f2, 1)}<td class="na">—</td>${td(r.win_usd_mt, f2, 1)}`) +
      `<td>${esc(r.cbot_date || "—")}</td>${td(r.fx, x => fx(x, 4))}${td(r.egp, f0, 1)}${td(r.win_egp, f0, 1)}</tr>`).join("") +
    `<tr class="tot"><td>Total / average · ${rows.length} days</td>${td(mt)}${td(c.fix.value, f2)}${td(c.premium, f2)}${td(c.cif_usd_mt, f2)}${bdTot(rows.map(r => Object.assign({}, svOf(r), {mt: r.mt})), true)}${td(avg, f2)}${td(wr.win_cbot, f2)}` +
    `${td(usd, f0, 1)}${td(sum(rows, r => r.win_usd), f0, 1)}<td>${!amt ? "Not assessable" : d >= n ? "Advantage" : d <= -n ? "Missed opportunity" : "Neutral"}</td>${localTot(eqAvg(rows))}` +
    `${td(d, f2, 1)}${td(wr.win_diff, f2, 1)}${td(amt ? usd / amt : null, f2, 1)}${td(wr.win_usd_mt, f2, 1)}<td class="note">① tonne-weighted</td>` +
    `${td(amt ? sum(a, r => r.fx * r.mt) / amt : null, x => fx(x, 4))}${td(egp, f0, 1)}${td(sum(rows, r => r.win_egp), f0, 1)}</tr></tbody>` +
    `<tfoot><tr><td colspan="33" class="note">CIF = (CBOT fixed + premium) × factor; landed = CIF × FX + discharge + clearance (+ inland freight), from the same day in Savings vs local. Local equiv. CBOT = (local excl. − discharge − clearance) ÷ that day's FX ÷ factor − contract premium: the CBOT at which this contract would have cost the same as local (above the fixing = we did better than local). Local price, equivalent premium and gap come from Savings vs local for the same day: equivalent premium = (local price excl. transport − discharge − clearance) ÷ that day's FX ÷ factor − that day's CBOT; gap = equivalent − contract premium (positive = the local market was dearer than our premium). Totals are tonne-weighted averages. ① = the CBOT stored for each consumption day (consumption days are FIFO estimates). ② = the average of the ${wr.win_days || 0} CBOT prices stored from ${esc(wr.win_start || "—")}${wr.win_from_storage ? " (storage date)" : " (first consumption day — no storage date recorded)"} to ${esc(wr.win_end || "—")} (last consumption day), applied to every consumed tonne — it does not depend on the estimated consumption days.</td></tr></tfoot>`;
}
const FACT = {CORN: 0.3937, SOYBEAN: 0.36745, WHEAT: 0.36745, SBM: 1.1023};
const OCB = [
  {h: "Contract / Supplier", v: r => r.contract, html: r => `<b>${esc(r.contract)}</b><br><span class="note">${esc(r.supplier)} · ${esc(r.contract_id)}</span>`},
  {h: "Commodity / Origin", v: r => r.commodity, html: r => `${esc(r.commodity)}<br><span class="note">${esc(r.origin || "—")}</span>`},
  {h: "Qty MT", n: 1, v: r => r.qty_mt, tot: rs => sum(rs, r => r.qty_mt)},
  {h: "Not yet consumed MT", n: 1, v: r => r.unconsumed_mt, tot: rs => sum(rs, r => r.unconsumed_mt)},
  {h: "Storage start", v: r => r.storage_start, html: storageCell},
  {h: "Premium", n: 1, v: r => r.premium, html: r => premCell(r.premium, r.unit, r.pricing_class)},
  {h: "Futures month", v: r => r.futures || "—"},
  {h: "Fixed / Live CBOT", n: 1, v: r => isN(r.fixed_cbot) ? r.fixed_cbot : r.latest_cbot, html: cbotCellO},
  {h: "CIF $/MT", n: 1, v: r => r.cif, html: cifCellO},
  {h: "FX", n: 1, v: r => r.fx, html: fxCellO},
  {h: "Pricing status", v: r => r.pricing_class, html: r => pTag(r.pricing_class)},
  {h: "Valuation", v: r => r.class, html: valTag}];
// Position against local now: cost at the CBOT the contract is valued at, break-even CBOT and headroom.
function headCell(r, sc) {
  if (flatC(r.pricing_class)) return '<span class="note">flat price</span>';
  const h = r["headroom_" + sc.k]; if (!isN(h)) return NA_;
  return `<span class="${sg(h)}"><b>${h >= 0 ? "+" : ""}${f2(h)}</b></span> <span class="note">${esc(r.unit)}</span><br><span class="note">${h >= 0 ? "CBOT can rise this much" : "local already cheaper"} · vs ${esc(r.ref_cbot_basis)} ${f2(r.ref_cbot)}</span>`;
}
// How an imported cost is built, column by column: CIF $/MT × FX = CIF EGP/MT,
// + discharge + clearance = cost excl. transport, + inland freight = cost incl.
// transport. g(r) returns the parts for an open-position row or a contract.
const gOpen = o => ({cif: o.cif, fx: o.fx, cifE: o.cif_egp, disc: o.discharge, clr: o.clearance,
  discB: o.port_avg ? "Average discharge + clearance (what-if)" : o.disc_basis, clrB: o.port_avg ? "included in the average" : o.clr_basis,
  discMiss: o.port_avg ? false : o.disc_missing, clrMiss: o.port_avg ? false : o.clr_missing, fr: o.freight, frB: o.man ? manualFor(CI[o.contract_id] || {})[1] : o.freight_basis,
  frNote: (CI[o.contract_id] || {}).freight_note, excl: o.cost_excl, incl: o.cost_incl});
const gCon = c => { const u = c.is_open && c.current && isN(c.current.cost_excl) ? c.current : null,
    cif = u ? u.cif : c.cif_usd_mt, fxv = u ? u.fx : c.fx, disc = u ? u.disc : (c.discharge_egp_mt || 0), clr = u ? u.clr : (c.clearance_egp_mt || 0),
    man = isN(c._man), fr = man ? c._man : c.freight_egp_mt, avg = pcOn(),
    excl = avg && isN(c.landed_excl_egp_mt) ? c.landed_excl_egp_mt - disc - clr + PC.avg : c.landed_excl_egp_mt;
  return {cif, fx: fxv, cifE: isN(cif) && isN(fxv) ? cif * fxv : null, disc: avg ? PC.avg : disc, clr: avg ? 0 : clr,
    discB: avg ? "Average discharge + clearance (what-if)" : c.disc_basis, clrB: avg ? "included in the average" : c.clr_basis,
    discMiss: avg ? false : c.disc_missing, clrMiss: avg ? false : c.clr_missing,
    fr, frB: man ? manualFor(c)[1] : c.freight_basis, frNote: c.freight_note, excl, incl: isN(excl) && isN(fr) ? excl + fr : null}; };
function bdTip(p, k) {
  if (!isN(p.excl)) return "";
  const s = `CIF ${f2(p.cif)} $/MT × FX ${fx(p.fx, 4)} = ${f2(p.cifE)} + discharge ${f2(p.disc)} + clearance ${f2(p.clr)} = ${f2(p.excl)} EGP/MT excl. transport`;
  return k === "excl" ? s : isN(p.incl) ? `${s} + inland freight ${f2(p.fr)} (${p.frB}) = ${f2(p.incl)} EGP/MT incl. transport` : `${s} · inland freight not recorded, so no figure incl. transport`;
}
const feeCell = (v, b, miss) => miss ? `<span class="stale">0.00</span><br><span class="note">Not recorded — cost excludes it</span>` :
  `${f2(v)}<br><span class="note">${esc(b || "")}</span>`;
function bdCols(g) {
  const L_ = scs(), inc = L_.some(sc => sc.k === "incl");
  return [
    {h: "CIF × FX = CIF EGP/MT", n: 1, v: r => g(r).cifE, html: r => { const p = g(r); return isN(p.cifE) ? `<b>${f2(p.cifE)}</b><br><span class="note">${f2(p.cif)} × ${fx(p.fx, 4)}</span>` : NA_; }},
    {h: "+ Discharge EGP/MT", n: 1, v: r => g(r).disc, html: r => { const p = g(r); return feeCell(p.disc, p.discB, p.discMiss); }},
    {h: "+ Clearance EGP/MT", n: 1, v: r => g(r).clr, html: r => { const p = g(r); return feeCell(p.clr, p.clrB, p.clrMiss); }},
    ...(inc ? [{h: "+ Inland freight EGP/MT", n: 1, v: r => g(r).fr, html: r => { const p = g(r);
      return isN(p.fr) ? `<b>${f2(p.fr)}</b><br><span class="note" title="${esc(p.frB || "")}">${esc(p.frB || "")}</span>`
        : `<span class="na nm">N/A — add manually</span><br><span class="note">${esc(p.frNote || p.frB || "no route in the freight table")}</span>`; }}] : [])];
}
const costCol = (h, sc, g) => ({h, n: 1, na: 1, v: sc.ocost, html: r => { const v = sc.ocost(r); if (!isN(v)) return NA_;
  return `<b data-tip="${esc(bdTip(g(r), sc.k))}">${f2(v)}</b><br><span class="note">${sc.k === "incl" ? "= excl. + freight" : "= CIF EGP + disch. + clear."}</span>`; }});
function posCols() {
  const L_ = scs();
  return [...bdCols(gOpen),
    ...L_.flatMap(sc => [costCol(`= Imported cost now ${sc.h}`, sc, gOpen), {h: `Local ${sc.h}`, n: 1, na: 1, v: sc.olocal, f: f2},
      {h: `Saving/MT now ${sc.h}`, n: 1, na: 1, v: sc.oper, f: f2, col: 1}]),
    {h: "Local date / age", v: r => r.local_age, html: r => (r.local_date ? esc(r.local_date) + "<br>" : "") + ageBadge(r.local_age)},
    ...L_.map(sc => ({h: `Break-even CBOT ${sc.h}`, n: 1, v: r => r["be_cbot_" + sc.k],
      html: r => flatC(r.pricing_class) ? '<span class="note">flat price</span>' : isN(r["be_cbot_" + sc.k]) ? `<b>${f2(r["be_cbot_" + sc.k])}</b> <span class="note">${esc(r.unit)}</span>` : NA_})),
    ...L_.map(sc => ({h: `Headroom ${sc.h}`, n: 1, v: r => r["headroom_" + sc.k], html: r => headCell(r, sc)})),
    {h: "Local equiv. premium", n: 1, v: r => r.local_eq_premium,
      html: r => flatC(r.pricing_class) ? '<span class="note">flat price</span>' : isN(r.local_eq_premium) ? `${f2(r.local_eq_premium)} <span class="note">vs contract ${f2(r.premium)}</span>` : NA_}];
}
function renderSvOpen(v) {
  const L_ = scs(), cols = OCB.slice(0, 5).concat([{h: "Pricing status", v: r => r.pricing_class, html: r => pTag(r.pricing_class)}], OCB.slice(5, 10), posCols(),
    L_.map(sc => ({h: `Total potential ${sc.h}`, n: 1, na: 1, v: sc.pot, col: 1, tot: rs => sum(rs, sc.pot)})), [{h: "Valuation", v: r => obucket(r) + r.class, html: valTag}]);
  let rows = v.op.filter(r => r.unconsumed_mt > 0);
  rows = S.sort.svo ? sortBy(rows, "svo", cols) : (byOrder(rows, r => r.storage_start || (CI[r.contract_id] || {}).delivery_date) || rows.slice().sort((a, b) => b.unconsumed_mt - a.unconsumed_mt));
  $("svOpenT").innerHTML = rows.length ? thead("svo", cols) + "<tbody>" + rows.map(r => `<tr class="row ${orow(r)}" data-goto="${esc(r.contract_id)}">` + cols.map(col => cell(col, r)).join("") + "</tr>").join("") +
    totRow(cols, rows, `Total · ${rows.length} contracts`) + "</tbody>" : '<tbody><tr><td class="note">No open contract with tonnes still to consume in this selection.</td></tr></tbody>';
}
function renderCbotOpen(v) {
  let rows = v.op.filter(r => FACT[r.base] && !["Flat-priced", "Not CBOT-based"].includes(r.pricing_class) && r.unconsumed_mt > 0);
  const cols = OCB.concat(posCols());
  rows = S.sort.ocb ? sortBy(rows, "ocb", cols) : (byOrder(rows, r => r.storage_start || (CI[r.contract_id] || {}).delivery_date) || rows.slice().sort((a, b) => b.unconsumed_mt - a.unconsumed_mt));
  $("tCbOpen").innerHTML = rows.length ? thead("ocb", cols) + "<tbody>" + rows.map(r => `<tr class="row ${orow(r)}" data-goto="${esc(r.contract_id)}">` + cols.map(col => cell(col, r)).join("") + "</tr>").join("") +
    totRow(cols, rows, `Total · ${rows.length} contracts`) + "</tbody>" : '<tbody><tr><td class="note">No open CBOT contract with tonnes still to consume in this selection.</td></tr></tbody>';
}
function renderCbot(v) {
  const n = M.options.neutral_cbot, by = {};
  v.cb.forEach(r => { const s = by[r.contract_id] = by[r.contract_id] || {mt: 0, amt: 0, usd: 0, egp: 0, w: 0, adv: 0, miss: 0, wmt: 0, wusd: 0, wegp: 0};
    s.mt += r.mt; if (r.assessable) { s.amt += r.mt; s.usd += r.usd; s.egp += r.egp || 0; s.w += r.cbot * r.mt; if (r.usd > 0) s.adv += r.usd; else s.miss += r.usd; }
    if (isN(r.win_usd)) { s.wmt += r.mt; s.wusd += r.win_usd; s.wegp += r.win_egp || 0; }
    if (isN(r.win_cbot)) Object.assign(s, {win: r.win_cbot, wstart: r.win_start, wend: r.win_end, wfs: r.win_from_storage}); });
  let rows = v.contracts.filter(c => by[c.id]).map(c => { const s = by[c.id], avg = s.amt ? s.w / s.amt : null, d = isN(avg) ? avg - c.fix.value : null;
    return Object.assign(c, {y: Object.assign(s, {avg, unfixed: false, res: !s.amt ? "Not assessable" : d >= n ? "Advantage" : d <= -n ? "Missed opportunity" : "Neutral"})}); });
  const byU = groupBy(v.cu, r => r.contract_id);
  rows = rows.concat(v.contracts.filter(c => byU[c.id] && !by[c.id]).map(c => { const u = byU[c.id], w = u.filter(r => isN(r.cbot)), wm = sum(w, r => r.mt);
    const w0 = u.find(r => isN(r.win_cbot)) || {};
    return Object.assign(c, {y: {mt: sum(u, r => r.mt), amt: 0, usd: 0, egp: 0, adv: 0, miss: 0, w: 0, avg: wm ? sum(w, r => r.cbot * r.mt) / wm : null,
      win: w0.win_cbot, wstart: w0.win_start, wend: w0.win_end, wfs: w0.win_from_storage, wmt: 0, wusd: 0, wegp: 0,
      unfixed: true, wm, ind: sum(u, r => r.ind_usd), res: "Not fixed yet — indicative"}}); }));
  const lastCb = {}; v.cb.concat(v.cu).forEach(r => { if (!lastCb[r.contract_id] || r.date > lastCb[r.contract_id]) lastCb[r.contract_id] = r.date; });
  rows = S.sort.cp ? sortBy(rows, "cp", CPC) : (byOrder(rows, c => lastCb[c.id]) || rows.sort((a, b) => (a.y.amt ? a.y.usd : 1e18) - (b.y.amt ? b.y.usd : 1e18)));
  const cbAll = groupBy(v.cb.concat(v.cu), r => r.contract_id);
  rows.forEach(c => { c.y.eq = eqAvg(cbAll[c.id] || []); });
  const K = kpis(v), fixedRows = rows.filter(c => !c.y.unfixed && c.y.amt && c.y.wmt), dis = fixedRows.filter(c => agreeOf(c) === "No");
  const B = '<span class="tag ben">Benchmark</span>', dmt = K.cbot_win_mt && K.cbot_assessed_mt ? K.cbot_win_net_usd / K.cbot_win_mt - K.cbot_net_usd / K.cbot_assessed_mt : null;
  $("cbK").innerHTML = [
    kcard("① Net vs CBOT on consumption days", K.cbot_net_usd, money("USD", K.cbot_net_usd), B, `${f0(K.cbot_assessed_mt)} MT · ${isN(K.cbot_net_usd) && K.cbot_assessed_mt ? f2(K.cbot_net_usd / K.cbot_assessed_mt) : "—"} USD/MT · ${money("EGP", K.cbot_net_egp)} · uses the estimated consumption days`),
    kcard("② Net vs average CBOT, storage date → last consumption", K.cbot_win_net_usd, money("USD", K.cbot_win_net_usd), B, `${f0(K.cbot_win_mt)} MT · ${K.cbot_win_mt ? f2(K.cbot_win_net_usd / K.cbot_win_mt) : "—"} USD/MT · ${money("EGP", K.cbot_win_net_egp)} · does not depend on consumption days`),
    kcard("Difference ② − ①", K.cbot_win_net_usd - K.cbot_net_usd, money("USD", K.cbot_win_net_usd - K.cbot_net_usd), '<span class="tag">Check</span>', `${isN(dmt) ? f2(dmt) : "—"} USD/MT on the same tonnes · ${fixedRows.length - dis.length} of ${fixedRows.length} contracts point the same way${dis.length ? ` · differ: ${dis.map(c => esc(c.contract)).join(", ")}` : ""}`)].join("");
  S.cpOpen = S.cpOpen || new Set();
  $("tCP").innerHTML = thead("cp", CPC) + "<tbody>" + rows.map(c => `<tr class="row" data-cp="${esc(c.id)}">` + CPC.map(col => cell(col, c)).join("") + "</tr>" +
    (S.cpOpen.has(c.id) ? `<tr class="det"><td colspan="${CPC.length}"><div class="detwrap" style="overflow-x:auto"><table>${c.y.unfixed ? cbotDaysU(c, v.cu.filter(r => r.contract_id === c.id)) : cbotDays(c, v.cb.filter(r => r.contract_id === c.id))}</table>` +
      `<p class="note" style="margin:6px 0 0"><button class="btn" data-goto="${esc(c.id)}">Open the full contract analysis</button></p></div></td></tr>` : "")).join("") +
    totRow(CPC, rows, `Total · ${rows.length} contracts`) + "</tbody>";
  const choices = rows.filter(c => !c.y.unfixed).sort((a, b) => b.y.amt - a.y.amt);
  if (!choices.find(c => c.id === S.cb)) S.cb = choices.length ? choices[0].id : "";
  $("cbSel").innerHTML = choices.map(c => `<option value="${esc(c.id)}" ${c.id === S.cb ? "selected" : ""}>${esc(c.contract)} · ${esc(c.commodity)} · ${f0(c.y.amt)} of ${f0(c.y.mt)} MT with a stored CBOT</option>`).join("");
  const c = CI[S.cb];
  renderCbotOpen(v);
  if (!c) { $("cbChart").innerHTML = `<p class="note">No fixed contract with consumption in this selection.${v.op.some(r => FACT[r.base] && r.unconsumed_mt > 0) ? " Open contracts not yet consumed are listed in the next section." : ""}</p>`; $("cbBars").innerHTML = ""; $("cbSum").innerHTML = ""; $("cbDays").innerHTML = ""; return; }
  const cr = v.cb.filter(r => r.contract_id === c.id), s = by[c.id];
  $("cbChart").innerHTML = cbotChart(c, cr);
  $("cbBars").innerHTML = dailyBars(cr);
  $("cbSum").innerHTML = `${esc(c.fix.status)} · fixed ${f2(c.fix.value)} ${esc(c.fix.unit)} · futures ${esc(c.contract_month ? c.contract_month.code : "—")} · CBOT on ${f0(s.amt)} of ${f0(s.mt)} MT consumed · advantage ${money("USD", s.adv)} · missed ${money("USD", s.miss)} · net <b class="${sg(s.usd)}">${money("USD", s.usd)}</b> · storage-date average ${isN(s.win) ? f2(s.win) : "—"} → net <b class="${sg(s.wusd)}">${s.wmt ? money("USD", s.wusd) : "—"}</b> · FX ${fxCell(c)}`;
  $("cbDays").innerHTML = cbotDays(c, cr);
}

// ── open tab ─────────────────────────────────────────────────────────
// The live CBOT the app values open contracts at (its time), else the last stored close (its date).
const liveTime = r => r.latest_cbot_live ? ((M.live_cbot || {})[r.base] || {}).time || r.latest_cbot_date : r.latest_cbot_date;
function cbotCellO(r) {
  if (flatC(r.pricing_class)) return '<span class="note">— flat price</span>';
  const a = isN(r.fixed_cbot) ? `${f2(r.fixed_cbot)} <span class="tag ${r.fix_type === "Implied" ? "pot" : "act"}">${r.fix_type === "Implied" ? "Implied CBOT Fixing" : "Fixed"}</span>` : '<span class="tag pot">Not fixed</span>';
  const b = isN(r.latest_cbot) ? `<br><span class="note" title="${esc(r.cbot_note || "")}">${r.latest_cbot_live ? "<b>live</b>" : "latest stored"} ${f2(r.latest_cbot)} · ${esc(liveTime(r))}</span>` : "";
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
    {h: "Fixed / Live CBOT", n: 1, v: r => isN(r.fixed_cbot) ? r.fixed_cbot : r.latest_cbot, html: cbotCellO},
    {h: "Final / Indicative CIF $/MT", n: 1, v: r => r.cif, html: cifCellO},
    {h: "Form 4 / Latest FX", n: 1, v: r => r.fx, html: fxCellO},
    ...bdCols(gOpen),
    ...L_.flatMap(sc => [costCol(`= Imported cost ${sc.h}`, sc, gOpen), {h: `Local ${sc.h}`, n: 1, na: 1, v: sc.olocal, f: f2}]),
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
  rows = S.sort.o ? sortBy(rows, "o", cols) : (byOrder(rows, r => r.storage_start || (CI[r.contract_id] || {}).delivery_date)
    || rows.slice().sort((a, b) => (isN(P_.pot(b)) ? P_.pot(b) : -1e18) - (isN(P_.pot(a)) ? P_.pot(a) : -1e18)));
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
    ["Inland freight not recorded", "Contracts without route freight", q.no_route_freight || 0, `${f0(q.no_route_freight_mt || 0)} MT consumed · add the freight on the contract`],
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
   <p>Inland freight is route-specific, never an average: a contract with its route entered keeps that freight; otherwise the freight approval rate for its commodity, loading place and plant, as in force on its delivery date (previous rate before the effective date), + 14% VAT. A contract whose route cannot be matched shows "N/A — add the freight manually" and is compared excluding transport only. See the Transport map tab.</p>
   <p>Transport scenarios: including = landed cost with inland freight vs local quote + local transport; excluding = landed cost without inland freight vs the local quote itself. Each side uses its own recorded transport; ocean freight stays in CIF. Missing transport is shown as N/A — Missing Source Data, never as zero, and left out of that scenario's totals.</p>
   <p>Landed cost: CIF × FX + discharge + clearance (+ inland freight when including transport). FX: Form 4 once entered (all commodities except SBM); historical rows keep their recorded basis; open contracts without Form 4 use the latest daily market FX ("Latest Market FX — Provisional") and switch automatically once Form 4 is entered. CBOT fixed: pricing lots, else Implied CBOT Fixing = CIF ÷ factor − premium (CORN 0.3937; SOYBEAN, WHEAT 0.36745; SBM 1.1023 with premium in $/short ton), so Final CIF = (fixed CBOT + premium) × factor. Unpriced contracts are never shown as fixed: their open tonnes are valued at (live CBOT + premium) × factor — the same live quote the app shows (the last stored close if the app has none) — labelled a proxy when that series is not the contract's own futures month. Flat-priced contracts keep their contract CIF.</p>
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
        "Premium", "Premium Unit", "Futures Month", "Fixed CBOT", "Live / Latest CBOT", "CBOT Date", "CBOT Note", "CIF USD/MT", "CIF Basis", "FX", "FX Basis", "FX Date", "Form 4 Status",
        "Discharge EGP/MT", "Clearance EGP/MT", "Import Inland Transport EGP/MT", ...L_.flatMap(sc => [`Imported Cost ${sc.h}`, `Local ${sc.h}`]), "Local Date", "Local Age (days)", "Local Price Age Status",
        ...L_.flatMap(sc => [`Savings/MT ${sc.h}`, `Total Potential ${sc.h}`]), "Pricing Status", "Valuation Class", "Totals Bucket", "Issues",
        "CIF x FX EGP/MT", "Discharge Source", "Clearance Source", "Inland Freight Basis"],
      ...v.op.map(r => [r.contract, r.contract_id, r.supplier, r.commodity, r.origin, r.qty_mt, r.available_mt, r.outstanding_mt, r.unconsumed_mt, r.storage_start || "Not recorded", r.receipt_status,
        flatC(r.pricing_class) ? "flat price" : nv(r.premium), r.unit, r.futures, isN(r.fixed_cbot) ? r.fixed_cbot : (flatC(r.pricing_class) ? "" : "Not fixed"), r.latest_cbot, r.latest_cbot_date, r.cbot_note,
        nv(r.cif), r.cif_basis, nv(r.fx), r.fx_basis, r.fx_date, r.form4_status,
        r.disc_missing ? "Not recorded" : r.discharge, r.clr_missing ? "Not recorded" : r.clearance, nv(r.freight), ...L_.flatMap(sc => [nv(sc.ocost(r)), nv(sc.olocal(r))]), r.local_date || NA, r.local_age, ageTxt(r.local_age),
        ...L_.flatMap(sc => [nv(sc.oper(r)), nv(sc.pot(r))]), r.pricing_class, r.class,
        {c: "Confirmed", i: "Indicative / provisional", x: "Excluded — missing source data"}[obucket(r)], (r.issues || []).concat(r.notes || []).join("; "),
        nv(r.cif_egp), r.disc_basis || "", r.clr_basis || "", gOpen(r).frB || ""])]]];
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
    COL.premium, COL.futures, COL.fixing, COL.cif, {h: "FX (Form 4 / basis)", n: 1, v: c => c.fx, html: fxCell}, COL.pstatus,
    {h: "Compared MT", n: 1, v: c => c.z.incl.mt, tot: rs => sum(rs, c => c.z.incl.mt)},
    ...bdCols(gCon),
    ...L_.flatMap(sc => [{h: `= Landed ${sc.h} EGP/MT`, n: 1, na: 1, v: c => c.z[sc.k].cost, html: c => { const v = c.z[sc.k].cost; if (!isN(v)) return NA_;
      return `<b data-tip="${esc(bdTip(gCon(c), sc.k))}">${f2(v)}</b><br><span class="note">${sc.k === "incl" ? "= excl. + freight" : "= CIF EGP + disch. + clear."}</span>`; }},
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
  if (!r.premium_factor) return '<td class="n na" colspan="5">no CBOT for this commodity</td>';  // (the two local-equiv. CBOT cells follow separately)
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
  rows = S.sort.sv ? sortBy(rows, "sv", cols) : (byOrder(rows, c => c.z.last) || ranked);
  let h = thead("sv", cols) + "<tbody>";
  rows.forEach(c => {
    h += `<tr class="row" data-sv="${esc(c.id)}" id="sv-${esc(c.id)}">` + cols.map(col => cell(col, c)).join("") + "</tr>";
    // The daily consumption table keeps its original layout (including transport, age in days).
    if (S.svOpen && S.svOpen.has(c.id)) h += `<tr class="det"><td colspan="${cols.length}"><div class="detwrap" style="overflow-x:auto"><table><thead><tr><th>Date</th><th class="n">MT</th>${BD_TH}<th class="n">Contract FX</th><th class="n">Local EGP/MT</th><th>Local quote of</th><th class="n">Age (days)</th><th class="n">Saving EGP/MT</th><th class="n">Saving EGP</th><th class="n">CBOT that day</th><th class="n">FX that day</th><th class="n">Local equiv. premium</th><th class="n">Contract premium</th><th class="n">Premium gap</th><th class="n">Local equiv. CBOT</th><th class="n">Local equiv. CBOT − fixed</th><th>Local record</th><th>Data quality</th></tr></thead><tbody>` +
      dayOrder(c.z.rows).map(r => `<tr><td>${esc(r.date)}</td>${td(r.mt)}${bdTds(r)}<td class="n">${fxCell(c)}</td>${td(r.local, f2)}<td>${esc(r.local_date)} <span class="note">${esc(r.local_key)}</span></td>${td(r.local_age)}${td(r.saving_mt, f2, 1)}${td(r.saving, f0, 1)}${premCells(r)}${eqcTds(r)}<td>${esc(r.local_source)}</td><td class="note">${esc(r.quality)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total</td>${td(c.z.incl.mt)}${bdTot(c.z.rows)}<td></td>${td(c.z.incl.local, f2)}<td></td><td></td>${td(c.z.incl.per, f2, 1)}${td(c.z.incl.sav, f0, 1)}${premAvg(c.z.rows)}${(e => td(e.eqc, f2) + td(e.eqd, f2, 1))(eqAvg(c.z.rows))}<td></td><td></td></tr></tbody></table></div></td></tr>`;
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

// ── transport map ───────────────────────────────────────────────────
const FMAP = M.freight_map || [];
const FCOMM = {CORN: "CORN", SBM: "SBM", SFM: "SFM", SOYBEAN: "SBS", DDGS: "DDGS"};
const FCOMM_LABEL = {CORN: "Yellow corn", SBM: "SBM", SFM: "SFM", SBS: "Soybean seed (whole soybeans)", DDGS: "DDGS", SBHULL: "Soybean hulls", FFS: "Full-fat soy"};
const fcommOf = c => FCOMM[c.base] || c.base;
const vatMul = () => $("tmVat").value === "ex" ? 1 : 1.14;
// Manual freight (what-if): an average (for contracts without route freight, or for all) and per-contract entries.
const MAN = (() => { try { return Object.assign({avg: null, scope: "missing", per: {}}, JSON.parse(localStorage.getItem("pp_manual_freight_v1") || "{}")); } catch (e) { return {avg: null, scope: "missing", per: {}}; } })();
const saveMan = () => { try { localStorage.setItem("pp_manual_freight_v1", JSON.stringify(MAN)); } catch (e) { /* storage unavailable */ } };
// Originals of every figure a what-if (manual freight, average port costs) can change; restored before each render.
const SAV_KEYS = ["cost", "cost_excl", "saving", "saving_mt", "saving_excl", "saving_excl_mt", "freight", "discharge", "clearance",
  "port_costs", "eq_premium", "premium_gap", "eq_cbot", "eq_cbot_diff"];
const OPEN_KEYS = ["freight", "cost_incl", "cost_excl", "landed", "saving_mt", "saving_excl_mt", "potential", "potential_excl", "discharge",
  "clearance", "be_cbot_incl", "be_cbot_excl", "headroom_incl", "headroom_excl", "local_eq_premium", "premium_gap_now"];
const snap = (r, keys) => Object.fromEntries(keys.map(k => [k, r[k]]));
M.savings.forEach(r => { r._f0 = snap(r, SAV_KEYS); });
M.open.forEach(o => { o._f0 = snap(o, OPEN_KEYS); });
// Port-cost basis: the discharge + clearance stored on each contract, or one average for every contract.
const PC = (() => { try { return Object.assign({mode: "actual", avg: 500}, JSON.parse(localStorage.getItem("pp_port_costs_v1") || "{}")); } catch (e) { return {mode: "actual", avg: 500}; } })();
const pcOn = () => PC.mode === "avg" && isN(PC.avg);
function applyPort() {
  if (!pcOn()) { $("pcBanner").style.display = "none"; return; }
  const A = PC.avg;
  M.savings.forEach(r => {
    const d = A - ((r.discharge || 0) + (r.clearance || 0));
    if (isN(r.cost_excl)) { r.cost_excl += d; r.saving_excl_mt = isN(r.local_excl) ? r.local_excl - r.cost_excl : null; r.saving_excl = isN(r.saving_excl_mt) ? r.saving_excl_mt * r.mt : null; }
    if (isN(r.cost)) { r.cost += d; r.saving_mt = r.local - r.cost; r.saving = r.saving_mt * r.mt; }
    r.discharge = A; r.clearance = 0; r.port_avg = true;
    if (r.premium_factor && isN(r.day_fx) && r.day_fx && isN(r.local_excl)) {
      r.port_costs = A;
      const usd = (r.local_excl - A) / r.day_fx / r.premium_factor;
      if (isN(r.day_cbot)) { r.eq_premium = usd - r.day_cbot; r.premium_gap = isN(r.contract_premium) ? r.eq_premium - r.contract_premium : null; }
      if (isN(r.contract_premium)) { r.eq_cbot = usd - r.contract_premium; r.eq_cbot_diff = isN(r.fixed_cbot) ? r.eq_cbot - r.fixed_cbot : null; }
    }
  });
  M.open.forEach(o => {
    const d = A - ((o.discharge || 0) + (o.clearance || 0));
    if (isN(o.cost_excl)) { o.cost_excl += d; o.saving_excl_mt = isN(o.local_excl) ? o.local_excl - o.cost_excl : null; o.potential_excl = isN(o.saving_excl_mt) ? o.saving_excl_mt * o.unconsumed_mt : null; }
    if (isN(o.cost_incl)) { o.cost_incl += d; o.landed = o.cost_incl; o.saving_mt = isN(o.local_incl) ? o.local_incl - o.cost_incl : null; o.potential = isN(o.saving_mt) ? o.saving_mt * o.unconsumed_mt : null; }
    o.discharge = A; o.clearance = 0; o.port_avg = true;
    const fac = FACT[o.base];
    if (fac && isN(o.premium) && o.fx && !flatC(o.pricing_class)) {
      o.be_cbot_excl = isN(o.local_excl) ? (o.local_excl - A) / o.fx / fac - o.premium : null;
      o.be_cbot_incl = isN(o.local_incl) && isN(o.freight) ? (o.local_incl - A - o.freight) / o.fx / fac - o.premium : null;
      ["excl", "incl"].forEach(k => { o["headroom_" + k] = isN(o["be_cbot_" + k]) && isN(o.ref_cbot) ? o["be_cbot_" + k] - o.ref_cbot : null; });
      o.local_eq_premium = isN(o.local_excl) && isN(o.ref_cbot) ? (o.local_excl - A) / o.fx / fac - o.ref_cbot : null;
      o.premium_gap_now = isN(o.local_eq_premium) ? o.local_eq_premium - o.premium : null;
    }
  });
  $("pcBanner").style.display = "block";
  $("pcBanner").innerHTML = `<b>Port costs: one average of ${f2(A)} EGP/MT (discharge + clearance) applied to every contract</b> instead of the values stored on each contract — a what-if for every tab, including the local-equivalent premium and break-even CBOT; the app's data is unchanged. <button class="btn" id="pcBack">Back to actual per contract</button>`;
}
function manualFor(c) {
  if (isN(MAN.per[c.id])) return [MAN.per[c.id], "Manual (this contract)"];
  if (isN(MAN.avg) && (MAN.scope === "all" || !isN(c.freight_egp_mt))) return [MAN.avg, MAN.scope === "all" ? "Manual average (all contracts)" : "Manual average (no route freight)"];
  return [null, ""];
}
function applyManual() {
  M.savings.forEach(r => Object.assign(r, r._f0));
  M.open.forEach(o => Object.assign(o, o._f0));
  applyPort();
  let n = 0;
  C.forEach(c => { const [f] = manualFor(c); c._man = isN(f) ? f : null; if (isN(f)) n++; });
  M.savings.forEach(r => { const c = CI[r.contract_id] || {}; r.man = false;
    if (isN(c._man) && isN(r.cost_excl)) { r.freight = c._man; r.cost = r.cost_excl + c._man; r.saving_mt = r.local - r.cost; r.saving = r.saving_mt * r.mt; r.man = true; } });
  M.open.forEach(o => { const c = CI[o.contract_id] || {}; o.man = false;
    if (isN(c._man) && isN(o.cost_excl)) { o.freight = c._man; o.cost_incl = o.cost_excl + c._man; o.landed = o.cost_incl; o.man = true;
      if (isN(o.local_incl)) { o.saving_mt = o.local_incl - o.cost_incl; o.potential = o.saving_mt * o.unconsumed_mt; }
      const fac = FACT[o.base];
      if (fac && isN(o.premium) && o.fx && isN(o.local_incl) && !flatC(o.pricing_class)) { o.be_cbot_incl = (o.local_incl - (o.discharge || 0) - (o.clearance || 0) - c._man) / o.fx / fac - o.premium;
        o.headroom_incl = isN(o.ref_cbot) ? o.be_cbot_incl - o.ref_cbot : null; } } });
  $("manBanner").style.display = n ? "block" : "none";
  $("manBanner").innerHTML = n ? `<b>Manual freight applied to ${n} contract${n > 1 ? "s" : ""} (what-if).</b> Figures including transport in every tab use your entries; the app's data is unchanged. <button class="btn" id="manBannerClear">Clear manual entries</button>` : "";
  return n;
}
function geoXY(lat, lon, W, H) { return [24 + (lon - 29.15) / 2.95 * (W - 48), 20 + (31.78 - lat) / 2.45 * (H - 40)]; }
function transportMap(comm, dest, v) {
  const W = 980, H = 600, xy = (la, lo) => geoXY(la, lo, W, H), mul = vatMul();
  const rates = FMAP.filter(r => r.commodity === comm && (!dest || r.destination === dest));
  const byPlace = groupBy(v.contracts.filter(c => fcommOf(c) === comm), c => placeOf(c) || "Not recorded");
  const vals = rates.map(r => r.rate).filter(x => x > 0), lo = Math.min(...vals), hi = Math.max(...vals);
  const shade = x => { const t = hi > lo ? (x - lo) / (hi - lo) : 0.5; return `hsl(${210 - t * 190}, 70%, ${45 - t * 5}%)`; };
  const coast = [[30.95, 29.15], [31.08, 29.65], [31.20, 29.92], [31.33, 30.10], [31.45, 30.35], [31.47, 30.62], [31.56, 31.00], [31.53, 31.32], [31.47, 31.62], [31.43, 31.86], [31.27, 32.10]];
  const nileR = [[30.05, 31.23], [30.22, 31.12], [30.55, 30.85], [30.85, 30.68], [31.12, 30.52], [31.40, 30.42]];
  const nileD = [[30.22, 31.12], [30.55, 31.18], [30.85, 31.32], [31.12, 31.58], [31.42, 31.82]];
  const pl = pts => pts.map(([a, b]) => xy(a, b).map(n => n.toFixed(1)).join(",")).join(" ");
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Transportation costs map">`;
  s += `<polygon points="${pl([[31.78, 29.15], ...coast, [31.78, 32.10]])}" fill="var(--s1)" opacity=".08"/><polyline points="${pl(coast)}" fill="none" stroke="var(--axis)" stroke-width="1.5"/>`;
  s += `<polyline points="${pl(nileR)}" fill="none" stroke="var(--s1)" stroke-width="2" opacity=".35"/><polyline points="${pl(nileD)}" fill="none" stroke="var(--s1)" stroke-width="2" opacity=".35"/>`;
  { const [x, y] = xy(31.68, 30.6); s += `<text x="${x}" y="${y}" style="fill:var(--muted)">Mediterranean Sea · البحر المتوسط</text>`; }
  { const [x, y] = xy(30.05, 31.23); s += `<circle cx="${x}" cy="${y}" r="3" fill="var(--muted)"/><text x="${x + 6}" y="${y + 14}" style="fill:var(--muted)">Cairo · القاهرة</text>`; }
  // routes
  rates.forEach(r => { const a = PLACE_GEO[r.place], b = DEST_GEO[r.destination]; if (!a || !b) return;
    const [x1, y1] = xy(a[0], a[1]), [x2, y2] = xy(b[0], b[1]), zero = !(r.rate > 0), n = (byPlace[r.place] || []).filter(c => c.destination === r.destination).length;
    const tip = `<b>${esc(r.place)} → ${esc(r.destination)}</b> · ${esc(FCOMM_LABEL[comm] || comm)}<br>${zero ? "0 in the approval — check before use" : `${f2(r.rate)} EGP/MT excl. VAT · ${f2(r.rate * 1.14)} incl. 14% VAT`}${isN(r.old_rate) ? `<br>previous rate ${f2(r.old_rate)} (before ${esc(r.effective)})` : ""}<br>${n} contract${n === 1 ? "" : "s"} on this route`;
    s += `<g data-tip="${esc(tip)}"><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${zero ? "var(--bad)" : shade(r.rate)}" stroke-width="${zero ? 2 : 3 + Math.min(n, 12) * 0.5}" ${zero ? 'stroke-dasharray="6 5"' : ""} opacity=".85"/>`;
    s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="transparent" stroke-width="14"/></g>`;
    if (dest) { const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      s += `<text x="${mx}" y="${my - 4}" text-anchor="middle" class="lbl" style="font-weight:700;paint-order:stroke;stroke:var(--surface);stroke-width:3px">${zero ? "0 — check" : f0(r.rate * mul)}</text>`; } });
  // plants
  Object.entries(DEST_GEO).forEach(([d, g]) => { const [x, y] = xy(g[0], g[1]);
    s += `<rect x="${x - 8}" y="${y - 8}" width="16" height="16" rx="3" fill="var(--ink)"/><text x="${x - 12}" y="${y + 24}" text-anchor="middle" class="lbl" style="font-weight:700;paint-order:stroke;stroke:var(--surface);stroke-width:4px">${esc(d)} · plant</text>`; });
  // loading places
  const shown = new Set(rates.map(r => r.place).concat(Object.keys(byPlace)));
  [...shown].forEach(p => { const g = PLACE_GEO[p]; if (!g) return; const [x, y] = xy(g[0], g[1]), cs = byPlace[p] || [], mt = sum(cs, c => c.qty_mt);
    const noRoute = cs.length && !rates.some(r => r.place === p), on = $("fPlace").value === p;
    const tip = `<b>${esc(p)}</b> · ${esc(g[2])}<br>${cs.length} ${esc(FCOMM_LABEL[comm] || comm)} contract${cs.length === 1 ? "" : "s"} · ${f0(mt)} MT${noRoute ? "<br><b>No rate in the freight table for this place — add the freight manually on each contract</b>" : ""}<br>Click to show only this loading place`;
    s += `<g data-place="${esc(p)}" style="cursor:pointer" data-tip="${esc(tip)}"><circle cx="${x}" cy="${y}" r="${6 + Math.sqrt(cs.length) * 2.2}" fill="${noRoute ? "var(--surface)" : "var(--s1)"}" stroke="${on ? "var(--ink)" : noRoute ? "var(--bad)" : "var(--surface)"}" stroke-width="${on ? 3 : 2}" ${noRoute ? 'stroke-dasharray="3 3"' : ""}/>`;
    const right = x > W * 0.72, off = 10 + Math.sqrt(cs.length) * 2.2;
    s += `<text x="${right ? x - off : x + off}" y="${y + 4}" text-anchor="${right ? "end" : "start"}" class="lbl" style="paint-order:stroke;stroke:var(--surface);stroke-width:3px">${esc(p)}${cs.length ? ` · ${cs.length}` : ""}${noRoute ? " · no route" : ""}</text></g>`; });
  s += `<text x="${W - 12}" y="${H - 10}" text-anchor="end" style="fill:var(--muted)">Positions approximate · line colour = freight (blue cheaper → red dearer) · thickness = contracts on the route</text></svg>`;
  return s;
}
function renderTransport(v) {
  const comms = [...new Set(FMAP.map(r => r.commodity))].sort((a, b) => (FCOMM_LABEL[a] ? 0 : 1) - (FCOMM_LABEL[b] ? 0 : 1) || a.localeCompare(b));
  const cur = $("tmComm").value || (v.f.base ? (FCOMM[v.f.base] || v.f.base) : "CORN");
  $("tmComm").innerHTML = comms.map(c => `<option value="${esc(c)}">${esc(FCOMM_LABEL[c] || c)}</option>`).join(""); $("tmComm").value = comms.includes(cur) ? cur : comms[0] || "";
  const comm = $("tmComm").value, dest = $("tmDest").value, mul = vatMul();
  // KPIs
  const cs = v.contracts, route = cs.filter(c => /^Freight table/.test(c.freight_basis || "")), entry = cs.filter(c => /^Contract route entry/.test(c.freight_basis || "")), none = cs.filter(c => !isN(c.freight_egp_mt));
  const changed = cs.filter(c => isN(c.freight_app_egp_mt) && (!isN(c.freight_egp_mt) || Math.abs(c.freight_app_egp_mt - c.freight_egp_mt) > 0.01));
  const noneMt = sum(v.sav.filter(r => none.some(c => c.id === r.contract_id)), r => r.mt);
  $("tmK").innerHTML = [
    kcard("Freight from the route table", route.length, `${route.length} contracts`, '<span class="tag good">Specific</span>', `rate for commodity + loading place + plant on the delivery date, + VAT · ${entry.length} more with the route entered on the contract`),
    kcard("No route freight — add manually", -none.length, `${none.length} contracts`, '<span class="tag bad">Missing</span>', `${f0(noneMt)} MT consumed compared excluding transport only · ${esc([...new Set(none.map(c => placeOf(c) || "no place"))].join(", ") || "—")}`),
    kcard("Changed from the app's stored freight", null, `${changed.length} contracts`, '<span class="tag pot">Review</span>', "stored value was a different route, commodity or VAT basis — see the table below")].join("");
  // map + rates
  $("tmMap").innerHTML = transportMap(comm, dest, v);
  const eff = [...new Set(FMAP.map(r => r.effective).filter(Boolean))].join(", ");
  $("tmRatesSub").textContent = `${FCOMM_LABEL[comm] || comm} · EGP/MT · current rates effective ${eff || "—"}; previous rates apply to earlier deliveries. Shown ${mul > 1 ? "incl. 14% VAT" : "excl. VAT"}.`;
  const rr = FMAP.filter(r => r.commodity === comm), places = [...new Set(rr.map(r => r.place))].sort((a, b) => regionOf(a).localeCompare(regionOf(b)) || a.localeCompare(b));
  const cell2 = (p, d) => { const r = rr.find(x => x.place === p && x.destination === d); if (!r) return '<td class="na">—</td><td class="na">—</td>';
    return r.rate > 0 ? `${td(r.rate * mul, f2)}${td(isN(r.old_rate) ? r.old_rate * mul : null, f2)}` : '<td class="n"><span class="tag bad" title="0 in the approval">0 — check</span></td><td class="na">—</td>'; };
  $("tmRates").innerHTML = `<thead><tr><th>Loading place</th><th>Region</th><th class="n">→ النوبارية</th><th class="n">previous</th><th class="n">→ الصف</th><th class="n">previous</th><th class="n">Contracts</th></tr></thead><tbody>` +
    places.map(p => `<tr class="row" data-place="${esc(p)}"><td>${esc(p)}</td><td class="note">${esc(regionOf(p))}</td>${cell2(p, "النوبارية")}${cell2(p, "الصف")}${td(cs.filter(c => fcommOf(c) === comm && placeOf(c) === p).length)}</tr>`).join("") + "</tbody>";
  // contracts by loading place
  const statusOf = c => isN(c._man) ? '<span class="tag pot">Manual</span>' : !isN(c.freight_egp_mt) ? '<span class="tag bad">No route — add manually</span>' :
    /^Contract route entry/.test(c.freight_basis || "") ? '<span class="tag act">Contract route entry</span>' : '<span class="tag good">Route table</span>';
  const rows = cs.slice().sort((a, b) => regionOf(placeOf(a)).localeCompare(regionOf(placeOf(b))) || placeOf(a).localeCompare(placeOf(b)) || String(b.storage_start || b.delivery_date).localeCompare(String(a.storage_start || a.delivery_date)));
  const groups = groupBy(rows, c => placeOf(c) || "Not recorded");
  let h = `<thead><tr><th>Contract</th><th>Commodity</th><th>Plant</th><th>Delivery / storage</th><th class="n">MT</th><th class="n">Freight used, incl. VAT</th><th>Status</th><th class="n">Route rate (excl. VAT)</th><th class="n">App value</th><th class="n">Used − app</th><th class="n">Manual freight</th><th>Basis / note</th></tr></thead><tbody>`;
  Object.entries(groups).forEach(([p, g]) => {
    const fr = g.map(c => isN(c._man) ? c._man : c.freight_egp_mt).filter(isN);
    h += `<tr class="tot"><td colspan="12">${esc(regionOf(p === "Not recorded" ? "" : p))} · <b>${esc(p)}</b> — ${g.length} contract${g.length > 1 ? "s" : ""} · ${f0(sum(g, c => c.qty_mt))} MT${fr.length ? ` · freight ${f0(Math.min(...fr))}–${f0(Math.max(...fr))} EGP/MT` : ""}${g.some(c => !isN(c.freight_egp_mt)) ? ' · <span class="neg">some contracts need the freight entered</span>' : ""}</td></tr>`;
    g.forEach(c => { const used = isN(c._man) ? c._man : c.freight_egp_mt, diff = isN(used) && isN(c.freight_app_egp_mt) ? used - c.freight_app_egp_mt : null;
      h += `<tr><td><b>${esc(c.contract)}</b><br><span class="note">${esc(c.supplier)} · ${esc(c.id)}</span></td><td>${esc(c.commodity)}</td><td>${esc(c.destination || "—")}</td><td>${esc(c.storage_start || c.delivery_date || "—")}</td>${td(c.qty_mt)}` +
        `<td class="n">${isN(used) ? `<b>${f2(used)}</b>` : NA_}</td><td>${statusOf(c)}</td>` +
        `<td class="n">${isN(c.route_rate_ex) ? `${f2(c.route_rate_ex)}<br><span class="note">${esc(c.route_rate_which)}</span>` : "—"}</td>${td(c.freight_app_egp_mt, f2)}${td(diff, f2, 1)}` +
        `<td class="n"><input class="ctl manIn" type="number" step="0.01" min="0" style="width:96px" data-id="${esc(c.id)}" value="${isN(MAN.per[c.id]) ? MAN.per[c.id] : ""}" placeholder="${isN(c.freight_egp_mt) ? "" : "add"}"></td>` +
        `<td class="note" style="white-space:normal;min-width:260px">${esc(isN(c._man) ? manualFor(c)[1] : c.freight_basis || "")}${c.freight_note ? `<br><span class="neg">${esc(c.freight_note)}</span>` : ""}</td></tr>`; });
  });
  $("tmContracts").innerHTML = h + "</tbody>";
  const nm = Object.keys(MAN.per).length;
  $("manNote").innerHTML = `${isN(MAN.avg) ? `Average ${f2(MAN.avg)} EGP/MT applied to ${MAN.scope === "all" ? "all contracts" : "contracts without route freight"}. ` : "No manual average. "}${nm} contract-specific manual entr${nm === 1 ? "y" : "ies"}.`;
  if (isN(MAN.avg)) $("manAvg").value = MAN.avg; $("manScope").value = MAN.scope;
}
function manualCsv() {
  const rows = [["Contract ID", "Contract", "Commodity", "Loading place", "Plant", "Route freight used EGP/MT", "Manual freight EGP/MT", "Manual source"]].concat(
    C.filter(c => isN(c._man) || !isN(c.freight_egp_mt)).map(c => [c.id, c.contract, c.commodity, c.loading_place || "", c.destination || "", isN(c.freight_egp_mt) ? c.freight_egp_mt.toFixed(2) : "N/A — add manually", isN(c._man) ? c._man : "", isN(c._man) ? manualFor(c)[1] : "needs freight"]));
  const csv = "﻿" + rows.map(r => r.map(x => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"})); a.download = `Manual_freight_${M.as_of}.csv`;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

// ── wiring ───────────────────────────────────────────────────────────
// ── Actions & alerts (from the model; not affected by the filters) ──
function renderActions() {
  const AL = M.alerts || [], EX = M.exposure || {cbot: [], fx: []}, SL = M.since_last || {rows: []}, FX_ = M.data_to_fix || [];
  const trig = AL.filter(a => a.status === "TRIGGERED"), high = FX_.filter(x => x.severity === "High");
  $("akpis").innerHTML = [
    kcard("Pricing alerts triggered", trig.length ? -1 : 0, `${trig.length} of ${AL.length}`, '<span class="tag pot">Alerts</span>', AL.length ? "targets set in the app on contracts not priced yet" : "no targets set yet — use Pricing alerts… in the app"),
    kcard("Tonnes not priced", null, `${f0(EX.total_unpriced_mt)} MT`, '<span class="tag">Exposure</span>', `${money("EGP", EX.total_cbot_egp_per_step)} per 10 ¢ CBOT move`),
    kcard("Tonnes on provisional FX", null, `${f0(EX.total_fx_mt)} MT`, '<span class="tag">Exposure</span>', `${money("EGP", EX.total_fx_egp_per_step)} per 1 EGP FX move · no Form 4 yet`),
    kcard("Data to fix", high.length ? -1 : 0, `${FX_.length} items`, '<span class="tag">To do</span>', `${high.length} high · ${FX_.filter(x => x.severity === "Medium").length} medium`)].join("");
  const f2n = x => isN(x) ? f2(x) : "—";
  $("tAl").innerHTML = AL.length ? `<thead><tr><th>Status</th><th>Contract</th><th>Commodity</th><th>Futures</th><th class="n">Not priced MT</th><th class="n">Live CBOT</th><th class="n">Break-even</th><th class="n">Headroom</th><th class="n">Fix at ≤</th><th class="n">Protect ≥</th><th class="n">Headroom ≤</th><th>Why / note</th></tr></thead><tbody>` +
    AL.map(a => `<tr class="row" data-goto="${esc(a.contract_id)}"><td>${a.status === "TRIGGERED" ? '<span class="tag bad">TRIGGERED</span>' : `<span class="tag">${esc(a.status)}</span>`}</td><td><b>${esc(a.contract)}</b><br><span class="note">${esc(a.supplier)}</span></td><td>${esc(a.base)}</td><td>${esc(a.futures)}</td>${td(a.unpriced_mt)}` +
      `<td class="n">${f2n(a.cbot)} <span class="note">${a.cbot_live ? "live" : "stored"}</span></td><td class="n">${f2n(a.be_cbot)}</td><td class="n ${sg(a.headroom)}">${f2n(a.headroom)} <span class="note">${esc(a.headroom_basis)}</span></td><td class="n">${f2n(a.cbot_below)}</td><td class="n">${f2n(a.cbot_above)}</td><td class="n">${f2n(a.headroom_below)}</td>` +
      `<td>${a.triggered.length ? `<b class="neg">${a.triggered.map(esc).join("<br>")}</b>` : ""}${a.note ? `<br><span class="note">${esc(a.note)}</span>` : ""}</td></tr>`).join("") + "</tbody>"
    : '<tbody><tr><td class="note">No pricing targets set. In the app, use “Pricing alerts…” to set a CBOT to fix at, a CBOT to protect against, or a minimum headroom against local.</td></tr></tbody>';
  $("tExC").innerHTML = `<thead><tr><th>Commodity</th><th>Futures</th><th class="n">Contracts</th><th class="n">Not priced MT</th><th class="n">of which consumed</th><th class="n">Avg premium</th><th class="n">CBOT now</th><th class="n">EGP per ±step</th></tr></thead><tbody>` +
    (EX.cbot || []).map(r => `<tr><td><b>${esc(r.base)}</b></td><td>${esc(r.futures)}</td><td class="n" title="${esc(r.contract_names)}">${r.contracts}</td>${td(r.unpriced_mt)}${td(r.consumed_unpriced_mt)}${td(r.avg_premium, f2)}${td(r.cbot, f2)}<td class="n"><b>±${f0(r.egp_per_step)}</b> <span class="note">per ${r.step} ${esc(r.unit)}</span></td></tr>`).join("") +
    `<tr class="tot"><td>Total</td><td></td><td></td>${td(EX.total_unpriced_mt)}<td></td><td></td><td></td><td class="n">±${f0(EX.total_cbot_egp_per_step)}</td></tr></tbody>`;
  $("tExF").innerHTML = `<thead><tr><th>Commodity</th><th class="n">Contracts without Form 4</th><th class="n">MT</th><th class="n">Value USD</th><th class="n">EGP per ±1 EGP FX</th></tr></thead><tbody>` +
    (EX.fx || []).map(r => `<tr><td><b>${esc(r.base)}</b></td>${td(r.contracts)}${td(r.mt)}${td(r.usd)}<td class="n"><b>±${f0(r.egp_per_step)}</b></td></tr>`).join("") +
    `<tr class="tot"><td>Total</td><td></td>${td(EX.total_fx_mt)}<td></td><td class="n">±${f0(EX.total_fx_egp_per_step)}</td></tr></tbody>`;
  $("slSub").textContent = SL.previous ? `Against the report of ${SL.previous.generated} (data as of ${SL.previous.as_of}).` : "No earlier report saved yet — the app keeps each export, so the next report will show what changed.";
  $("tSl").innerHTML = SL.rows.length ? `<thead><tr><th>Figure</th><th class="n">Previous</th><th class="n">Now</th><th class="n">Change</th></tr></thead><tbody>` +
    SL.rows.map(r => { const d = /CBOT|FX/.test(r.label) ? f2 : f0; return `<tr><td>${esc(r.label)} <span class="note">${esc(r.unit)}</span></td>${td(r.previous, d)}${td(r.now, d)}<td class="n ${/CBOT|FX/.test(r.label) ? "" : sg(r.change)}">${isN(r.change) ? (r.change > 0 ? "+" : "") + d(r.change) : "—"}</td></tr>`; }).join("") + "</tbody>" : "";
  $("tFix").innerHTML = FX_.length ? `<thead><tr><th>Severity</th><th>Issue</th><th>Contract</th><th>Commodity</th><th class="n">MT</th><th>Detail</th><th>What to do</th></tr></thead><tbody>` +
    FX_.map(x => `<tr class="row" ${x.contract_id ? `data-goto="${esc(x.contract_id)}"` : ""}><td><span class="tag ${x.severity === "High" ? "bad" : x.severity === "Medium" ? "pot" : ""}">${esc(x.severity)}</span></td><td>${esc(x.category)}</td><td>${x.contract ? `<b>${esc(x.contract)}</b>` : "—"}</td><td>${esc(x.base)}</td>${td(x.mt)}<td>${esc(x.detail)}</td><td class="note">${esc(x.action)}</td></tr>`).join("") + "</tbody>"
    : '<tbody><tr><td class="note">Nothing to fix.</td></tr></tbody>';
}
// Pinned horizontal scrollbars: one per wide scroll container, synced both ways.
function hbars() {
  document.querySelectorAll("main .tw, main .detwrap").forEach(el => {
    let bar = el.nextElementSibling && el.nextElementSibling.classList.contains("hbar") ? el.nextElementSibling : null;
    const wide = el.offsetParent !== null && el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflowX !== "visible";
    if (!wide) { if (bar) bar.remove(); el.classList.remove("hasbar"); return; }
    if (!bar) {
      bar = document.createElement("div"); bar.className = "hbar"; bar.innerHTML = "<div></div>";
      el.after(bar);
      let lock = false;
      bar.addEventListener("scroll", () => { if (lock) { lock = false; return; } lock = true; el.scrollLeft = bar.scrollLeft; });
      el.addEventListener("scroll", () => { if (lock) { lock = false; return; } lock = true; bar.scrollLeft = el.scrollLeft; });
    }
    const inner = !!el.parentElement.closest(".tw");
    bar.classList.toggle("inner", inner);
    bar.style.width = el.clientWidth + "px";
    bar.firstChild.style.width = el.scrollWidth + "px";
    bar.scrollLeft = el.scrollLeft;
    // A day table inside a scrolling table keeps its own scrollbar and gets a screen-pinned copy while that one is off-screen.
    el.classList.toggle("hasbar", !inner);
  });
  placeInnerBars();
}
function placeInnerBars() {
  const H = window.innerHeight;
  document.querySelectorAll(".hbar.inner").forEach(bar => {
    const el = bar.previousElementSibling, r = el && el.getBoundingClientRect();
    const show = r && r.top < H - 60 && r.bottom > H - 18;
    bar.style.display = show ? "block" : "none";
    if (show) { bar.style.left = Math.max(r.left, 0) + "px"; bar.style.width = Math.min(r.width, window.innerWidth - Math.max(r.left, 0)) + "px"; bar.scrollLeft = el.scrollLeft; }
  });
}
window.addEventListener("scroll", () => requestAnimationFrame(placeInnerBars), {passive: true});
let _hbT = 0;
const hbarsSoon = () => { cancelAnimationFrame(_hbT); _hbT = requestAnimationFrame(hbars); };
new MutationObserver(muts => { if (muts.some(m => !(m.target.classList && m.target.classList.contains("hbar")))) hbarsSoon(); })
  .observe(document.querySelector("main"), {childList: true, subtree: true});
window.addEventListener("resize", hbarsSoon);
document.addEventListener("click", e => { if (e.target.closest(".tab")) hbarsSoon(); });
function render() {
  applyManual();
  const v = view(), K = kpis(v);
  renderOverview(v, K); renderSavings(v); renderSvOpen(v); renderTransport(v); renderContracts(v); renderCbot(v); renderOpen(v); renderTrends(v);
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
  ((M.alerts || []).some(a => a.status === "TRIGGERED") || (M.data_to_fix || []).length ? `<button class="badge no" id="bAct">${(M.alerts || []).filter(a => a.status === "TRIGGERED").length} alert(s) · ${(M.data_to_fix || []).length} to fix</button>` : "") +
  `<span class="tag act">Actual = consumed (FIFO estimated)</span><span class="tag pot">Potential = not yet consumed</span><span class="tag ben">Benchmark = CBOT comparison</span>`;
$("bReady").addEventListener("click", () => { if (!document.body.classList.contains("mgmt")) showTab("quality"); });
if ($("bAct")) $("bAct").addEventListener("click", () => showTab("actions"));
renderActions();
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.p)));
["fBase", "fOrigin", "fSupplier", "fFrom", "fTo", "fOpen", "fFix", "fDQ", "fAge", "fRegion", "fPlace"].forEach(id => $(id).addEventListener("change", render));
$("fOrder").addEventListener("change", () => { S.sort = {}; render(); });
["oBucket", "oRes", "oRem"].forEach(id => $(id).addEventListener("change", () => renderOpen(view())));
const TXN = {side: "Side-by-side: including transport = inland transport on both sides; excluding = without it. Ocean freight stays in CIF.",
  incl: "Including transportation: landed cost with inland freight vs local quote + local transport.", excl: "Excluding transportation: landed cost without inland freight vs the local quote itself."};
$("txNote").textContent = TXN.side;
function pcSave() { try { localStorage.setItem("pp_port_costs_v1", JSON.stringify(PC)); } catch (e) { /* per-viewer convenience only */ } }
function pcSync() { document.querySelectorAll("#pcSeg button").forEach(x => x.classList.toggle("on", x.dataset.pc === PC.mode)); $("pcAvg").value = PC.avg; }
$("pcSeg").addEventListener("click", e => { const b = e.target.closest("button[data-pc]"); if (!b) return; PC.mode = b.dataset.pc; pcSave(); pcSync(); S.sort = {}; render(); });
$("pcAvg").addEventListener("change", () => { const v = parseFloat($("pcAvg").value); if (isFinite(v) && v >= 0 && v !== PC.avg) { PC.avg = v; PC.mode = "avg"; pcSave(); pcSync(); render(); } });
document.addEventListener("click", e => { if (e.target.id === "pcBack") { PC.mode = "actual"; pcSave(); pcSync(); render(); } });
pcSync();
$("txSeg").addEventListener("click", e => { const b = e.target.closest("button[data-tx]"); if (!b) return;
  S.tx = b.dataset.tx; S.sort = {}; document.querySelectorAll("#txSeg button").forEach(x => x.classList.toggle("on", x === b)); $("txNote").textContent = TXN[S.tx]; render(); });
$("fQ").addEventListener("input", render);
$("fPreset").addEventListener("change", e => { const v = e.target.value, end = M.as_of; let start = "";
  if (v === "ytd") start = end.slice(0, 4) + "-01-01"; else if (v) { const d = new Date(end); d.setDate(d.getDate() - +v); start = d.toISOString().slice(0, 10); }
  $("fFrom").value = start; $("fTo").value = v ? end : ""; render(); });
$("bReset").addEventListener("click", () => { ["fBase", "fOrigin", "fSupplier", "fQ", "fFrom", "fTo", "fPreset", "fOpen", "fFix", "fDQ", "fAge", "fOrder", "fRegion", "fPlace", "oBucket", "oRes", "oRem"].forEach(id => $(id).value = ""); render(); });
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
["tmComm", "tmDest", "tmVat"].forEach(id => $(id).addEventListener("change", () => renderTransport(view())));
$("manApply").addEventListener("click", () => { const x = parseFloat($("manAvg").value); MAN.avg = isFinite(x) && x >= 0 ? x : null; MAN.scope = $("manScope").value; saveMan(); render(); });
$("manClear").addEventListener("click", () => { MAN.avg = null; MAN.per = {}; $("manAvg").value = ""; saveMan(); render(); });
$("manCsv").addEventListener("click", manualCsv);
document.addEventListener("change", e => { const t = e.target; if (!t.classList || !t.classList.contains("manIn")) return;
  const x = parseFloat(t.value); if (isFinite(x) && x >= 0) MAN.per[t.dataset.id] = x; else delete MAN.per[t.dataset.id]; saveMan(); render(); });
$("dqTiles").addEventListener("click", e => { const b = e.target.closest("button[data-dq]"); if (!b || !b.dataset.dq) return;
  S.dqTile = S.dqTile === b.dataset.dq ? "" : b.dataset.dq; renderQuality(); });
document.addEventListener("click", e => {
  const th = e.target.closest("th[data-sort]");
  if (th) { const k = th.dataset.sort, i = +th.dataset.i, cur = S.sort[k]; S.sort[k] = {i, dir: cur && cur.i === i ? -cur.dir : -1}; render(); return; }
  if (e.target.id === "manBannerClear") { MAN.avg = null; MAN.per = {}; $("manAvg").value = ""; saveMan(); render(); return; }
  const pl = e.target.closest("[data-place]"); if (pl) { const p = pl.getAttribute("data-place"); $("fPlace").value = $("fPlace").value === p ? "" : p; render(); return; }
  const g = e.target.closest("[data-goto]"); if (g) { openContract(g.getAttribute("data-goto")); return; }
  const cpr = e.target.closest("tr.row[data-cp]");
  if (cpr) { S.cpOpen = S.cpOpen || new Set(); const id = cpr.dataset.cp; S.cpOpen.has(id) ? S.cpOpen.delete(id) : S.cpOpen.add(id); renderCbot(view()); return; }
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
