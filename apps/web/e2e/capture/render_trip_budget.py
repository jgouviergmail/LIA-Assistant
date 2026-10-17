"""Render a fictional, interactive trip-budget skill for the public UI captures.

This fixture follows the skill frame contract. It runs locally during capture;
it is not installed as a system skill and never contacts a booking provider.
"""

import json
import sys

HTML = r"""<!doctype html>
<html lang="en" data-theme="light">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}body{margin:0;padding:22px;background:#f8fbfc;color:#183342;font:14px system-ui,sans-serif}
header{display:flex;align-items:start;justify-content:space-between;gap:16px;margin-bottom:20px}
h1{font-size:24px;line-height:1.15;margin:4px 0 8px;letter-spacing:-.7px}p{margin:0;color:#536d79;line-height:1.5}
.tag{display:inline-block;padding:6px 10px;border-radius:8px;background:#dcf1ed;color:#176657;font-size:12px;font-weight:650}
.layout{display:grid;grid-template-columns:1.1fr 1fr;gap:22px;align-items:start}
.overview{display:flex;align-items:center;gap:14px;background:white;padding:14px;border:1px solid #dce8ed;border-radius:14px}
.ring{width:174px;height:174px;flex:none;position:relative}.ring svg{width:100%;height:100%;transform:rotate(-90deg)}
.total{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.total strong{font-size:30px;letter-spacing:-1px}.total span{color:#617784;font-size:11px;margin-top:2px}
.margin{font-size:25px;font-weight:750;color:#176657}.margin.over{color:#b13f32}
.detail{margin-top:15px}.row{display:grid;grid-template-columns:10px 1fr auto;align-items:center;gap:9px;margin:10px 0;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%}.row b{font-variant-numeric:tabular-nums}.bar{height:4px;background:#e7eef1;border-radius:3px;margin:-4px 0 12px 19px;overflow:hidden}.bar i{display:block;height:100%;border-radius:3px}
fieldset{border:0;margin:0;padding:0}legend{font-size:15px;font-weight:700;margin-bottom:14px}
label{display:flex;justify-content:space-between;align-items:center;font-size:13px;font-weight:600}
output{font-size:14px;color:#126f94;font-variant-numeric:tabular-nums}
input[type=range]{width:100%;accent-color:#147f9c;margin:9px 0 18px;cursor:pointer}
input:focus-visible{outline:3px solid #83c6e1;outline-offset:3px}
.plan{border-top:1px solid #dce8ed;padding-top:13px;margin-top:2px;display:grid;gap:10px}
.day{display:grid;grid-template-columns:36px 1fr;gap:9px;align-items:center;font-size:12px}
.num{display:grid;place-items:center;width:32px;height:32px;background:#e4f1f7;border-radius:9px;color:#176487;font-weight:750}
.day b{display:block;margin-bottom:2px;font-size:13px}.day small{color:#617784}
footer{border-top:1px solid #dce8ed;margin-top:18px;padding-top:11px;display:flex;justify-content:space-between;gap:12px;font-size:11px;color:#617784}
@media(max-width:560px){body{padding:16px}.layout{grid-template-columns:1fr}.overview{justify-content:center}.ring{width:154px;height:154px}footer{display:block}}
</style></head><body>
<header><div><h1>A weekend in Lyon</h1><p>Shape the trip. See what changes.</p></div><span class="tag">Budget studio</span></header>
<main class="layout">
<section aria-label="Trip budget breakdown">
<div class="overview">
<div class="ring"><svg viewBox="0 0 180 180" role="img" aria-label="Trip spending by category" id="chart"></svg>
<div class="total"><strong id="total">€584</strong><span>estimated trip</span></div></div>
<div><p id="margin-label">Room in your budget</p><div id="margin" class="margin">€176</div><p id="per-person">€292 per person</p><p id="stay">2 travellers · 2 nights</p></div>
</div><div id="breakdown" class="detail" aria-live="polite"></div>
</section>
<section aria-label="Adjust your trip"><fieldset><legend>Make it your weekend</legend>
<label for="travellers">Travellers <output id="travellers-value">2</output></label>
<input id="travellers" type="range" min="1" max="6" value="2">
<label for="nights">Nights away <output id="nights-value">2</output></label>
<input id="nights" type="range" min="1" max="5" value="2">
<label for="budget">Total budget <output id="budget-value">€760</output></label>
<input id="budget" type="range" min="400" max="1800" step="20" value="760">
</fieldset><div class="plan">
<div class="day"><span class="num">01</span><div><b>Old Lyon &amp; the riverside</b><small>Train arrival, neighbourhood walk, dinner</small></div></div>
<div class="day"><span class="num">02</span><div><b>Food hall &amp; city views</b><small>Local transport, market lunch, museum</small></div></div>
</div></section></main>
<footer><span>Example estimates · no booking prices checked</span><span>Adjustments calculate here instantly</span></footer>
<script>
(function(){
var euro=new Intl.NumberFormat('en-GB',{style:'currency',currency:'EUR',maximumFractionDigits:0});
var ids=['travellers','nights','budget'];
function money(n){return euro.format(n)}
function update(){
var people=Number(document.getElementById('travellers').value);
var nights=Number(document.getElementById('nights').value);
var budget=Number(document.getElementById('budget').value);
var costs=[['Train travel',48*people,'#147f9c'],['Accommodation',110*nights,'#3455b0'],['Food & coffee',26*people*(nights+1),'#37a58d'],['Museums & activities',32*people,'#d6943c'],['Getting around',8*people*(nights+1),'#9a6cb6']];
var total=costs.reduce(function(sum,item){return sum+item[1]},0);
var left=budget-total,offset=0,circumference=2*Math.PI*73;
document.getElementById('chart').innerHTML=costs.map(function(item){
var length=item[1]/total*circumference;
var arc='<circle cx="90" cy="90" r="73" fill="none" stroke="'+item[2]+'" stroke-width="15" stroke-dasharray="'+(length-2)+' '+(circumference-length+2)+'" stroke-dashoffset="'+(-offset)+'"/>';
offset+=length;return arc}).join('');
document.getElementById('breakdown').innerHTML=costs.map(function(item){return '<div class="row"><span class="dot" style="background:'+item[2]+'"></span><span>'+item[0]+'</span><b>'+money(item[1])+'</b></div><div class="bar"><i style="width:'+(item[1]/total*100)+'%;background:'+item[2]+'"></i></div>'}).join('');
document.getElementById('total').textContent=money(total);
document.getElementById('margin-label').textContent=left>=0?'Room in your budget':'Above your budget';
document.getElementById('margin').textContent=money(Math.abs(left));
document.getElementById('margin').className=left>=0?'margin':'margin over';
document.getElementById('per-person').textContent=money(Math.round(total/people))+' per person';
document.getElementById('stay').textContent=people+' travellers · '+nights+' nights';
document.getElementById('travellers-value').textContent=people;
document.getElementById('nights-value').textContent=nights;
document.getElementById('budget-value').textContent=money(budget);
}
ids.forEach(function(id){document.getElementById(id).addEventListener('input',update)});
update();
})();
</script></body></html>"""


def main() -> None:
    """Emit the same frame envelope a scripted interactive skill returns."""
    json.load(sys.stdin)
    json.dump(
        {
            "frame": {
                "title": "Weekend Budget Studio",
                "html": HTML,
                "aspect_ratio": 1.65,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
