"""Standalone, offline HTML for the Procurement Decision & Contract Timing Report.

One file: the report model as embedded JSON, the styles, and a small script
that draws every chart as SVG and runs the filters, sorting and search.
No library, font or image is fetched from anywhere, so it opens the same
on a plane as at the desk, and prints to PDF from the browser.
"""

from __future__ import annotations

import html
import json

REPORT_HTML_VERSION = "1.0"


def render(model):
    """The complete HTML document for ``model``."""
    data = json.dumps(model, default=str, ensure_ascii=False, separators=(",", ":"))
    # Inside <script>, only "</" can end the block early.
    data = data.replace("</", "<\\/")
    title = html.escape(model.get("title") or "Procurement Decision & Contract Timing Report")
    return (_TEMPLATE.replace("__TITLE__", title)
            .replace("__DATA__", data))


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#16243a;--muted:#5d6b7e;--line:#dfe5ee;--bg:#f5f7fa;--card:#fff;--navy:#1f3a5f;--blue:#1a6ebd;
--good:#1a7a1a;--good-bg:#e3f4e1;--mid:#9a6b00;--mid-bg:#fff4d6;--bad:#b3261e;--bad-bg:#fbe3e1;--na:#6b7280;--na-bg:#eef0f3}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--navy);color:#fff;padding:22px 28px}
header h1{margin:0 0 4px;font-size:22px}
header p{margin:2px 0;color:#c9d6e8;font-size:13px}
main{max-width:1320px;margin:0 auto;padding:18px 20px 60px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:16px 0}
h2{font-size:17px;margin:0 0 10px;color:var(--navy)}
h3{font-size:14px;margin:14px 0 6px;color:var(--navy)}
.note{color:var(--muted);font-size:12.5px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fbfcfe}
.kpi .l{font-size:12px;color:var(--muted)}
.kpi .v{font-size:20px;font-weight:700;margin-top:2px}
.kpi .s{font-size:11.5px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media (max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}
.filters{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:10px;align-items:center;
background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:16px 0;box-shadow:0 2px 6px rgba(0,0,0,.04)}
.filters label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:2px}
select,input[type=search]{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;min-width:140px}
button{font:inherit;padding:6px 12px;border:1px solid var(--blue);background:var(--blue);color:#fff;border-radius:6px;cursor:pointer}
button.ghost{background:#fff;color:var(--blue)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f0f4f9;position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap}
th.sorted-asc::after{content:" ▲";font-size:10px}th.sorted-desc::after{content:" ▼";font-size:10px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tablewrap{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11.5px;font-weight:600;white-space:nowrap}
.Favorable{background:var(--good-bg);color:var(--good)}.Acceptable{background:var(--mid-bg);color:var(--mid)}
.Unfavorable{background:var(--bad-bg);color:var(--bad)}.Insufficient,.NA,.Pending{background:var(--na-bg);color:var(--na)}
.pos{color:var(--good)}.neg{color:var(--bad)}
svg text{font:11px -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;fill:#44546a}
.chart{width:100%;overflow:hidden}
.tabs{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.tabs button{background:#fff;color:var(--blue);padding:4px 10px}
.tabs button.on{background:var(--blue);color:#fff}
.tip{position:fixed;pointer-events:none;background:#16243a;color:#fff;font-size:12px;padding:6px 8px;border-radius:6px;display:none;z-index:20;max-width:320px}
details.contract{border:1px solid var(--line);border-radius:8px;margin:8px 0;background:#fff}
details.contract>summary{cursor:pointer;padding:10px 12px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;list-style:none}
details.contract>summary::-webkit-details-marker{display:none}
details.contract>summary::before{content:"▸";color:var(--muted)}
details.contract[open]>summary::before{content:"▾"}
details.contract .body{padding:4px 14px 14px;border-top:1px solid var(--line)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:4px 18px}
.kv div{display:flex;justify-content:space-between;gap:10px;border-bottom:1px dotted var(--line);padding:2px 0}
.kv span:first-child{color:var(--muted)}
.formula{font-family:ui-monospace,Consolas,monospace;background:#f6f8fb;border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:12px;overflow-x:auto}
ul.why{margin:6px 0 0 18px;padding:0}
.flag{background:var(--mid-bg);border-left:3px solid var(--mid);padding:6px 10px;border-radius:4px;margin:6px 0;font-size:12.5px}
.flag.bad{background:var(--bad-bg);border-color:var(--bad)}.flag.good{background:var(--good-bg);border-color:var(--good)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:4px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px}
@media print{
 body{background:#fff;font-size:11.5px}
 .filters,.noprint,.tabs{display:none!important}
 section{border:none;padding:6px 0;margin:6px 0;break-inside:auto}
 .tablewrap{max-height:none;overflow:visible;border:none}
 th{position:static}
 details.contract{break-inside:avoid;border-color:#bbb}
 header{background:#fff;color:var(--ink);border-bottom:2px solid var(--navy)}
 header p{color:var(--muted)}
}
</style>
</head>
<body>
<header>
 <h1 id="h-title"></h1>
 <p id="h-sub"></p>
 <p>Savings against local and timing opportunity answer different questions and are never added together. Best-day figures are hindsight benchmarks, not claims that the day was knowable.</p>
</header>
<main>
<div class="filters noprint" id="filters">
 <label>Commodity<select id="f-base"></select></label>
 <label>Supplier<select id="f-supplier"></select></label>
 <label>Final assessment<select id="f-verdict"></select></label>
 <label>Timing<select id="f-timing"></select></label>
 <label>Search<input type="search" id="f-q" placeholder="contract, ID, origin…"></label>
 <span style="flex:1"></span>
 <button class="ghost" id="b-expand">Expand all</button>
 <button id="b-print">Print / PDF</button>
</div>

<section id="dash">
 <h2>Executive dashboard</h2>
 <p class="note" id="dash-note"></p>
 <div class="kpis" id="kpis"></div>
 <div class="grid3" style="margin-top:14px">
  <div><h3>Saving vs local by commodity, EGP</h3><div class="chart" id="c-savings"></div></div>
  <div><h3>Final assessment</h3><div class="chart" id="c-verdicts"></div></div>
  <div><h3>Timing assessment</h3><div class="chart" id="c-timing"></div></div>
 </div>
</section>

<section id="findings"><h2>Major findings</h2><ul id="findings-list" class="why"></ul></section>

<section id="cbot">
 <h2>CBOT history, pricing days and hindsight best days</h2>
 <div class="tabs" id="cbot-tabs"></div>
 <div class="chart" id="c-cbot"></div>
 <div class="legend"><span><i style="background:#1f3a5f"></i>CBOT (stored front-month history)</span>
  <span><i style="background:#b3261e"></i>CBOT fixed (contract)</span>
  <span><i style="background:#1a7a1a"></i>Hindsight best day in its window</span></div>
 <h3>Timeline — each assessed fixing against its window</h3>
 <div class="chart" id="c-timeline"></div>
 <p class="note">Bar = the window searched (days before and after the pricing day). Red = when the CBOT was fixed; green = the lowest day in the window (hindsight).</p>
</section>

<section id="missed">
 <h2>Missed opportunities — ranked</h2>
 <div class="grid2">
  <div class="chart" id="c-missed"></div>
  <div><h3>Arrivals that prevented a shortage</h3><div class="tablewrap" style="max-height:330px"><table id="t-tight"></table></div>
   <p class="note">Stock before arrival was below the safety cover: buying earlier kept (or shortened a stop in) production.</p></div>
 </div>
</section>

<section id="register">
 <h2>Contract comparison</h2>
 <p class="note">Click a column to sort; click a contract to open its full analysis below.</p>
 <div class="tablewrap"><table id="t-main"></table></div>
</section>

<section id="stock"><h2>Stock coverage today</h2><div class="tablewrap" style="max-height:none"><table id="t-stock"></table></div>
 <p class="note">Projected shortage = consumption at the configured daily rate on days when no recorded cargo had stock left.</p></section>

<section id="contracts"><h2>Contract-by-contract decision report</h2><div id="cards"></div></section>

<section id="method"><h2>Data &amp; methodology</h2><div id="method-body"></div></section>
</main>
<div class="tip" id="tip"></div>
<script type="application/json" id="report-data">__DATA__</script>
<script>
(function(){
"use strict";
var M = JSON.parse(document.getElementById("report-data").textContent);
var ROWS = M.contracts, P = M.params;
var $ = function(id){return document.getElementById(id);};
var esc = function(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});};
var isNum = function(v){return typeof v==="number" && isFinite(v);};
var f0 = function(v){return isNum(v)? v.toLocaleString("en-US",{maximumFractionDigits:0}) : "—";};
var f2 = function(v){return isNum(v)? v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}) : "—";};
var sg0 = function(v){return isNum(v)? (v>0?"+":"")+f0(v) : "—";};
var pct = function(v,d){return isNum(v)? v.toFixed(d==null?1:d)+"%" : "—";};
var cls = function(v){return isNum(v)? (v>=0?"pos":"neg") : "";};
var badgeClass = function(v){v=v||"";return v.indexOf("Insufficient")===0?"Insufficient":(v==="Not applicable"?"NA":(v==="Pending"?"Pending":v));};
var badge = function(v){return '<span class="badge '+badgeClass(v)+'">'+esc(v||"—")+'</span>';};
var T = function(r){return r.timing||{};};
var C = function(r){return r.coverage||{};};

$("h-title").textContent = M.title;
$("h-sub").textContent = "Generated "+M.generated+" · data as of "+M.as_of+" · "+ROWS.length+" contracts · "+M.app;

// ── filters ──────────────────────────────────────────────────────────
var uniq = function(key){var s={};ROWS.forEach(function(r){s[key(r)]=1;});return Object.keys(s).filter(Boolean).sort();};
var fill = function(id, values, all){$(id).innerHTML='<option value="ALL">'+all+'</option>'+values.map(function(v){return '<option>'+esc(v)+'</option>';}).join("");};
fill("f-base", uniq(function(r){return r.base;}), "All commodities");
fill("f-supplier", uniq(function(r){return r.supplier;}), "All suppliers");
fill("f-verdict", ["Favorable","Acceptable","Unfavorable","Insufficient Data"], "All");
fill("f-timing", ["Favorable","Acceptable","Unfavorable","Insufficient Data","Not applicable","Pending"], "All");
var state = {sort:"opp", dir:-1, cbot:null};
function current(){
  var b=$("f-base").value, s=$("f-supplier").value, v=$("f-verdict").value, t=$("f-timing").value, q=$("f-q").value.trim().toLowerCase();
  return ROWS.filter(function(r){
    if(b!=="ALL" && r.base!==b) return false;
    if(s!=="ALL" && r.supplier!==s) return false;
    if(v!=="ALL" && r.final_assessment!==v) return false;
    if(t!=="ALL" && T(r).assessment!==t) return false;
    if(q && (r.id+" "+r.contract+" "+r.origin+" "+r.commodity+" "+r.supplier).toLowerCase().indexOf(q)<0) return false;
    return true;
  });
}
["f-base","f-supplier","f-verdict","f-timing"].forEach(function(id){$(id).addEventListener("change",renderAll);});
$("f-q").addEventListener("input",renderAll);
$("b-print").addEventListener("click",function(){window.print();});
$("b-expand").addEventListener("click",function(){
  var all=document.querySelectorAll("details.contract"), open=Array.prototype.some.call(all,function(d){return !d.open;});
  all.forEach(function(d){d.open=open;}); this.textContent=open?"Collapse all":"Expand all";});
window.addEventListener("beforeprint",function(){document.querySelectorAll("details.contract").forEach(function(d){d.open=true;});});

// ── tooltip ──────────────────────────────────────────────────────────
var tip=$("tip");
function bindTips(root){
  root.querySelectorAll("[data-tip]").forEach(function(el){
    el.addEventListener("mousemove",function(e){tip.style.display="block";tip.innerHTML=el.getAttribute("data-tip");
      tip.style.left=Math.min(e.clientX+12,window.innerWidth-330)+"px";tip.style.top=(e.clientY+12)+"px";});
    el.addEventListener("mouseleave",function(){tip.style.display="none";});
  });
}

// ── tiny SVG chart kit ───────────────────────────────────────────────
function niceTicks(lo,hi,n){if(!(hi>lo)){hi=lo+1;}var step=Math.pow(10,Math.floor(Math.log10((hi-lo)/n)));
  var err=(hi-lo)/n/step; step*= err>=7.5?10:err>=3.5?5:err>=1.5?2:1; var t=[],v=Math.ceil(lo/step)*step;
  for(;v<=hi+1e-9;v+=step)t.push(v); return t;}
function short(v){var a=Math.abs(v);return a>=1e9?(v/1e9).toFixed(1)+"B":a>=1e6?(v/1e6).toFixed(1)+"M":a>=1e3?(v/1e3).toFixed(0)+"k":String(Math.round(v));}
function bars(el, items, opts){
  opts=opts||{}; var W=420,H=opts.h||220,L=opts.horizontal?150:46,R=12,Tp=10,B=opts.horizontal?22:40;
  if(!items.length){el.innerHTML='<p class="note">Nothing to show for this selection.</p>';return;}
  var vals=[];items.forEach(function(it){(it.values||[it.value]).forEach(function(v){vals.push(v||0);});});
  var lo=Math.min(0,Math.min.apply(null,vals)), hi=Math.max(0,Math.max.apply(null,vals)); if(hi===lo)hi=lo+1;
  var ticks=niceTicks(lo,hi,4); lo=Math.min(lo,ticks[0]); hi=Math.max(hi,ticks[ticks.length-1]);
  var s='<svg viewBox="0 0 '+W+' '+H+'" width="100%" role="img">';
  var colors=opts.colors||["#1a6ebd","#e0a100"], series=(items[0].values||[0]).length;
  if(opts.horizontal){
    var x=function(v){return L+(v-lo)/(hi-lo)*(W-L-R);}, bh=(H-Tp-B)/items.length;
    ticks.forEach(function(t){s+='<line x1="'+x(t)+'" x2="'+x(t)+'" y1="'+Tp+'" y2="'+(H-B)+'" stroke="#e8edf3"/><text x="'+x(t)+'" y="'+(H-6)+'" text-anchor="middle">'+short(t)+'</text>';});
    items.forEach(function(it,i){var y=Tp+i*bh, v=it.value||0, a=x(Math.min(0,v)), w=Math.abs(x(v)-x(0));
      s+='<text x="'+(L-6)+'" y="'+(y+bh*0.62)+'" text-anchor="end">'+esc(it.label.length>24?it.label.slice(0,23)+"…":it.label)+'</text>';
      s+='<rect data-tip="'+esc(it.tip||it.label)+'" x="'+a+'" y="'+(y+bh*0.15)+'" width="'+Math.max(w,1)+'" height="'+(bh*0.7)+'" fill="'+(it.color||colors[0])+'" rx="2"/>';});
  } else {
    var y=function(v){return Tp+(hi-v)/(hi-lo)*(H-Tp-B);}, bw=(W-L-R)/items.length;
    ticks.forEach(function(t){s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(t)+'" y2="'+y(t)+'" stroke="#e8edf3"/><text x="'+(L-6)+'" y="'+(y(t)+4)+'" text-anchor="end">'+short(t)+'</text>';});
    items.forEach(function(it,i){var vs=it.values||[it.value], gw=bw*0.75/vs.length;
      vs.forEach(function(v,k){v=v||0;var x0=L+i*bw+bw*0.125+k*gw, top=y(Math.max(0,v)), h=Math.abs(y(v)-y(0));
        s+='<rect data-tip="'+esc((it.tips&&it.tips[k])||it.tip||it.label)+'" x="'+x0+'" y="'+top+'" width="'+(gw*0.92)+'" height="'+Math.max(h,1)+'" fill="'+(it.color||colors[k%colors.length])+'" rx="2"/>';});
      s+='<text x="'+(L+i*bw+bw/2)+'" y="'+(H-B+14)+'" text-anchor="middle">'+esc(it.label)+'</text>';});
    s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(0)+'" y2="'+y(0)+'" stroke="#9aa7b8"/>';
  }
  s+='</svg>'; if(opts.legend) s+='<div class="legend">'+opts.legend.map(function(l,k){return '<span><i style="background:'+colors[k]+'"></i>'+esc(l)+'</span>';}).join("")+'</div>';
  el.innerHTML=s; bindTips(el);
}
function lineChart(el, series, points, opts){
  opts=opts||{}; var W=opts.w||1000,H=opts.h||300,L=56,R=16,Tp=12,B=28;
  if(!series.length){el.innerHTML='<p class="note">No stored history for this commodity.</p>';return;}
  var ts=series.map(function(p){return Date.parse(p[0]);}), vs=series.map(function(p){return p[1];});
  points.forEach(function(p){ts.push(Date.parse(p.d));vs.push(p.v);});
  var t0=Math.min.apply(null,ts),t1=Math.max.apply(null,ts),lo=Math.min.apply(null,vs),hi=Math.max.apply(null,vs),pad=(hi-lo)*0.06||1;lo-=pad;hi+=pad;
  var x=function(t){return L+(t-t0)/((t1-t0)||1)*(W-L-R);}, y=function(v){return Tp+(hi-v)/(hi-lo)*(H-Tp-B);};
  var s='<svg viewBox="0 0 '+W+' '+H+'" width="100%" role="img">';
  niceTicks(lo,hi,5).forEach(function(t){s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(t)+'" y2="'+y(t)+'" stroke="#e8edf3"/><text x="'+(L-6)+'" y="'+(y(t)+4)+'" text-anchor="end">'+f0(t)+'</text>';});
  var d0=new Date(t0); d0=new Date(d0.getFullYear(),d0.getMonth(),1);
  for(var m=new Date(d0);m.getTime()<=t1;m.setMonth(m.getMonth()+1)){var tx=x(m.getTime()); if(tx<L)continue;
    s+='<line x1="'+tx+'" x2="'+tx+'" y1="'+(H-B)+'" y2="'+(H-B+4)+'" stroke="#9aa7b8"/><text x="'+tx+'" y="'+(H-8)+'" text-anchor="middle">'+m.toLocaleString("en-US",{month:"short"})+" "+String(m.getFullYear()).slice(2)+'</text>';}
  s+='<polyline fill="none" stroke="#1f3a5f" stroke-width="1.6" points="'+series.map(function(p){return x(Date.parse(p[0])).toFixed(1)+","+y(p[1]).toFixed(1);}).join(" ")+'"/>';
  points.forEach(function(p){var cx=x(Date.parse(p.d)),cy=y(p.v);
    s+= p.kind==="best" ? '<path data-tip="'+esc(p.tip)+'" d="M'+cx+','+(cy-6)+' l6,10 l-12,0 z" fill="#1a7a1a" opacity=".9"/>'
                        : '<circle data-tip="'+esc(p.tip)+'" cx="'+cx+'" cy="'+cy+'" r="5" fill="#b3261e" opacity=".9"/>';});
  s+='</svg>'; el.innerHTML=s; bindTips(el);
}

// ── renderers ────────────────────────────────────────────────────────
function sum(list,fn){return list.reduce(function(a,r){var v=fn(r);return a+(isNum(v)?v:0);},0);}
function count(list,fn){return list.filter(fn).length;}
function renderKPIs(list){
  var assessed=list.filter(function(r){return T(r).status==="assessed";});
  var k=[
    ["Total contract value", "$"+f0(sum(list,function(r){return r.contract_value_usd;})), "EGP "+f0(sum(list,function(r){return r.contract_value_egp;}))],
    ["Saving vs local — realized", "EGP "+sg0(sum(list,function(r){return r.saving_kind==="Realized"?r.saving_local_egp:null;})), "closed & priced contracts"],
    ["Saving vs local — estimated", "EGP "+sg0(sum(list,function(r){return r.saving_kind==="Estimated"?r.saving_local_egp:null;})), "open contracts, marked to today"],
    ["Timing opportunity (hindsight)", "$"+f0(sum(assessed,function(r){return T(r).opportunity_usd;})), "EGP "+f0(sum(assessed,function(r){return T(r).opportunity_egp;}))+" · separate from savings"],
    ["Contracts analysed", f0(list.length), f0(sum(list,function(r){return r.qty_mt;}))+" MT"],
    ["Favorable timing", f0(count(list,function(r){return T(r).assessment==="Favorable";})), "of "+assessed.length+" assessed"],
    ["Potentially missed savings", f0(count(list,function(r){return T(r).assessment==="Unfavorable";})), "unfavorable timing"],
    ["Need review", f0(count(list,function(r){return r.final_assessment==="Unfavorable"||r.final_assessment==="Insufficient Data"||T(r).assessment==="Insufficient Data";})), "unfavorable or missing data"]
  ];
  $("kpis").innerHTML=k.map(function(c){return '<div class="kpi"><div class="l">'+esc(c[0])+'</div><div class="v">'+esc(c[1])+'</div><div class="s">'+esc(c[2])+'</div></div>';}).join("");
  $("dash-note").textContent = list.length===ROWS.length ? "All contracts." : "Filtered: "+list.length+" of "+ROWS.length+" contracts. Every figure below follows the filters.";
}
function renderDashCharts(list){
  var bases={}; list.forEach(function(r){var b=bases[r.base]||(bases[r.base]={r:0,e:0}); if(isNum(r.saving_local_egp)){if(r.saving_kind==="Realized")b.r+=r.saving_local_egp; else if(r.saving_kind==="Estimated")b.e+=r.saving_local_egp;}});
  bars($("c-savings"), Object.keys(bases).sort().map(function(b){return {label:b, values:[bases[b].r,bases[b].e], tips:[b+" realized: EGP "+sg0(bases[b].r), b+" estimated: EGP "+sg0(bases[b].e)]};}), {legend:["Realized","Estimated"]});
  var colors={"Favorable":"#1a7a1a","Acceptable":"#e0a100","Unfavorable":"#b3261e","Insufficient Data":"#9aa3ae","Not applicable":"#c9ced6","Pending":"#7aa7d6"};
  var vc=["Favorable","Acceptable","Unfavorable","Insufficient Data"].map(function(v){var n=count(list,function(r){return r.final_assessment===v;});return {label:v.replace(" Data",""),value:n,color:colors[v],tip:v+": "+n};});
  bars($("c-verdicts"), vc, {});
  var tc=["Favorable","Acceptable","Unfavorable","Insufficient Data","Not applicable","Pending"].map(function(v){var n=count(list,function(r){return T(r).assessment===v;});return {label:v.replace(" Data","").replace("Not applicable","N/A"),value:n,color:colors[v],tip:v+": "+n};});
  bars($("c-timing"), tc, {});
}
function renderFindings(){
  var s=M.summary, out=[];
  out.push("Saving against local: EGP "+sg0(s.saving_local_realized_egp)+" realized on closed, priced contracts, plus EGP "+sg0(s.saving_local_estimated_egp)+" estimated on open ones (marked to today).");
  if(s.ranking.length){var top=ROWS.filter(function(r){return r.id===s.ranking[0];})[0], t=T(top);
    out.push("Largest hindsight timing opportunity: "+top.contract+" ("+top.id+") — lowest CBOT in its window on "+t.best_date+", worth $"+f0(t.opportunity_usd)+" ("+pct(t.opportunity_pct)+" of CIF). A hindsight benchmark only.");}
  out.push("Timing assessed for "+s.timing_assessed+" of "+s.contracts+" contracts: "+s.timing_favorable+" favorable, "+s.timing_acceptable+" acceptable, "+s.timing_unfavorable+" unfavorable. "+s.timing_insufficient+" have a premium but no pricing date (Insufficient Data), "+s.timing_not_applicable+" are flat-price, "+s.timing_pending+" are open and still to be priced.");
  var tight=count(ROWS,function(r){return String(C(r).verdict||"").indexOf("Needed")===0;}), early=count(ROWS,function(r){return String(C(r).verdict||"").indexOf("Early")===0;});
  out.push(tight+" arrivals came with stock below the "+P.safety_days+"-day safety cover (earlier buying kept the plant running); "+early+" arrived with more than "+P.ample_days+" days of stock.");
  (M.stock||[]).forEach(function(st){if(st.shortage_mt>0) out.push(st.base+": "+f0(st.shortage_mt)+" MT of consumption at "+f0(st.daily_rate)+" MT/day had no recorded cargo to come from — opening stock missing, or the rate is above what was bought.");});
  out.push("Signing date, shipment date and lead time are not recorded for any contract, so the timing of the purchase itself (as opposed to its CBOT pricing) cannot be evaluated from the data.");
  $("findings-list").innerHTML=out.map(function(x){return "<li>"+esc(x)+"</li>";}).join("");
}
function renderCbot(list){
  var bases=Object.keys(M.market).filter(function(b){return M.market[b].length;});
  if(!state.cbot || bases.indexOf(state.cbot)<0) state.cbot = bases.indexOf("CORN")>=0?"CORN":bases[0];
  $("cbot-tabs").innerHTML=bases.map(function(b){return '<button class="'+(b===state.cbot?"on":"")+'" data-b="'+b+'">'+b+'</button>';}).join("");
  $("cbot-tabs").querySelectorAll("button").forEach(function(btn){btn.onclick=function(){state.cbot=btn.getAttribute("data-b");renderCbot(current());};});
  var pts=[], lines=[];
  list.filter(function(r){return r.base===state.cbot && T(r).status==="assessed";}).forEach(function(r){
    (T(r).events||[]).forEach(function(e){ if(e.status!=="assessed")return;
      pts.push({d:e.history_date,v:e.history_on_day,kind:"priced",tip:esc(r.contract)+" ("+r.id+")<br>CBOT fixed "+e.date+": history "+f2(e.history_on_day)+"<br>"+f0(e.qty_mt)+" MT"});
      pts.push({d:e.best_date,v:e.best_history,kind:"best",tip:esc(r.contract)+"<br>hindsight best "+e.best_date+": "+f2(e.best_history)+"<br>opportunity "+f2(e.opportunity_cbot)+" per unit"});
      lines.push({r:r,e:e});});});
  lineChart($("c-cbot"), M.market[state.cbot]||[], pts, {});
  // timeline
  var el=$("c-timeline"); if(!lines.length){el.innerHTML='<p class="note">No assessed fixings for '+esc(state.cbot)+' in this selection.</p>';return;}
  lines.sort(function(a,b){return a.e.date<b.e.date?-1:1;});
  var W=1000,rowH=18,L=190,R=16,H=lines.length*rowH+30;
  var t0=Math.min.apply(null,lines.map(function(l){return Date.parse(l.e.window_start);})), t1=Math.max.apply(null,lines.map(function(l){return Date.parse(l.e.window_end);}));
  var x=function(d){return L+(Date.parse(d)-t0)/((t1-t0)||1)*(W-L-R);};
  var s='<svg viewBox="0 0 '+W+' '+H+'" width="100%">';
  lines.forEach(function(l,i){var y=8+i*rowH, e=l.e;
    s+='<text x="'+(L-6)+'" y="'+(y+11)+'" text-anchor="end">'+esc((l.r.contract.length>26?l.r.contract.slice(0,25)+"…":l.r.contract))+'</text>';
    s+='<rect x="'+x(e.window_start)+'" y="'+(y+4)+'" width="'+Math.max(x(e.window_end)-x(e.window_start),2)+'" height="8" fill="#dbe6f3" rx="3"/>';
    s+='<circle data-tip="'+esc(l.r.contract)+'<br>fixed '+e.date+'" cx="'+x(e.date)+'" cy="'+(y+8)+'" r="5" fill="#b3261e"/>';
    s+='<path data-tip="'+esc(l.r.contract)+'<br>best '+e.best_date+' (hindsight)" d="M'+x(e.best_date)+','+(y+2)+' l6,11 l-12,0 z" fill="#1a7a1a"/>';});
  [[t0,"start"],[(t0+t1)/2,"middle"],[t1,"end"]].forEach(function(p){var d=new Date(p[0]).toISOString().slice(0,10);s+='<text x="'+x(d)+'" y="'+(H-6)+'" text-anchor="'+p[1]+'">'+d+'</text>';});
  s+='</svg>'; el.innerHTML=s; bindTips(el);
}
function renderMissed(list){
  var ranked=list.filter(function(r){return isNum(T(r).opportunity_usd);}).sort(function(a,b){return T(b).opportunity_usd-T(a).opportunity_usd;}).slice(0,15);
  bars($("c-missed"), ranked.map(function(r){var t=T(r);return {label:r.contract, value:t.opportunity_usd,
      color:t.assessment==="Unfavorable"?"#b3261e":(t.assessment==="Acceptable"?"#e0a100":"#1a7a1a"),
      tip:esc(r.contract)+" ("+r.id+")<br>$"+f0(t.opportunity_usd)+" · "+pct(t.opportunity_pct)+" of CIF<br>best "+t.best_date+" · "+t.assessment};}),
    {horizontal:true, h:Math.max(140, ranked.length*22+30)});
  var tight=list.filter(function(r){return String(C(r).verdict||"").indexOf("Needed")===0;});
  $("t-tight").innerHTML='<thead><tr><th>ID</th><th>Contract</th><th>Arrival</th><th class="n">Cover before, days</th></tr></thead><tbody>'+
    tight.map(function(r){return '<tr><td>'+esc(r.id)+'</td><td><a href="#k-'+esc(r.id)+'">'+esc(r.contract)+'</a></td><td>'+esc(r.delivery_date)+'</td><td class="n">'+f2(C(r).cover_days)+'</td></tr>';}).join("")+'</tbody>';
}
var COLS=[
  ["id","ID",function(r){return r.id;}],["contract","Contract",function(r){return r.contract;}],["base","Base",function(r){return r.base;}],
  ["supplier","Supplier",function(r){return r.supplier;}],["qty","Qty MT",function(r){return r.qty_mt;},1],
  ["arrival","Arrival",function(r){return r.delivery_date;}],["cif","CIF $/MT",function(r){return r.cif_usd_mt;},2],
  ["landed","Landed EGP/MT",function(r){return r.landed_cost_egp_mt;},1],["local","Local EGP/MT",function(r){return r.local_egp_mt;},1],
  ["savmt","Saving EGP/MT",function(r){return r.saving_local_egp_mt;},1],["sav","Saving EGP",function(r){return r.saving_local_egp;},1],
  ["lr","Local result",function(r){return r.local_assessment;}],["opp","Timing opp. $",function(r){return T(r).opportunity_usd;},1],
  ["oppp","Opp. % CIF",function(r){return T(r).opportunity_pct;},3],["ta","Timing",function(r){return T(r).assessment;}],
  ["cover","Cover at arrival, d",function(r){return C(r).cover_days;},2],["fa","Final",function(r){return r.final_assessment;}]];
function renderTable(list){
  var col=COLS.filter(function(c){return c[0]===state.sort;})[0], get=col[2];
  var sorted=list.slice().sort(function(a,b){var x=get(a),y=get(b); if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
    return (x<y?-1:x>y?1:0)*state.dir;});
  var head='<thead><tr>'+COLS.map(function(c){var k=c[0]===state.sort?(state.dir>0?"sorted-asc":"sorted-desc"):"";
    return '<th data-k="'+c[0]+'" class="'+(c[3]?"n ":"")+k+'">'+esc(c[1])+'</th>';}).join("")+'</tr></thead>';
  var body='<tbody>'+sorted.map(function(r){return '<tr>'+COLS.map(function(c){var v=c[2](r);
    if(c[0]==="contract") return '<td><a href="#k-'+esc(r.id)+'">'+esc(v)+'</a></td>';
    if(c[0]==="lr"||c[0]==="ta"||c[0]==="fa") return '<td>'+badge(v)+'</td>';
    if(c[3]===1) return '<td class="n '+((c[0]==="sav"||c[0]==="savmt")?cls(v):"")+'">'+f0(v)+'</td>';
    if(c[3]===2) return '<td class="n">'+f2(v)+'</td>';
    if(c[3]===3) return '<td class="n">'+pct(v,2)+'</td>';
    return '<td>'+esc(v)+'</td>';}).join("")+'</tr>';}).join("")+'</tbody>';
  $("t-main").innerHTML=head+body;
  $("t-main").querySelectorAll("th").forEach(function(th){th.onclick=function(){var k=th.getAttribute("data-k");
    state.dir = (state.sort===k)? -state.dir : (["contract","id","base","supplier","arrival","lr","ta","fa"].indexOf(k)>=0?1:-1); state.sort=k; renderTable(current());};});
}
function renderStock(){
  $("t-stock").innerHTML='<thead><tr><th>Commodity</th><th class="n">Daily consumption MT</th><th class="n">Stock now MT</th><th class="n">Cover, days</th><th class="n">Inbound MT</th><th class="n">Cover incl. inbound</th><th class="n">Projected shortage MT</th></tr></thead><tbody>'+
   (M.stock||[]).map(function(s){return '<tr><td>'+esc(s.base)+'</td><td class="n">'+f0(s.daily_rate)+'</td><td class="n">'+f0(s.stock_mt)+'</td><td class="n">'+f2(s.cover_days)+'</td><td class="n">'+f0(s.inbound_mt)+'</td><td class="n">'+f2(s.cover_with_inbound_days)+'</td><td class="n '+(s.shortage_mt>0?"neg":"")+'">'+f0(s.shortage_mt)+'</td></tr>';}).join("")+'</tbody>';
}
function kv(pairs){return '<div class="kv">'+pairs.map(function(p){return '<div><span>'+esc(p[0])+'</span><span>'+p[1]+'</span></div>';}).join("")+'</div>';}
function miniWindow(r){
  var t=T(r), series=M.market[r.base]||[]; if(t.status!=="assessed"||!series.length) return "";
  var e=(t.events||[]).filter(function(x){return x.status==="assessed";}); if(!e.length) return "";
  var a=e.reduce(function(m,x){return x.window_start<m?x.window_start:m;},e[0].window_start), b=e.reduce(function(m,x){return x.window_end>m?x.window_end:m;},e[0].window_end);
  var part=series.filter(function(p){return p[0]>=a && p[0]<=b;}); if(part.length<2) return "";
  var pts=[]; e.forEach(function(x){pts.push({d:x.history_date,v:x.history_on_day,kind:"priced",tip:"fixed "+x.date+": "+f2(x.history_on_day)});pts.push({d:x.best_date,v:x.best_history,kind:"best",tip:"best "+x.best_date+": "+f2(x.best_history)});});
  var holder=document.createElement("div"); lineChart(holder, part, pts, {w:700,h:180}); return '<div class="chart" style="max-width:720px">'+holder.innerHTML+'</div>';
}
function explain(r){
  var t=T(r), c=C(r), out=[];
  if(isNum(r.saving_local_egp_mt)) out.push((r.saving_local_egp_mt>=0?"Cheaper":"Dearer")+" than buying locally by "+f0(Math.abs(r.saving_local_egp_mt))+" EGP/MT on the arrival day ("+r.saving_kind.toLowerCase()+"), against the "+esc(r.local_key||"local")+" price of "+esc(r.local_date)+".");
  else out.push("No local price on or before the arrival day, so no comparison with local.");
  if(r.fx_source) out.push("Cost converted at the "+esc(r.fx_source)+" FX ("+f2(r.fx)+").");
  if(t.status==="assessed"){
    out.push("CBOT fixed at "+(t.range_position*100).toFixed(0)+"% of its "+esc(t.window)+" range (0% = the low). The hindsight best day was "+t.best_date+", worth "+f2(t.opportunity_usd_mt)+" USD/MT, $"+f0(t.opportunity_usd)+" in all.");
    out.push("At the time (prices on or before the pricing day only), the fixing was "+(t.vs_trailing_avg<=0?"below":"above")+" its 20-day average by "+f2(Math.abs(t.vs_trailing_avg))+" — "+(t.vs_trailing_avg<=0?"a reasonable call with what was known then.":"higher than the recent average a buyer could see."));
    if(t.confidence && t.confidence.indexOf("Low")===0) out.push("Low confidence: the stored CBOT on the pricing day is a one-day outlier — verify that day's price.");
    out.push("Moving the pricing day does not move the shipment, so the alternative carries no stock risk of its own (assuming the contract allowed pricing anywhere in the window).");
  } else out.push("Timing: "+esc(t.reason||t.assessment)+".");
  if(isNum(c.cover_days)) out.push("Stock at arrival: "+esc(c.explain)+".");
  return '<ul class="why">'+out.map(function(x){return "<li>"+x+"</li>";}).join("")+'</ul>';
}
function card(r){
  var t=T(r), c=C(r);
  var flags="";
  if(t.assessment==="Unfavorable") flags+='<div class="flag bad">Purchased CBOT above a feasible alternative in its window: $'+f0(t.opportunity_usd)+' ('+pct(t.opportunity_pct)+' of CIF) on the hindsight best day '+t.best_date+'.</div>';
  if(String(c.verdict||"").indexOf("Needed")===0) flags+='<div class="flag good">Arrival justified by stock: '+esc(c.explain)+'.</div>';
  if(t.assessment==="Insufficient Data") flags+='<div class="flag">Timing cannot be assessed: '+esc(t.reason)+'. Enter it in Contracts to include this contract.</div>';
  var landed = (isNum(r.cif_usd_mt)&&isNum(r.fx)) ? '<div class="formula">'+f2(r.cif_usd_mt)+' $/MT × '+f2(r.fx)+' + '+f2(r.discharge_egp_mt)+' intake + '+f2(r.clearance_egp_mt)+' clearance + '+f2(r.freight_egp_mt)+' freight = <b>'+f2(r.landed_cost_egp_mt)+' EGP/MT</b></div>' : "";
  var timing = t.status==="assessed" ? kv([
      ["Priced by",esc(t.source)],["Pricing day(s)",esc((t.events||[]).map(function(e){return e.date;}).join(", "))],
      ["Priced CBOT",f2(t.actual_cbot)],["Window",esc(t.window)],["Hindsight best day",esc(t.best_date)],
      ["Best CBOT equivalent",f2(t.best_cbot_equivalent)],["Opportunity USD/MT",f2(t.opportunity_usd_mt)],
      ["Opportunity",'$'+f0(t.opportunity_usd)+' · EGP '+f0(t.opportunity_egp)],["Opportunity % of CIF",pct(t.opportunity_pct,2)],
      ["Position in window",(t.range_position*100).toFixed(0)+"%"],["vs 20-day avg at the time",f2(t.vs_trailing_avg)],
      ["Confidence",esc(t.confidence)]])+'<div class="formula">Opportunity = ('+f2(t.actual_cbot)+' − '+f2(t.best_cbot_equivalent)+') × '+t.factor+' × '+f0(t.qty_priced)+' MT = $'+f0(t.opportunity_usd)+'</div>'+miniWindow(r)
    : (t.forward ? '<p class="note">Forward-looking only (not a forecast): CBOT '+f2(t.forward.current)+' on '+esc(t.forward.current_date)+' sits at '+(t.forward.range_position*100).toFixed(0)+'% of its last '+t.forward.obs+' trading days ('+f2(t.forward.low)+'–'+f2(t.forward.high)+').</p>' : '<p class="note">'+esc(t.reason||"")+'</p>');
  return '<details class="contract" id="k-'+esc(r.id)+'"><summary><b>'+esc(r.contract)+'</b><span class="note">'+esc(r.id)+' · '+esc(r.commodity)+' · '+esc(r.supplier)+' · '+f0(r.qty_mt)+' MT · arrived '+esc(r.delivery_date)+'</span>'+
    '<span style="flex:1"></span>Local '+badge(r.local_assessment)+' Timing '+badge(t.assessment)+' Final '+badge(r.final_assessment)+'</summary><div class="body">'+flags+
    '<h3>Contract overview</h3>'+kv([["Supplier",esc(r.supplier)],["Commodity / origin",esc(r.commodity+" / "+r.origin)],["Status",esc(r.status+" · "+r.pricing_status)],
      ["Quantity",f0(r.qty_mt)+" MT"],["Signing date","not recorded"],["Pricing date",esc(r.pricing_date||"—")],["Form 4 date",esc(r.form4_date||"—")],
      ["Shipment date","not recorded"],["Arrival",esc(r.delivery_date)],["CIF",f2(r.cif_usd_mt)+" $/MT"],["FX ("+esc(r.fx_source||"—")+")",f2(r.fx)],
      ["Contract value",'$'+f0(r.contract_value_usd)+' · EGP '+f0(r.contract_value_egp)]])+
    '<h3>Against the local market</h3>'+landed+kv([["Local (delivered)",f2(r.local_egp_mt)+" · "+esc(r.local_key)+" "+esc(r.local_date)],
      ["Saving per MT",'<span class="'+cls(r.saving_local_egp_mt)+'">'+sg0(r.saving_local_egp_mt)+'</span>'],["Saving",'<span class="'+cls(r.saving_local_egp)+'">EGP '+sg0(r.saving_local_egp)+'</span>'],
      ["Kind",esc(r.saving_kind)],["Local result",badge(r.local_assessment)]])+
    '<h3>Consumption and stock</h3>'+kv([["Daily consumption",f0(r.daily_consumption_mt)+" MT"],["This cargo covers",f2(c.cargo_days)+" days"],
      ["Stock before arrival",f0(r.stock_before_arrival_mt)+" MT"],["Cover before arrival",f2(c.cover_days)+" days"],["Arrival verdict",esc(c.verdict||"—")],
      ["Max delay without shortage",isNum(c.max_safe_delay_days)?f0(c.max_safe_delay_days)+" days":"—"]])+
    '<h3>CBOT and FX</h3>'+kv([["Premium",f2(r.premium)],["Futures month",esc(r.futures_month||"—")],["CBOT factor",esc(r.cbot_factor||"—")],
      ["History on pricing day",f2(r.cbot_at_pricing)],["History at arrival",f2(r.cbot_at_delivery)],["Latest ("+esc(r.cbot_latest_date)+")",f2(r.cbot_latest)]])+
    '<h3>Purchasing timing — actual vs best feasible alternative</h3>'+timing+
    '<h3>Why this result</h3>'+explain(r)+
    '<h3>Final assessment</h3><p>'+badge(r.final_assessment)+' <span class="note">local '+esc(r.local_assessment)+' + timing '+esc(t.assessment)+' (Favorable +1, Acceptable 0, Unfavorable −1).</span></p>'+
    (r.missing&&r.missing.length?'<p class="note">Missing in the data: '+esc(r.missing.join(", "))+'.</p>':'')+
    '</div></details>';
}
function renderCards(list){
  var open={}; document.querySelectorAll("details.contract[open]").forEach(function(d){open[d.id]=1;});
  $("cards").innerHTML = list.length ? list.map(card).join("") : '<p class="note">No contract matches the filters.</p>';
  Object.keys(open).forEach(function(id){var d=document.getElementById(id); if(d) d.open=true;});
  bindTips($("cards"));
}
function renderMethod(){
  var p=P, rows=[
   ["Contract value","Qty × CIF (USD); × FX for EGP."],
   ["FX","The contract's cost FX: Form 4 FX once entered (every commodity except SBM), else delivery FX, else today's market FX."],
   ["Landed cost","CIF × FX + intake/discharge + clearance + freight."],
   ["Local price","Logged on or before the arrival day, matched to the cargo's origin, plus its transport (delivered)."],
   ["Saving vs local","Local − landed, per MT and × qty. Realized = closed & priced (Savings Tracker); Estimated = open, marked to today."],
   ["Priced CBOT","CIF ÷ factor − premium, or the CBOT stored on each pricing lot. Factors: corn 0.3937, soybean/wheat 0.36745, SBM 1.1023."],
   ["Window",p.window_before_days+" days before to "+p.window_after_days+" days after each pricing day, never past the last stored day."],
   ["Best CBOT equivalent","Priced CBOT + (history on best day − history on pricing day): only the history's moves are used (front-month series vs the contract's own month)."],
   ["Timing opportunity","(Priced CBOT − best equivalent) × factor × tonnes priced = (actual comparable cost − best feasible alternative) × quantity, premium, fees and FX held as contracted. × FX for EGP; ÷ CIF for %."],
   ["Timing assessment","Favorable if ≤ "+p.small_opportunity_pct+"% of CIF or in the lowest third of the window; middle third Acceptable; top third Unfavorable."],
   ["Local result","Favorable ≥ +"+p.local_band_pct+"% of local; Unfavorable ≤ −"+p.local_band_pct+"%; else Acceptable."],
   ["Final assessment","Favorable +1, Acceptable 0, Unfavorable −1, local + timing: ≥ +1 Favorable, 0 Acceptable, ≤ −1 Unfavorable; without timing the local result stands; without local, Insufficient Data."],
   ["Stock","The app's FIFO walk at the configured daily rate from each delivery; cover = stock the day before arrival ÷ daily rate."],
   ["Hindsight vs at the time","Best days use later prices (benchmark only). The 20-day view uses only the "+p.trailing_obs+" trading days on or before the pricing day."],
   ["Outliers","Days ≥ "+p.spike_pct+"% away from both neighbours that come back are treated as stray prints: never a best/worst day; a pricing day that is one lowers confidence."],
   ["Limits","A futures roll inside a window can shift a result by the calendar spread. Signing date, shipment date and lead time are not in the data. Nothing is estimated: missing inputs are listed and marked Insufficient Data."]];
  var gaps={}; (M.gaps||[]).forEach(function(g){(gaps[g.missing]=gaps[g.missing]||[]).push(g.id);});
  $("method-body").innerHTML='<table><tbody>'+rows.map(function(r){return '<tr><th style="width:200px;cursor:default">'+esc(r[0])+'</th><td>'+esc(r[1])+'</td></tr>';}).join("")+'</tbody></table>'+
    '<h3>Missing information</h3>'+(Object.keys(gaps).length?'<ul class="why">'+Object.keys(gaps).sort().map(function(k){return '<li><b>'+esc(k)+'</b> — '+gaps[k].length+' contract(s): '+esc(gaps[k].join(", "))+'</li>';}).join("")+'</ul>':'<p class="note">None beyond the fields the app does not record.</p>')+
    '<p class="note">Report version '+esc(M.version)+' · built from the app data of '+esc(M.as_of)+'.</p>';
}
function renderAll(){var list=current(); renderKPIs(list); renderDashCharts(list); renderCbot(list); renderMissed(list); renderTable(list); renderCards(list);}
renderFindings(); renderStock(); renderMethod(); renderAll();
})();
</script>
</body>
</html>
"""
