# tt_newui_html — 운영자가 준 새 디자인(대시보드 + 상세 검수, 2026-11-24 지시문 「폰트 재현 검수 시스템 — UI/UX 전면 개편」)으로
# 영상 한 편을 보이는 화면. 지금은 조니 뎁 영상(페이퍼로지 한 집안으로 다시 맞춘 것)만 넣는다(운영자 2026-11-24 「이번에 만든 것만 … 이것만 넣어봐」).
#   python -I -X utf8 tt_newui_html.py <영상 폴더(그림/·값/ 있는 곳)> <영상 id> "<영상 제목>"  → <폴더>/새화면.html
# 값은 모두 파일에서 읽는다: 값/<id>_검수.json(독립 검수) · 값/페이퍼로지_맞춤.json(맞춘 효과 값) · 값/화면용.json(글자 카드·화소 수) · 값/눈확인.json
# 잰 적 없는 값은 「안 잼」으로 적는다(지어 채우지 않음). 「일치」는 모든 값이 원본과 같을 때만.
import json, os, sys, html, time

def rj(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

E = lambda s: html.escape(str(s))

CSS = r"""
/* ── variables ── */
:root{--bg:#F5F7FC;--card:#FFFFFF;--sub:#F8FAFF;--tx:#17213A;--tx2:#64718B;--tx3:#9AA5B7;--blue:#246BFD;--blueh:#1457E5;--bluel:#EAF1FF;
--violet:#6548ED;--ok:#16A34A;--warn:#F59E0B;--err:#EF4444;--line:#E3E9F3;--line2:#D5E1FA;--in:#DCE4F1;
--s4:4px;--s8:8px;--s12:12px;--s16:16px;--s20:20px;--s24:24px;--s32:32px;--r:12px}
/* ── reset / typography ── */
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--bg);color:var(--tx);font:400 14px/1.5 Pretendard,"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Malgun Gothic",sans-serif}
h1{font-size:22px;font-weight:700;margin:0}h2{font-size:20px;font-weight:700;margin:0}h3{font-size:16px;font-weight:700;margin:0}
.small{font-size:12px;color:var(--tx2)}.muted{color:var(--tx3)}
/* ── layout ── */
.wrap{padding:var(--s16) var(--s24) var(--s32);max-width:1536px;margin:0 auto}
.sec{margin-top:var(--s16)}
.secttl{display:inline-flex;align-items:center;gap:8px;background:var(--blue);color:#fff;font-weight:700;font-size:16px;padding:6px 16px;border-radius:999px;margin:var(--s8) 0}
/* ── components ── */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:0 2px 8px rgba(31,51,90,.04)}
.pad{padding:var(--s16) var(--s20)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:40px;padding:0 14px;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--tx);font:600 14px inherit;font-family:inherit;cursor:pointer}
.btn:hover{border-color:var(--line2);background:var(--sub)}.btn:active{transform:translateY(1px)}.btn:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.btn:disabled{pointer-events:auto;color:var(--tx3);background:#fff;cursor:not-allowed;border-color:var(--line)}
.btn.pri{background:var(--blue);color:#fff;border-color:var(--blue)}.btn.pri:hover{background:var(--blueh);border-color:var(--blueh)}
.btn.sm{height:34px;padding:0 12px;font-size:13px}
.btn.on{background:var(--bluel);border-color:var(--line2);color:var(--blue)}
.inp{background:#fff;border:1px solid var(--in);border-radius:10px;height:40px;padding:0 12px;font-size:14px;font-family:inherit;color:var(--tx)}
.badge{display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.b-ok{background:#E8F7EE;color:var(--ok)}.b-warn{background:#FEF3DC;color:#B45309}.b-err{background:#FDECEC;color:var(--err)}.b-wait{background:#EEF1F6;color:var(--tx2)}
.b-blue{background:var(--blue);color:#fff}.b-bl{background:var(--bluel);color:var(--blue)}
table.t{width:100%;border-collapse:collapse;font-size:13px}table.t th,table.t td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
table.t th{color:var(--tx2);font-weight:600;background:var(--sub)}
.sw{display:inline-block;width:12px;height:12px;border-radius:50%;border:1px solid rgba(0,0,0,.15);vertical-align:-1px;margin-right:4px}
[data-tip]{position:relative}
[data-tip]:hover::after,[data-tip]:focus-visible::after{content:attr(data-tip);position:absolute;left:50%;top:calc(100% + 8px);transform:translateX(-50%);z-index:50;
 width:max-content;max-width:min(280px,80vw);white-space:normal;text-align:left;background:#17213A;color:#fff;font-size:12px;font-weight:500;line-height:1.45;padding:7px 10px;border-radius:8px;box-shadow:0 6px 18px rgba(23,33,58,.22);pointer-events:none}
[data-tip]:hover::before,[data-tip]:focus-visible::before{content:"";position:absolute;left:50%;top:calc(100% + 3px);transform:translateX(-50%);border:5px solid transparent;border-bottom-color:#17213A;z-index:50;pointer-events:none}
/* ── dashboard ── */
.top{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s12)}.logo{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--blue),var(--violet));color:#fff;font-weight:800;display:grid;place-items:center;font-size:18px}
.top .sp{flex:1}
.stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:var(--s12);margin-top:var(--s16)}
.stat{display:flex;align-items:center;gap:var(--s12);padding:var(--s16) var(--s20)}
.stat .ic{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:18px}
.stat .n{font-size:28px;font-weight:700;line-height:1.1}.stat .l{font-size:13px;color:var(--tx2)}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s8);margin-top:var(--s16)}
.chip{height:36px;padding:0 14px;border-radius:999px;border:1px solid var(--line);background:#fff;font:600 13px inherit;font-family:inherit;color:var(--tx);cursor:pointer}
.chip.on{background:var(--blue);border-color:var(--blue);color:#fff}
.vsep{width:1px;height:24px;background:var(--line);margin:0 4px}
.tog{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:13px;cursor:pointer}
.tog input{appearance:none;width:36px;height:20px;border-radius:999px;background:var(--line);position:relative;cursor:pointer;transition:.15s}
.tog input::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.15s}
.tog input:checked{background:var(--blue)}.tog input:checked::after{left:18px}
.search{margin-left:auto;width:280px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--s12);margin-top:var(--s12)}
.vcard{padding:var(--s12);cursor:pointer;transition:.12s}.vcard:hover{border-color:var(--line2)}.vcard.sel{border:2px solid var(--blue)}
.vcard .vt{font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:var(--s8)}
.vcard .th{aspect-ratio:16/10;border-radius:8px;overflow:hidden;background:var(--sub);display:grid;place-items:center}
.vcard .th img{width:100%;height:100%;object-fit:cover;object-position:top}
.vcard .ft{display:flex;align-items:center;gap:6px;margin-top:var(--s8)}
.empty{padding:var(--s24);text-align:center;color:var(--tx2)}
/* ── detail ── */
.dbar{display:flex;align-items:center;gap:var(--s12);padding:var(--s12) var(--s16)}
.dbar .vt{font-size:17px;font-weight:700}.dbar .mini{width:46px;height:30px;border-radius:6px;object-fit:cover;object-position:top;border:1px solid var(--line)}
.tools{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s8);padding:var(--s12) var(--s16);border-top:1px solid var(--line)}
.tools input[type=range]{width:140px;accent-color:var(--blue)}
.dmain{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:var(--s12);padding:0 var(--s16) var(--s16)}
.cmp{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--s12);align-content:start}
.cmp.single,.cmp.stack{grid-template-columns:minmax(0,1fr)}
.pane{position:relative;border-radius:10px;overflow:hidden;background:#0d1220;border:1px solid var(--line);height:560px;cursor:grab}
.pane.drag{cursor:grabbing}
.pane .lab{position:absolute;left:8px;top:8px;z-index:3;background:rgba(255,255,255,.92);color:var(--tx);font-weight:700;font-size:13px;padding:3px 10px;border-radius:6px}
.pane .dim{position:absolute;right:8px;bottom:8px;z-index:3;background:rgba(0,0,0,.65);color:#fff;font-size:12px;font-weight:600;padding:3px 8px;border-radius:6px}
.pane .stage{position:absolute;left:0;top:0;transform-origin:0 0}
.pane .stage img{position:absolute;left:0;top:0;display:block;image-rendering:auto}
.pane .stage img.pix{image-rendering:pixelated}
.pane .gridov{position:absolute;inset:0;z-index:2;pointer-events:none;display:none;
 background-image:linear-gradient(rgba(36,107,253,.35) 1px,transparent 1px),linear-gradient(90deg,rgba(36,107,253,.35) 1px,transparent 1px);background-size:var(--gs,40px) var(--gs,40px)}
.showgrid .pane .gridov{display:block}
.pane .err{position:absolute;inset:0;display:none;place-items:center;color:#fff}
.fpanel{grid-column:1/-1}.finfo{display:flex;flex-wrap:wrap;gap:6px 24px;margin:8px 0 10px;font-size:13px;color:var(--tx2)}.finfo b{color:var(--tx)}.ftab td,.ftab th{white-space:nowrap}.ftab td:first-child{font-weight:600}
.verdict{background:#FFF5F5;border-color:#F8D4D4;text-align:center}
.verdict .big{font-size:36px;font-weight:700;color:var(--err);line-height:1.1;margin:var(--s8) 0}
.verdict .why{text-align:left;font-size:13px;color:#B42318;margin-top:var(--s12)}
.verdict .why li{margin:2px 0}
/* ── analysis ── */
.tabs{display:flex;gap:var(--s4);overflow-x:auto;border-bottom:1px solid var(--line);padding:0 var(--s16)}
.tab{flex:none;white-space:nowrap;background:none;border:0;border-bottom:2px solid transparent;padding:10px 14px;font:600 14px inherit;font-family:inherit;color:var(--tx2);cursor:pointer}
.tab.on{color:var(--blue);border-bottom-color:var(--blue)}
.tpanel{display:none;padding:var(--s16)}.tpanel.on{display:block}
.acc{display:flex;align-items:center;justify-content:space-between;padding:var(--s12) var(--s16);cursor:pointer;user-select:none}
.collapsed .tabs,.collapsed .tpanels{display:none}
.gcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:var(--s8)}
.gc{padding:var(--s8);text-align:center}.gc .ch{font-size:20px;font-weight:700}
.gc .imgs{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:6px 0}.gc .imgs figure{margin:0;min-width:0}.gc .imgs img{width:100%;aspect-ratio:1/1.1;object-fit:contain;image-rendering:pixelated;border-radius:4px;border:1px solid var(--line);background:#000}
.gc figcaption{font-size:11px;color:var(--tx2)}
.lineh{font-weight:700;margin:var(--s16) 0 var(--s8)}
.legend{font-size:12px;color:var(--tx2)}.legend b{font-weight:700}
.note{background:var(--sub);border:1px solid var(--line);border-radius:10px;padding:var(--s12);font-size:13px;color:var(--tx2)}
.embed .dash{display:none}.embed body{background:transparent}
/* ── responsive ── */
/* 표는 감싸개 안에서 가로로 밀어 본다(화면 전체가 옆으로 넘치지 않게) · 그림은 칸 폭을 넘지 않게 */
.tscroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.wrap img{max-width:100%;height:auto}.pane .stage img{max-width:none}
.dmain>*,.cmp>*,.grid>*,.stats>*,.gcards>*{min-width:0}
.finfo>span{min-width:0;overflow-wrap:anywhere}.dbar .vt{min-width:0;overflow-wrap:anywhere}
@media (max-width:1439px){.dmain{grid-template-columns:minmax(0,1fr) 240px}.stats{grid-template-columns:repeat(3,minmax(0,1fr))}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:1023px){.dmain{grid-template-columns:minmax(0,1fr)}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.search{width:100%;margin-left:0}}
@media (max-width:767px){.wrap{padding:var(--s12) var(--s12) var(--s24)}.cmp,.cmp.stack{grid-template-columns:minmax(0,1fr)}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s8)}
 .grid{grid-template-columns:minmax(0,1fr)}.pane{height:420px}.dbar{flex-wrap:wrap}.pad{padding:var(--s12)}
 h1{font-size:18px}h2{font-size:17px}.secttl{font-size:14px;padding:5px 12px}.stat{padding:var(--s12);gap:var(--s8)}.stat .ic{width:32px;height:32px;font-size:15px}.stat .n{font-size:22px}
 .verdict .big{font-size:30px}.tools,.dbar{padding:var(--s8) var(--s12)}.dmain{padding:0 var(--s8) var(--s12)}.tabs{padding:0 var(--s8)}.tpanel{padding:var(--s12) var(--s8)}
 .gcards{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}.vsep{display:none}}
"""

JS = r"""
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
/* 묶음 화면(최종.html) 안에 넣어 보일 때(?embed): 이 화면의 대시보드는 숨기고, 돌아가기·이전·다음은 바깥 화면이 처리 */
const EMB=new URLSearchParams(location.search).has('embed');if(EMB)document.documentElement.classList.add('embed');
/* 대시보드 필터·검색 — 카드의 data-* 로 거른다 */
const F={st:'all',type:null,bad:false,unk:false,q:''};
function applyF(){let n=0;$$('.vcard').forEach(c=>{const d=c.dataset;let ok=true;
 if(F.st==='run'&&d.state!=='진행 중')ok=false; if(F.st==='wait'&&d.state!=='대기')ok=false;
 if(F.type&&d.type!==F.type)ok=false; if(F.bad&&d.match!=='no')ok=false; if(F.unk&&d.font!=='unk')ok=false;
 if(F.q&&!d.title.toLowerCase().includes(F.q))ok=false; c.style.display=ok?'':'none'; if(ok)n++;});
 $('#emptyF').style.display=n?'none':'';}
$$('[data-st]').forEach(b=>b.onclick=()=>{$$('[data-st]').forEach(x=>x.classList.remove('on'));b.classList.add('on');F.st=b.dataset.st;applyF()});
$$('[data-type]').forEach(b=>b.onclick=()=>{const on=!b.classList.contains('on');$$('[data-type]').forEach(x=>x.classList.remove('on'));if(on)b.classList.add('on');F.type=on?b.dataset.type:null;applyF()});
$('#fBad').onchange=e=>{F.bad=e.target.checked;applyF()};$('#fUnk').onchange=e=>{F.unk=e.target.checked;applyF()};
$('#q').oninput=e=>{F.q=e.target.value.trim().toLowerCase();applyF()};
$$('.vcard').forEach(c=>c.onclick=e=>{if(e.target.closest('button'))return;$$('.vcard').forEach(x=>x.classList.remove('sel'));c.classList.add('sel');$('#detail').scrollIntoView({behavior:'smooth'})});
$('#newBtn').onclick=()=>alert('영상 등록은 아직 만들지 않았습니다(이번에는 조니 뎁 한 편만 넣으라는 지시).');
$('#guideBtn').onclick=()=>{const g=$('#guide');g.style.display=g.style.display==='none'?'':'none'};

/* 상세 비교 도구 */
const V={mode:'cmp',view:'title',z:1,fit:1,x:0,y:0,op:50,grid:false,blink:null,phase:0};
const SRC=window.SRC;
const panes=()=>$$('.pane');
function setImgs(){const s=SRC[V.view];const two=V.mode==='cmp';
 $('#cmp').classList.toggle('single',!two);$('#cmp').classList.toggle('stack',two&&s.w/s.h>2);
 $('#paneR').style.display=two?'':'none';requestAnimationFrame(()=>{sizePanes();});
 const L=$('#paneL');L.querySelector('.lab').textContent=two?'원본 이미지':(V.mode==='blink'?(V.phase?'재현 이미지':'원본 이미지'):'원본 + 재현 겹침');
 L.querySelector('.base').src=s.o; L.querySelector('.top').src=s.r;
 L.querySelector('.top').style.display=two?'none':'';
 L.querySelector('.top').style.opacity=V.mode==='overlay'?V.op/100:(V.mode==='blink'?(V.phase?1:0):0);
 $('#paneR .base').src=s.r;
 $$('.pane .dim').forEach((d,i)=>d.textContent=(i===0&&two?'원본 크기: ':(two?'재현 크기: ':'크기: '))+s.w+' × '+s.h);
 $$('.pane .stage').forEach(st=>{st.style.width=s.w+'px';st.style.height=s.h+'px';st.querySelectorAll('img').forEach(im=>{im.width=s.w;im.height=s.h})});}
function fitZ(){const p=$('#paneL'),s=SRC[V.view];return Math.min(p.clientWidth/s.w,p.clientHeight/s.h);}
function draw(){const s=SRC[V.view];$$('.pane .stage').forEach(st=>{st.style.transform=`translate(${V.x}px,${V.y}px) scale(${V.z})`;
 st.querySelectorAll('img').forEach(im=>im.classList.toggle('pix',V.z>=2))});
 document.documentElement.style.setProperty('--gs',Math.max(8,40*V.z/ (V.fit||1))+'px');
 $('#zl').textContent=Math.round(V.z*100)+'%';}
function center(){const p=$('#paneL'),s=SRC[V.view];V.x=(p.clientWidth-s.w*V.z)/2;V.y=(p.clientHeight-s.h*V.z)/2;}
function clampXY(){const p=$('#paneL'),s=SRC[V.view],w=s.w*V.z,h=s.h*V.z;
 V.x=w<=p.clientWidth?(p.clientWidth-w)/2:Math.min(0,Math.max(p.clientWidth-w,V.x));
 V.y=h<=p.clientHeight?(p.clientHeight-h)/2:Math.min(0,Math.max(p.clientHeight-h,V.y));}
function zoomAt(f,cx,cy){const nz=Math.min(16,Math.max(V.fit*0.5,V.z*f));V.x=cx-(cx-V.x)*nz/V.z;V.y=cy-(cy-V.y)*nz/V.z;V.z=nz;clampXY();draw();}
function stopBlink(){if(V.blink){clearInterval(V.blink);V.blink=null;}$('#bBlink').classList.remove('on');}
function setMode(m){stopBlink();V.mode=m;$$('[data-mode]').forEach(b=>b.classList.toggle('on',b.dataset.mode===m));
 if(m==='blink'){V.phase=0;$('#bBlink').classList.add('on');V.blink=setInterval(()=>{V.phase^=1;setImgs();},600);} setImgs();requestAnimationFrame(fitView);}
function sizePanes(){const s=SRC[V.view],p=$('#paneL');const h=Math.max(200,Math.min(620,Math.round(p.clientWidth*s.h/s.w)));$$('.pane').forEach(x=>x.style.height=h+'px');}
function fitView(){sizePanes();V.fit=fitZ();V.z=V.fit;center();draw();}
function reset(){stopBlink();V.mode='cmp';V.op=50;$('#op').value=50;$('#opv').textContent='50%';V.grid=false;document.body.classList.remove('showgrid');$('#bGrid').classList.remove('on');
 $$('[data-mode]').forEach(b=>b.classList.toggle('on',b.dataset.mode==='cmp'));setImgs();requestAnimationFrame(fitView);}
$$('[data-mode]').forEach(b=>b.onclick=()=>{if(b.dataset.mode==='blink'&&V.blink){setMode('overlay');return;}setMode(b.dataset.mode)});
$('#bGrid').onclick=()=>{V.grid=!V.grid;document.body.classList.toggle('showgrid',V.grid);$('#bGrid').classList.toggle('on',V.grid)};
$('#op').oninput=e=>{V.op=+e.target.value;$('#opv').textContent=V.op+'%';if(V.mode!=='overlay')setMode('overlay');else setImgs();};
$('#zIn').onclick=()=>{const p=$('#paneL');zoomAt(1.25,p.clientWidth/2,p.clientHeight/2)};
$('#zOut').onclick=()=>{const p=$('#paneL');zoomAt(0.8,p.clientWidth/2,p.clientHeight/2)};
$('#zFit').onclick=fitView;
$('#z1').onclick=()=>{const p=$('#paneL');zoomAt(1/V.z,p.clientWidth/2,p.clientHeight/2)};
$('#bReset').onclick=reset;
$$('[data-view]').forEach(b=>b.onclick=()=>{$$('[data-view]').forEach(x=>x.classList.toggle('on',x===b));V.view=b.dataset.view;setImgs();requestAnimationFrame(fitView)});
panes().forEach(p=>{p.addEventListener('wheel',e=>{e.preventDefault();const r=p.getBoundingClientRect();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX-r.left,e.clientY-r.top)},{passive:false});
 p.addEventListener('pointerdown',e=>{p.setPointerCapture(e.pointerId);p.classList.add('drag');const sx=e.clientX-V.x,sy=e.clientY-V.y;
  const mv=ev=>{V.x=ev.clientX-sx;V.y=ev.clientY-sy;clampXY();draw()};const up=()=>{p.classList.remove('drag');p.removeEventListener('pointermove',mv);p.removeEventListener('pointerup',up)};
  p.addEventListener('pointermove',mv);p.addEventListener('pointerup',up)});});
$$('.pane img').forEach(im=>im.onerror=()=>{im.closest('.pane').querySelector('.err').style.display='grid'});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopBlink()});
window.addEventListener('resize',()=>{const was=V.z===V.fit;V.fit=fitZ();if(was){V.z=V.fit;center()}clampXY();draw()});
/* 상세 분석 탭·접기 */
$$('.tab').forEach(t=>t.onclick=()=>{$$('.tab').forEach(x=>x.classList.toggle('on',x===t));$$('.tpanel').forEach(p=>p.classList.toggle('on',p.id===t.dataset.t))});
$('#accH').onclick=()=>{$('#ana').classList.toggle('collapsed');$('#accA').textContent=$('#ana').classList.contains('collapsed')?'펼치기 ▾':'접기 ▴'};
setImgs();requestAnimationFrame(fitView);

if(EMB){const bar=$('.dbar');const bs=[...bar.querySelectorAll('button')];
 bs[0].onclick=()=>parent.scrollTo({top:0,behavior:'smooth'});
 const pv=bs.find(b=>b.textContent.includes('이전')),nx=bs.find(b=>b.textContent.includes('다음'));
 for(const [b,d,t] of [[pv,-1,'앞 영상으로 갑니다'],[nx,1,'다음 영상으로 갑니다']]){b.disabled=false;b.dataset.tip=t;b.setAttribute('aria-label',t);b.onclick=()=>parent.ttGo&&parent.ttGo(d);}}
"""


def build(D, vid, title):
    V = rj(os.path.join(D, "값", f"{vid}_검수.json"), {})
    FIT = rj(os.path.join(D, "값", "페이퍼로지_맞춤.json"), [])
    UI = rj(os.path.join(D, "값", "화면용.json"), {})
    R = rj(os.path.join(D, "값", f"{vid}.json"), {})
    eye = (rj(os.path.join(D, "값", "눈확인.json"), {}) or {}).get(vid) or {}
    W, H = R.get("canvas", [1080, 1920]); kind = "롱폼" if W > H else "쇼츠"
    tb = UI.get("title_box", [0, 0, W, H])
    title_lines = [L for L in V.get("lines", []) if L["text"] in {d["text"] for d in FIT}]
    allg = [g for L in title_lines for g in L["glyphs"]]
    mean_f1 = sum(g["f1"] for g in allg) / len(allg) if allg else None
    n_items = sum(len(L["items"]) for L in title_lines); n_diff = sum(1 for L in title_lines for x in L["items"].values() if not x["ok"])
    done_all = bool(V) and bool(eye)
    match = bool(V.get("all_ok"))
    upd = time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(D, "값", f"{vid}_검수.json")))) if V else "—"
    fit_by = {d["text"]: d for d in FIT}

    # 비교 그림
    SRC = {"title": dict(o="그림/제목칸_원본.png", r="그림/제목칸_재현.png", w=tb[2] - tb[0], h=tb[3] - tb[1]),
           "full": dict(o=f"그림/{vid}_원본.png", r=f"그림/{vid}_재현.png", w=W, h=H),
           "col": dict(o="그림/제목칸_원본.png", r="그림/제목칸_색겹침.png", w=tb[2] - tb[0], h=tb[3] - tb[1])}

    # 판정 원인: 독립 검수에서 다른 항목을 종류별로 센다
    def kind_of(k):
        for key, lab in (("색", "색상 차이"), ("획 굵기", "획 굵기 차이"), ("자간", "자간 차이"), ("너비", "가로 비율·너비 차이"), ("높이", "크기(높이) 차이"),
                         ("기울", "기울기 차이"), ("줄", "자리(줄 위·아래) 차이"), ("기준선", "자리(줄 위·아래) 차이"), ("행간", "줄 사이 차이")):
            if key in k: return lab
        return "기타"
    why = {}
    for L in title_lines:
        for k, x in L["items"].items():
            if not x["ok"]: why[kind_of(k)] = why.get(kind_of(k), 0) + 1
    shape_bad = sum(1 for g in allg if not g["ok"])
    why_html = "".join(f"<li>{E(k)} — {v}개 항목</li>" for k, v in sorted(why.items(), key=lambda z: -z[1]))
    why_html = f"<li>글자 형태 차이 — 글자 {shape_bad}/{len(allg)}자 겹침이 1.00 아님</li>" + why_html

    # 폰트 정보 표(가로 표 — 줄마다 한 행: 한 글꼴 집안, 효과만 다름)
    frows = []
    for li_, d in enumerate(FIT, 1):
        cols = " ".join(f'<span class="sw" style="background:{c}"></span>{c}' for c in dict.fromkeys(c_ for c_, ch_ in zip(d["colors"], d["text"]) if ch_ != " "))
        fl = [c["fit"] for c in UI.get("cards", []) if c["line"] == li_ and c["fit"] is not None]
        vl = [c["f1"] for c in UI.get("cards", []) if c["line"] == li_ and c["f1"] is not None]
        frows.append(f'<tr><td>「{E(d["text"])}」</td><td><b>{E(d["font"])}</b></td><td>{d["size"]}px</td><td>{round(d["hs"] * 100, 1)}%</td>'
                     f'<td>{round(d.get("vs", 1) * 100, 1)}%</td><td>{d["bold"]:+}px</td><td>{cols}</td>'
                     f'<td>{min(fl):.4f} / {sum(fl) / len(fl):.4f}</td><td>{f"{min(vl):.4f} / {sum(vl) / len(vl):.4f}" if vl else "<span class=small>글자 나누기 오류</span>"}</td></tr>')
    fam = sorted({d["font"].split(" ")[0] for d in FIT})
    # 테두리: 맞춤 값에 테두리 굵기가 있으면 보인다(없으면 「없음」)
    _ol = [d for d in FIT if d.get("outline_px")]
    outline_txt = (" · ".join(f'{d["outline_px"]:g}px {d.get("outline_color", "")}' for d in _ol) + " (바깥쪽은 점점 옅어짐 — 부드러운 그림자 함께)") if _ol else "없음"

    # 글자 카드(자르기 = 재현에서 그린 글자 자리 · 겹침 = 맞춤 값 + 독립 검수 값(같은 자리 글자를 찾은 때만))
    gcards = []; cur = None
    for c in UI.get("cards", []):
        d = FIT[c["line"] - 1]
        if cur != c["line"]:
            if cur is not None: gcards.append("</div>")
            nv = sum(1 for x in UI["cards"] if x["line"] == c["line"] and x["f1"] is not None)
            warn = "" if nv else ' <span class="badge b-warn">독립 검수가 이 줄 글자를 잘못 나눔 — 글자별 검수 값 없음</span>'
            gcards.append(f'<div class="lineh">「{E(d["text"])}」 — {E(d["font"])}{warn}</div><div class="gcards">'); cur = c["line"]
        ok = (c["f1"] or 0) >= 1.0 and (c["fit"] or 0) >= 1.0
        vtxt = f'검수 겹침 {c["f1"]:.4f}<br>상자 어긋남 {", ".join(f"{v:+.1f}" for v in c["d_box"])}px' if c["f1"] is not None else "검수 겹침 없음(글자 나누기 오류)"
        gcards.append(f'''<div class="card gc"><div class="ch">{E(c["ch"])}</div>
<div class="imgs"><figure><img src="그림/글자/{c["line"]}_{c["i"]}_o.png" alt="원본 {E(c["ch"])}"><figcaption>원본</figcaption></figure>
<figure><img src="그림/글자/{c["line"]}_{c["i"]}_r.png" alt="재현 {E(c["ch"])}"><figcaption>재현</figcaption></figure>
<figure><img src="그림/글자/{c["line"]}_{c["i"]}_c.png" alt="색 겹침 {E(c["ch"])}"><figcaption>겹침</figcaption></figure></div>
<span class="badge {"b-ok" if ok else "b-err"}">{"일치" if ok else "불일치"}</span>
<div class="small" style="margin-top:4px">맞춤 겹침 {c["fit"]:.4f}<br>{vtxt}</div></div>''')
    if cur is not None: gcards.append("</div>")
    fits = [c["fit"] for c in UI.get("cards", []) if c["fit"] is not None]
    fit_mean = sum(fits) / len(fits) if fits else None
    l1 = [c["f1"] for c in UI.get("cards", []) if c["f1"] is not None]
    v1_mean = sum(l1) / len(l1) if l1 else None
    bad_lines = [FIT[i - 1]["text"] for i in sorted({c["line"] for c in UI.get("cards", [])}) if not any(x["f1"] is not None for x in UI["cards"] if x["line"] == i)]

    # 색·자리·수치 표
    def items_table(filt):
        rows = []
        for L in title_lines:
            for k, x in L["items"].items():
                if not filt(k): continue
                rows.append(f'<tr><td>「{E(L["text"])}」</td><td>{E(k)}</td><td>{E(x["o"])}</td><td>{E(x["r"])}</td><td>{E(x["d"])}</td>'
                            f'<td><span class="badge {"b-ok" if x["ok"] else "b-err"}">{"같음" if x["ok"] else "다름"}</span></td></tr>')
        return ('<div class="tscroll"><table class="t"><tr><th>줄</th><th>항목</th><th>원본</th><th>재현</th><th>차이</th><th>판정</th></tr>' + "".join(rows) + "</table></div>") if rows else '<div class="note">이 항목은 잰 값이 없습니다.</div>'
    def swatch_cell(v):
        s = str(v)
        return f'<span class="sw" style="background:{E(s)}"></span>{E(s)}' if s.startswith("#") else E(s)
    crow = []
    for L in title_lines:
        for k, x in L["items"].items():
            if "색" not in k: continue
            o, r = str(x["o"]), str(x["r"])
            rgb = lambda h: ",".join(str(int(h[i:i + 2], 16)) for i in (1, 3, 5)) if h.startswith("#") and len(h) == 7 else "—"
            crow.append(f'<tr><td>「{E(L["text"])}」</td><td>{E(k)}</td><td>{swatch_cell(o)}<br><span class="small">RGB {rgb(o)}</span></td>'
                        f'<td>{swatch_cell(r)}<br><span class="small">RGB {rgb(r)}</span></td><td>{E(x["d"])}</td><td><span class="badge {"b-ok" if x["ok"] else "b-err"}">{"같음" if x["ok"] else "다름"}</span></td></tr>')
    ctable = ('<div class="tscroll"><table class="t"><tr><th>줄</th><th>항목</th><th>원본 색</th><th>재현 색</th><th>차이</th><th>판정</th></tr>' + "".join(crow) + "</table></div>") if crow else '<div class="note">색 값이 없습니다.</div>'
    px = UI.get("pixels", {})

    state_badge = ('<span class="badge b-ok">● 완료</span>' if done_all else '<span class="badge b-warn">● 완료 안 됨</span>')
    match_badge = ('<span class="badge b-ok">✓ 100% 일치</span>' if match else '<span class="badge b-err">✕ 일치 안 됨</span>')
    font_state = "unk"   # 글자마다 겹침 1.00 이 아니면 원본 글꼴은 미확인
    thumb = f"그림/{vid}_원본.png"
    titleE = E(title)

    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>폰트 재현 검수 시스템 — {titleE}</title><style>{CSS}</style></head><body><div class="wrap">

<div class="secttl dash">1. 대시보드 화면 (전체 현황 및 작업 목록)</div>
<div class="card pad dash">
 <div class="top"><div class="logo">Aa</div><div><h1>폰트 재현 검수 시스템</h1><div class="small">원본과 재현 이미지를 비교하고, 폰트 일치 여부를 확인하세요</div></div>
  <div class="sp"></div><span class="small">🕒 마지막 업데이트 {E(upd)}</span><button class="btn sm" id="guideBtn" data-tip="이 화면에 무엇이 들어 있는지 설명을 열고 닫습니다" aria-label="이 화면에 무엇이 들어 있는지 설명을 열고 닫습니다">작업 가이드 ?</button><button class="btn pri" id="newBtn" data-tip="새 영상(YouTube 주소나 썸네일 그림)을 등록합니다 — 아직 만들지 않음" aria-label="새 영상(YouTube 주소나 썸네일 그림)을 등록합니다 — 아직 만들지 않음">＋ 신규 영상 등록</button></div>
 <div id="guide" class="note" style="margin-top:12px;display:none"><div>이 화면에는 운영자 지시(2026-11-24 「이번에 만든 것만 … 이것만 넣어봐」)대로 <b>조니 뎁 영상 한 편</b>만 들어 있습니다. 제목 글꼴을 페이퍼로지 한 집안으로 다시 맞춘 결과입니다. 「일치」는 모든 잰 값이 원본과 100% 같을 때만 붙습니다.</div></div>
 <div class="stats">
  <div class="card stat"><div class="ic" style="background:var(--bluel);color:var(--blue)">▶</div><div><div class="l">전체 영상</div><div class="n">1개</div></div></div>
  <div class="card stat"><div class="ic" style="background:var(--bluel);color:var(--blue)">⟳</div><div><div class="l">진행 중</div><div class="n">0개</div></div></div>
  <div class="card stat"><div class="ic" style="background:#EEF1F6;color:var(--tx2)">◷</div><div><div class="l">대기</div><div class="n">0개</div></div></div>
  <div class="card stat"><div class="ic" style="background:#E8F7EE;color:var(--ok)">✓</div><div><div class="l">폰트 일치</div><div class="n">{1 if match else 0}개</div></div></div>
  <div class="card stat"><div class="ic" style="background:#FEF3DC;color:var(--warn)">?</div><div><div class="l">폰트 미확인</div><div class="n">{0 if match else 1}개</div></div></div>
  <div class="card stat"><div class="ic" style="background:var(--bluel);color:var(--blue)">%</div><div><div class="l">전체 통과율</div><div class="n">{100 if match else 0}%</div></div></div>
 </div>
 <div class="filters">
  <button class="chip on" data-st="all" data-tip="모든 영상을 보입니다" aria-label="모든 영상을 보입니다">전체 (1)</button><button class="chip" data-st="run" data-tip="지금 재현을 돌리는 중인 영상만 보입니다" aria-label="지금 재현을 돌리는 중인 영상만 보입니다">진행 중 (0)</button><button class="chip" data-st="wait" data-tip="다시 돌리려고 줄 세운 영상만 보입니다" aria-label="다시 돌리려고 줄 세운 영상만 보입니다">대기 (0)</button>
  <span class="vsep"></span><button class="chip" data-type="쇼츠" data-tip="세로 썸네일(쇼츠) 영상만 — 다시 누르면 풀림" aria-label="세로 썸네일(쇼츠) 영상만 — 다시 누르면 풀림">쇼츠</button><button class="chip" data-type="롱폼" data-tip="가로 썸네일(롱폼) 영상만 — 다시 누르면 풀림" aria-label="가로 썸네일(롱폼) 영상만 — 다시 누르면 풀림">롱폼</button><span class="vsep"></span>
  <label class="tog" data-tip="원본과 일치하지 않는 영상만 보입니다">불일치만 보기 <input type="checkbox" id="fBad" aria-label="원본과 일치하지 않는 영상만 보입니다"></label><span class="vsep"></span><label class="tog" data-tip="원본 글꼴을 확정하지 못한 영상만 보입니다">폰트 미확인만 보기 <input type="checkbox" id="fUnk" aria-label="원본 글꼴을 확정하지 못한 영상만 보입니다"></label>
  <span class="search" data-tip="영상 제목으로 찾습니다(글자를 치는 대로 바로 걸러짐)"><input class="inp" style="width:100%" id="q" aria-label="영상 제목으로 찾습니다(글자를 치는 대로 바로 걸러짐)" placeholder="🔍 영상 제목을 검색하세요..."></span>
 </div>
 <div class="grid">
  <div class="card vcard sel" data-state="{"완료" if done_all else "완료 안 됨"}" data-type="{kind}" data-match="{"yes" if match else "no"}" data-font="{font_state}" data-title="{titleE.lower()}">
   <div class="vt">▶ {titleE}</div><div class="th"><img src="{thumb}" alt="썸네일" onerror="this.replaceWith(Object.assign(document.createElement('span'),{{textContent:'썸네일 없음',className:'small'}}))"></div>
   <div class="ft"><span class="badge b-blue">{kind}</span>{state_badge}{match_badge}<span class="sp" style="flex:1"></span><span class="small">겹침 {fit_mean:.3f}</span></div>
  </div>
 </div>
 <div id="emptyF" class="empty" style="display:none">조건에 맞는 영상이 없습니다.</div>
</div>

<div class="secttl dash" style="margin-top:24px">2. 상세 검수 화면 (비교 및 분석)</div>
<div class="card" id="detail">
 <div class="dbar"><button class="btn sm" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" data-tip="위쪽 대시보드(영상 목록)로 올라갑니다" aria-label="위쪽 대시보드(영상 목록)로 올라갑니다">← 대시보드로 돌아가기</button>
  <img class="mini" src="{thumb}" alt=""><span class="vt">{titleE}</span><span class="badge b-bl">{kind}</span><span style="flex:1"></span>
  {state_badge}{match_badge}<button class="btn sm" disabled data-tip="앞 영상으로 — 지금은 영상이 1편이라 꺼 둠" aria-label="앞 영상으로 — 지금은 영상이 1편이라 꺼 둠">‹ 이전</button><button class="btn sm" disabled data-tip="다음 영상으로 — 지금은 영상이 1편이라 꺼 둠" aria-label="다음 영상으로 — 지금은 영상이 1편이라 꺼 둠">다음 ›</button></div>
 <div class="tools">
  <button class="btn sm on" data-mode="cmp" data-tip="원본과 재현을 나란히(가로로 긴 그림은 위아래로) 봅니다" aria-label="원본과 재현을 나란히(가로로 긴 그림은 위아래로) 봅니다">▣ 비교 보기</button><button class="btn sm" data-mode="blink" id="bBlink" data-tip="원본과 재현을 0.6초마다 번갈아 보여 줍니다 — 다시 누르면 멈춤" aria-label="원본과 재현을 0.6초마다 번갈아 보여 줍니다 — 다시 누르면 멈춤">◐ 깜빡이기</button><button class="btn sm" data-mode="overlay" data-tip="원본 위에 재현을 같은 자리에 겹칩니다 — 투명도 막대로 진하기 조절" aria-label="원본 위에 재현을 같은 자리에 겹칩니다 — 투명도 막대로 진하기 조절">⧉ 겹쳐보기</button>
  <button class="btn sm" id="bGrid" data-tip="그림 위에 칸 줄을 그어 글자 자리·기준선을 비교합니다 — 다시 누르면 끔" aria-label="그림 위에 칸 줄을 그어 글자 자리·기준선을 비교합니다 — 다시 누르면 끔">▦ 격자 표시</button><span class="vsep"></span>
  <span class="small">투명도</span><span data-tip="겹쳐보기에서 위에 얹은 재현 그림의 진하기(0~100%) — 움직이면 겹쳐보기로 바뀜" style="display:inline-flex;align-items:center"><input type="range" id="op" min="0" max="100" value="50" aria-label="겹쳐보기에서 위에 얹은 재현 그림의 진하기(0~100%) — 움직이면 겹쳐보기로 바뀜"></span><b id="opv" style="width:40px">50%</b><span class="vsep"></span>
  <button class="btn sm" id="zIn" data-tip="그림을 1.25배 키웁니다 — 그림 위에서 마우스 휠로도 됨, 끌어서 옮기기" aria-label="그림을 1.25배 키웁니다 — 그림 위에서 마우스 휠로도 됨, 끌어서 옮기기">＋ 확대</button><button class="btn sm" id="zOut" data-tip="그림을 0.8배 줄입니다" aria-label="그림을 0.8배 줄입니다">－ 축소</button><b id="zl" class="small" style="width:46px;text-align:center">100%</b>
  <button class="btn sm" id="zFit" data-tip="그림 전체가 칸 안에 들어오게 맞춥니다" aria-label="그림 전체가 칸 안에 들어오게 맞춥니다">화면 맞춤</button><button class="btn sm" id="z1" data-tip="그림을 원래 화소 크기(100%)로 봅니다" aria-label="그림을 원래 화소 크기(100%)로 봅니다">원래 크기</button><button class="btn sm" id="bReset" data-tip="확대·위치·투명도(50%)·격자·깜빡이기를 처음 상태로 되돌립니다(결과 값은 안 바뀜)" aria-label="확대·위치·투명도(50%)·격자·깜빡이기를 처음 상태로 되돌립니다(결과 값은 안 바뀜)">↺ 초기화</button>
  <span class="vsep"></span><button class="btn sm on" data-view="title" data-tip="썸네일에서 제목 두 줄 부분만 잘라 크게 봅니다" aria-label="썸네일에서 제목 두 줄 부분만 잘라 크게 봅니다">제목 부분</button><button class="btn sm" data-view="full" data-tip="썸네일 전체(1080×1920)를 봅니다" aria-label="썸네일 전체(1080×1920)를 봅니다">전체 썸네일</button><button class="btn sm" data-view="col" data-tip="흰색=둘 다 글자 · 자홍=원본에만 · 초록=재현에만 인 그림으로 봅니다" aria-label="흰색=둘 다 글자 · 자홍=원본에만 · 초록=재현에만 인 그림으로 봅니다">색 겹침</button>
 </div>
 <div class="dmain">
  <div class="cmp" id="cmp">
   <div class="pane" id="paneL"><span class="lab">원본 이미지</span><div class="stage"><img class="base" alt="원본"><img class="top" alt="재현"></div><div class="gridov"></div><span class="dim"></span><div class="err">그림을 불러오지 못했습니다</div></div>
   <div class="pane" id="paneR"><span class="lab">재현 이미지</span><div class="stage"><img class="base" alt="재현"></div><div class="gridov"></div><span class="dim"></span><div class="err">그림을 불러오지 못했습니다</div></div>
  <div class="card fpanel pad"><h3>◇ 폰트 정보</h3>
   <div class="finfo"><span>원본 폰트 <b style="color:var(--warn)">미확인</b> <span class="small">(글자 겹침이 1.00이 아님)</span></span>
    <span>최유사 후보 <b>{E(" · ".join(fam))}</b> <span class="small">{"(집안 하나 — 굵기만 줄마다 다름)" if len(fam) == 1 else "(집안 여럿 — 아래 표의 줄마다 글꼴 참고)"}</span></span>
    <span>기울기 <b>0°</b> <span class="small">(맞추지 않음)</span></span><span>테두리·그림자 <b>{E(outline_txt)}</b></span></div>
   <div class="tscroll"><table class="t ftab"><tr><th>줄</th><th>글꼴</th><th>크기</th><th>가로</th><th>세로</th><th>굵기 조절</th><th>글자 색</th><th>맞춤 겹침<br>최소 / 평균</th><th>독립 검수 겹침<br>최소 / 평균</th></tr>
   {"".join(frows)}</table></div>
   <div class="small" style="margin-top:8px">굵기 조절 = 원본 화소의 진하기(배경→글자색 사이 0~1)와 같아지도록 0.05px 단위로 맞춘 값 · 자간 = 글자마다 1/8px 자리로 맞춤(줄 하나의 값으로 재지 않음)</div></div>
  </div>
  <div class="card verdict pad"><h3 style="color:var(--err)">ⓘ 검수 결과</h3>
   <div class="small" style="margin-top:8px">제목 글자 겹침 평균(맞춤 · 글자 {len(fits)}자)</div><div class="big">{fit_mean * 100:.1f}%</div>
   <div class="small">독립 검수 글자 겹침 평균 {v1_mean * 100:.1f}% (글자 {len(l1)}자만)</div>
   {match_badge}
   <div class="small" style="margin-top:8px">검수 항목 {n_items}개 중 <b>{n_diff}개 다름</b></div>
   <ul class="why">{why_html}</ul>
   {f'<div class="small" style="text-align:left;color:#B45309;margin-top:6px">⚠ 독립 검수가 「{E(" / ".join(bad_lines))}」 글자를 잘못 나눔 — 이 줄의 항목 판정은 못 믿음(검수 도구 고칠 것)</div>' if bad_lines else ''}
   <div class="small" style="text-align:left;margin-top:8px">Claude 눈 확인: {E(eye.get("note", "안 함"))}</div></div>
 </div>
 <div id="ana">
  <div class="acc" id="accH" style="border-top:1px solid var(--line)"><h3>상세 분석</h3><span class="btn sm" id="accA">접기 ▴</span></div>
  <div class="tabs"><button class="tab on" data-t="t1" data-tip="원본과 재현의 색 겹침 그림" aria-label="원본과 재현의 색 겹침 그림">비교 이미지</button><button class="tab" data-t="t2" data-tip="화소 수와 줄 자리·크기 값(독립 검수)" aria-label="화소 수와 줄 자리·크기 값(독립 검수)">픽셀 분석</button><button class="tab" data-t="t3" data-tip="원본 색과 재현 색(HEX·RGB)과 차이" aria-label="원본 색과 재현 색(HEX·RGB)과 차이">색상 비교</button><button class="tab" data-t="t4" data-tip="글자마다 원본·재현·겹침 그림과 겹침 값" aria-label="글자마다 원본·재현·겹침 그림과 겹침 값">글자별 비교</button><button class="tab" data-t="t5" data-tip="독립 검수가 잰 모든 값을 표로" aria-label="독립 검수가 잰 모든 값을 표로">수치 데이터</button></div>
  <div class="tpanels">
   <div class="tpanel on" id="t1"><div class="legend" style="margin-bottom:8px"><b>흰색</b> = 둘 다 글자 · <b style="color:#d0d">자홍</b> = 원본에만 · <b style="color:#0a0">초록</b> = 재현에만</div>
    <img src="그림/제목칸_색겹침.png" alt="색 겹침" style="max-width:100%;border-radius:10px;border:1px solid var(--line)"></div>
   <div class="tpanel" id="t2"><div class="tscroll"><table class="t" style="max-width:640px"><tr><th>항목</th><th>값</th></tr>
    <tr><td>그림 크기</td><td>{W} × {H}</td></tr><tr><td>비교 범위(제목 칸)</td><td>x {tb[0]}~{tb[2]}, y {tb[1]}~{tb[3]}</td></tr>
    <tr><td>둘 다 글자인 화소</td><td>{px.get("both", "안 잼")}</td></tr><tr><td>원본에만 있는 화소(자홍)</td><td>{px.get("o_only", "안 잼")}</td></tr>
    <tr><td>재현에만 있는 화소(초록)</td><td>{px.get("r_only", "안 잼")}</td></tr></table></div>
    <div class="lineh">자리·크기 (독립 검수)</div>{items_table(lambda k: "색" not in k)}</div>
   <div class="tpanel" id="t3">{ctable}</div>
   <div class="tpanel" id="t4">{"".join(gcards)}</div>
   <div class="tpanel" id="t5">{items_table(lambda k: True)}</div>
  </div>
 </div>
</div>
</div>
<script>window.SRC={json.dumps(SRC, ensure_ascii=False)};{JS}</script></body></html>'''


if __name__ == "__main__":
    D, vid, title = sys.argv[1], sys.argv[2], sys.argv[3]
    p = os.path.join(D, "새화면.html")
    open(p, "w", encoding="utf-8").write(build(D, vid, title))
    print("만듦:", p)
