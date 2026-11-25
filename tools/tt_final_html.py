# 최종 묶음 화면: 영상 여러 편을 대시보드 하나에 카드로 놓고, 카드를 고르면 아래에 그 영상의 상세 화면(새화면.html?embed)을 띄운다.
#   python tt_final_html.py <타이틀재현_3판 폴더> <폴더1> <영상id1> "<제목1>" [<폴더2> <영상id2> "<제목2>" ...]
#   폴더는 <타이틀재현_3판 폴더> 기준 상대 경로(예: 새화면_조니뎁). 결과 = <타이틀재현_3판 폴더>/최종.html
import os, sys, json, html, time, shutil, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tt_newui_html import CSS, rj

E = lambda s: html.escape(str(s), quote=True)


def info(R, rel, vid, title):
    D = os.path.join(R, rel)
    V = rj(os.path.join(D, "값", f"{vid}_검수.json"), {})
    UI = rj(os.path.join(D, "값", "화면용.json"), {})
    J = rj(os.path.join(D, "값", f"{vid}.json"), {})
    eye = (rj(os.path.join(D, "값", "눈확인.json"), {}) or {}).get(vid)
    W, H = J.get("canvas", [1080, 1920])
    fits = [c["fit"] for c in UI.get("cards", []) if c.get("fit") is not None]
    up = os.path.getmtime(os.path.join(D, "값", f"{vid}_검수.json")) if V else 0
    return dict(rel=rel.replace("\\", "/"), vid=vid, title=title, kind="롱폼" if W > H else "쇼츠",
                done=bool(V) and bool(eye), match=bool(V.get("all_ok")),
                fit=sum(fits) / len(fits) if fits else None, up=up)


JS = r"""
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];let cur=0;
const fr=$('#dframe');
function show(i,scroll){cur=(i+PAGES.length)%PAGES.length;$$('.vcard').forEach(c=>c.classList.toggle('sel',+c.dataset.i===cur));fr.src=PAGES[cur];if(scroll)$('#detail').scrollIntoView({behavior:'smooth'});}
window.ttGo=d=>show(cur+d,true);
setInterval(()=>{try{const h=fr.contentDocument.documentElement.scrollHeight;if(h&&Math.abs(fr.offsetHeight-h)>2)fr.style.height=h+'px';}catch(e){}},300);
$$('.vcard').forEach(c=>{c.onclick=()=>show(+c.dataset.i,true);c.onkeydown=e=>{if(e.key==='Enter')show(+c.dataset.i,true)}});
const F={type:null,bad:false,q:''};
function applyF(){let n=0;$$('.vcard').forEach(c=>{const d=c.dataset;let ok=true;if(F.type&&d.kind!==F.type)ok=false;if(F.bad&&d.match!=='no')ok=false;if(F.q&&!d.title.includes(F.q))ok=false;c.style.display=ok?'':'none';if(ok)n++;});$('#emptyF').style.display=n?'none':'';}
$$('button[data-type]').forEach(b=>b.onclick=()=>{const on=!b.classList.contains('on');$$('button[data-type]').forEach(x=>x.classList.remove('on'));if(on)b.classList.add('on');F.type=on?b.dataset.type:null;applyF()});
$('[data-st=all]').onclick=()=>{$$('button[data-type]').forEach(x=>x.classList.remove('on'));F.type=null;$('#fBad').checked=false;F.bad=false;$('#q').value='';F.q='';applyF()};
$('#fBad').onchange=e=>{F.bad=e.target.checked;applyF()};$('#q').oninput=e=>{F.q=e.target.value.trim().toLowerCase();applyF()};
function ed(id){window.open('편집기.html?base=.'+(id?'&id='+encodeURIComponent(id):''),'tt_editor','width=1600,height=1000');}
const edV=()=>window.open('편집기.html?base='+encodeURIComponent(VIDS[cur][0])+'&id='+encodeURIComponent(VIDS[cur][1]),'tt_editor','width=1600,height=1000');$('#edBtn').onclick=edV;$('#edCur').onclick=edV;   // 편집기 = 지금 고른 영상(공유 주소에도 영상 폴더째 올라가 바로 열림)
// 신규 영상 등록: 이 화면을 도구가 설치된 컴퓨터의 편집 서버(tt_editor.py)로 열었을 때만 자동 재현이 돎
let SRV=false;fetch('/jobs').then(r=>{SRV=r.ok&&(r.headers.get('content-type')||'').includes('json');if(SRV)jobs();}).catch(()=>{});
const nm=t=>{$('#newMsg').textContent=t};
$('#newBtn').onclick=()=>{const b=$('#newBox');b.style.display=b.style.display==='none'?'':'none';if(!SRV)nm('이 화면은 자동 재현 도구 없이 열려 있습니다(공유 주소·파일). 그림을 넣으면 편집기에서 손으로 맞출 수 있고, 자동 재현은 도구를 설치한 컴퓨터에서 「python tools/tt_editor.py <결과 폴더>」로 켠 뒤 http://127.0.0.1:8765/최종.html 로 열면 됩니다.');};
async function startJob(body,headers){if(!SRV){ed('');return;}const r=await(await fetch('/entry',{method:'POST',body,headers})).json();if(!r.job){nm('시작 못 함: '+JSON.stringify(r));return;}nm('시작함 — 아래에 단계·걸린 시간이 보입니다(무거운 일이라 몇 분~수십 분).');jobs();}
const up=f=>{if(!f)return;if(!/^image\/(jpeg|png|webp)$/.test(f.type)){nm('jpg·png·webp 그림만 받습니다.');return;}startJob(f,{'Content-Type':f.type,'X-Name':encodeURIComponent(f.name)});};
$('#drop').onclick=()=>$('#upf').click();$('#upf').onchange=e=>up(e.target.files[0]);
$('#drop').ondragover=e=>{e.preventDefault();$('#drop').style.borderColor='var(--blue)'};$('#drop').ondragleave=()=>{$('#drop').style.borderColor=''};
$('#drop').ondrop=e=>{e.preventDefault();$('#drop').style.borderColor='';up([...e.dataTransfer.files][0]);};
$('#ygo').onclick=()=>{const s=$('#yurl').value.trim();if(!/^[A-Za-z0-9_-]{11}$/.test(s)&&!/(youtube\.com\/(watch\?|shorts\/|live\/|embed\/)|youtu\.be\/)/.test(s)){nm('유튜브 주소(watch?v= · youtu.be/ · shorts/)나 영상 번호 11자를 넣어 주세요.');return;}startJob(JSON.stringify({url:s}),{'Content-Type':'application/json'});};
const esc=t=>String(t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let JT=null;async function jobs(){if(!SRV)return;let L=[],W=[];try{L=await(await fetch('/jobs')).json();W=await(await fetch('/ai_wait')).json();}catch(e){}
 const wait=new Set(W.map(x=>x.job));
 $('#jobList').innerHTML=L.length?'<table class="small" style="width:100%"><tr><th align=left>작업</th><th align=left>상태</th><th align=left>걸린 시간</th><th></th></tr>'+L.slice(0,10).map(j=>`<tr><td>${esc((j.제목||j.job).slice(0,40))}</td><td>${esc(j.상태)}${wait.has(j.job)?' · <b>AI 눈 확인 대기</b>':''}</td><td>${j.경과초||0}초</td><td><a href="/?job=${encodeURIComponent(j.job)}" target="_blank">진행</a>${j.상태==='끝'?` · <a href="/view/${encodeURIComponent(j.job)}/비교.html" target="_blank">비교 화면</a> · <a href="/?r=${encodeURIComponent(j.job)}&id=${encodeURIComponent(j.영상||'')}" target="_blank">편집기</a>`:''}</td></tr>`).join('')+'</table>':'<span class="small">아직 등록한 작업이 없습니다.</span>';
 clearTimeout(JT);if(L.some(j=>j.상태==='진행 중'))JT=setTimeout(jobs,4000);}
$('#guideBtn').onclick=()=>{const g=$('#guide');g.style.display=g.style.display==='none'?'':'none'};
show(0,false);
"""


def build(items):
    n = len(items)
    nm = sum(1 for x in items if x["match"])
    upd = time.strftime("%m-%d %H:%M", time.localtime(max(x["up"] for x in items)))
    cards = []
    for k, x in enumerate(items):
        st = '<span class="badge b-ok">● 완료</span>' if x["done"] else '<span class="badge b-warn">● 완료 안 됨</span>'
        mt = '<span class="badge b-ok">✓ 100% 일치</span>' if x["match"] else '<span class="badge b-err">✕ 일치 안 됨</span>'
        fit = f'겹침 {x["fit"]:.3f}' if x["fit"] is not None else ""
        cards.append(
            f'<div class="card vcard{" sel" if k == 0 else ""}" data-i="{k}" data-kind="{x["kind"]}" '
            f'data-match="{"yes" if x["match"] else "no"}" data-title="{E(x["title"].lower())}" tabindex="0" role="button" '
            f'aria-label="{E(x["title"])} — 누르면 아래에 상세 비교 화면이 열립니다" data-tip="누르면 아래에 이 영상의 상세 비교 화면이 열립니다">'
            f'<div class="vt">▶ {E(x["title"])}</div><div class="th"><img src="{E(x["rel"])}/그림/{E(x["vid"])}_원본.png" alt="썸네일"></div>'
            f'<div class="ft"><span class="badge b-blue">{x["kind"]}</span>{st}{mt}<span class="sp" style="flex:1"></span><span class="small">{fit}</span></div></div>')
    # 편집기에 줄 폴더: 영상 폴더에 값/<영상>.json 이 있으면 그 폴더(공유 주소에도 그 폴더째 올라감), 없으면 이 폴더
    vids = json.dumps([[x["rel"] if os.path.exists(os.path.join(ROOT, x["rel"], "값", x["vid"] + ".json")) else ".", x["vid"]] for x in items], ensure_ascii=False)
    pages = json.dumps([f'{x["rel"]}/새화면.html?embed' for x in items], ensure_ascii=False)
    nk = lambda t: sum(1 for x in items if x["kind"] == t)
    chip = lambda t: (f'<button class="chip" data-type="{t}" data-tip="{t} 영상만 — 다시 누르면 풀림" '
                      f'aria-label="{t} 영상만 — 다시 누르면 풀림">{t} ({nk(t)})</button>')
    stat = lambda ic, bg, col, lab, v: (f'<div class="card stat"><div class="ic" style="background:{bg};color:{col}">{ic}</div>'
                                        f'<div><div class="l">{lab}</div><div class="n">{v}</div></div></div>')
    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>폰트 재현 검수 시스템 — 최종 {n}편</title><style>{CSS}
#dframe{{width:100%;border:0;display:block;min-height:600px}}</style></head><body><div class="wrap">
<div class="secttl">1. 대시보드 화면 (전체 현황 및 작업 목록)</div>
<div class="card pad">
 <div class="top"><div class="logo">Aa</div><div><h1>폰트 재현 검수 시스템</h1><div class="small">원본과 재현 이미지를 비교하고, 폰트 일치 여부를 확인하세요 · 내부 연구용 비교 자료 · 썸네일 저작권은 각 채널에</div></div>
  <div class="sp"></div><span class="small">🕒 마지막 업데이트 {E(upd)}</span><button class="btn sm" id="newBtn" style="background:var(--blue);color:#fff;border-color:var(--blue)" data-tip="썸네일 그림을 올리거나 유튜브 주소를 넣어 새로 재현합니다" aria-label="새 영상 등록">+ 신규 영상 등록</button><button class="btn sm" id="edBtn" data-tip="편집기를 새 창으로 엽니다 — 그림 위 글자를 끌어 늘리고 테두리·그림자·광선 등 효과를 바꿔 원본과 견줌. 각자 컴퓨터 브라우저에서 돌아감" aria-label="편집기를 새 창으로 엽니다">✎ 편집기</button><button class="btn sm" id="guideBtn" data-tip="이 화면에 무엇이 들어 있는지 설명을 열고 닫습니다" aria-label="이 화면에 무엇이 들어 있는지 설명을 열고 닫습니다">작업 가이드 ?</button></div>
 <div id="newBox" class="note" style="margin-top:12px;display:none">
  <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
   <div id="drop" style="flex:1;min-width:260px;border:2px dashed var(--line2);border-radius:10px;padding:18px;text-align:center;cursor:pointer" tabindex="0" aria-label="썸네일 그림을 끌어 놓거나 눌러서 고르기">썸네일 그림을 여기에 끌어 놓거나 <b>눌러서 고르기</b> (jpg·png·webp)<input type="file" id="upf" accept="image/jpeg,image/png,image/webp" hidden></div>
   <div style="flex:1;min-width:260px"><input class="inp" id="yurl" style="width:100%" placeholder="유튜브 주소(watch?v= · youtu.be/ · shorts/) 또는 영상 번호" aria-label="유튜브 주소"><button class="btn sm" id="ygo" style="margin-top:6px">주소로 시작</button></div>
  </div>
  <div id="newMsg" class="small" style="margin-top:8px"></div>
  <div id="jobList" style="margin-top:8px"></div>
 </div>
 <div id="guide" class="note" style="margin-top:12px;display:none">최종 결과 {n}편입니다. 카드를 누르면 아래에 그 영상의 비교 화면이 열립니다. 「일치」는 모든 잰 값이 원본과 100% 같을 때만 붙습니다.</div>
 <div class="stats">
  {stat("▶", "var(--bluel)", "var(--blue)", "전체 영상", f"{n}개")}{stat("⟳", "var(--bluel)", "var(--blue)", "진행 중", "0개")}{stat("◷", "#EEF1F6", "var(--tx2)", "대기", "0개")}
  {stat("✓", "#E8F7EE", "var(--ok)", "폰트 일치", f"{nm}개")}{stat("?", "#FEF3DC", "var(--warn)", "폰트 미확인", f"{n - nm}개")}{stat("%", "var(--bluel)", "var(--blue)", "전체 통과율", f"{round(100 * nm / n)}%")}
 </div>
 <div class="filters">
  <button class="chip on" data-st="all" data-tip="거르기를 모두 풀고 모든 영상을 보입니다" aria-label="거르기를 모두 풀고 모든 영상을 보입니다">전체 ({n})</button><span class="vsep"></span>
  {chip("쇼츠")}{chip("롱폼")}<span class="vsep"></span>
  <label class="tog" data-tip="원본과 일치하지 않는 영상만 보입니다">불일치만 보기 <input type="checkbox" id="fBad" aria-label="원본과 일치하지 않는 영상만 보입니다"></label>
  <span class="search" data-tip="영상 제목으로 찾습니다(글자를 치는 대로 바로 걸러짐)"><input class="inp" style="width:100%" id="q" aria-label="영상 제목으로 찾습니다(글자를 치는 대로 바로 걸러짐)" placeholder="🔍 영상 제목을 검색하세요..."></span>
 </div>
 <div class="grid">{"".join(cards)}</div>
 <div id="emptyF" class="empty" style="display:none">조건에 맞는 영상이 없습니다.</div>
</div>
<div class="secttl" style="margin-top:24px" id="detail">2. 상세 검수 화면 (비교 및 분석) <button class="btn sm" id="edCur" data-tip="지금 고른 영상을 편집기 새 창으로 엽니다" aria-label="지금 고른 영상을 편집기 새 창으로 엽니다">✎ 이 영상 편집기로 열기</button></div>
<iframe id="dframe" title="고른 영상의 상세 비교 화면"></iframe>
</div>
<script>const PAGES={pages};const VIDS={vids};{JS}</script></body></html>'''


if __name__ == "__main__":
    R = sys.argv[1]; ROOT = R
    a = sys.argv[2:]
    items = [info(R, a[i], a[i + 1], a[i + 2]) for i in range(0, len(a), 3)]
    # 편집기: tools/tt_editor.html 을 같은 폴더에 편집기.html 로 두고, 이 폴더 값/·그림/ 의 영상 목록을 편집기_목록.json 으로
    #   (공유 주소에서는 서버가 없어 목록을 이 파일로 읽음 — 편집·그리기는 보는 사람 컴퓨터 브라우저에서 함)
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_editor.html"), os.path.join(R, "편집기.html"))
    try:
        L = json.load(open(os.path.join(os.path.dirname(R.rstrip("/\\")), "영상목록.json"), encoding="utf-8")); L = L.get("vids", L) if isinstance(L, dict) else L
        tl = {x.get("id"): x.get("t", "") for x in L}
    except Exception:
        tl = {}
    ids = sorted(os.path.basename(f)[:11] for f in glob.glob(os.path.join(R, "값", "*.json")) if len(os.path.basename(f)) == 16)
    ids = [v for v in ids if os.path.exists(os.path.join(R, "그림", f"{v}_원본.png"))]
    json.dump([dict(id=v, title=tl.get(v, v)) for v in ids], open(os.path.join(R, "편집기_목록.json"), "w", encoding="utf-8"), ensure_ascii=False)
    p = os.path.join(R, "최종.html")
    open(p, "w", encoding="utf-8").write(build(items))
    print("만듦:", p)
