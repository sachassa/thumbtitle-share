# tt_overview_html — 재현 결과 여러 장을 한 화면에 겹쳐 보는 칸(운영자 2026-11-24 「여러 개를 한 번에 겹쳐서 확인 못 해?」).
# 운영자 2026-11-24 「html 하나로 합쳐」 → 따로 쪽을 만들지 않고 비교.html 맨 위에 들어간다(tt_compare_html3 가 overview_block 을 부름).
#   python -I -X utf8 tt_overview_html.py <결과 폴더>  → 한눈에.html 은 비교.html 로 넘겨주는 쪽만 남김(옛 주소용)
# 장마다 원본 위에 재현을 겹치고, 장마다 따로 움직이는 투명도 막대. 할 일을 다 마친 영상(tt_status 「완료」)만 나온다.
import json, os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_status as TS

CSS = """
.ov{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;margin-bottom:16px}
.ov .card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:6px} .ov .card.tall{width:260px} .ov .card.wide{width:460px}
.ov .hd{min-height:44px;line-height:1.35;font-size:13px} .ov .hd a{color:#111;font-weight:bold;text-decoration:none}
.ov .opic{position:relative;width:100%;overflow:hidden;border:1px solid #ccc} .ov .opic img{position:absolute;inset:0;width:100%;height:100%}
.ov .ctl{margin-top:4px;font-size:12px} .ov .ctl input[type=range]{width:110px;vertical-align:middle} .ov .ctl button{font-size:12px;margin-left:4px}
.ov .opic .col{display:none} .ov .card.showcol .opic .col, body.allcol .ov .opic .col{display:block}
body.big .ov .card.tall{width:400px} body.big .ov .card.wide{width:700px}
.ov .okc{color:#047857} .ov .badc{color:#b91c1c}
"""

CONTROLS = ('<label><input type="checkbox" onchange="document.body.classList.toggle(\'big\',this.checked)"> 겹쳐 보기 크게</label> '
            '<label><input type="checkbox" onchange="document.body.classList.toggle(\'allcol\',this.checked)"> 모두 색으로 겹침</label> '
            '<small>색으로 겹침: <b style="color:#f0f">자홍</b> = 원본에만 있는 글자 화소 · <b style="color:#0a0">초록</b> = 재현에만 · 흰색 = 둘 다 · '
            '테두리 <b style="color:#f80">주황</b> = 원본에만 · <b style="color:#05f">파랑</b> = 재현에만 · 회색 = 둘 다</small>')


def overview_block(OUT, vids, title_of):
    """할 일을 다 마친 영상의 겹쳐 보기 칸들. 제목을 누르면 같은 쪽 아래 그 영상의 자세한 표로 간다."""
    e = lambda s: html.escape(str(s))
    cards = []
    for vid in vids:
        if not os.path.exists(os.path.join(OUT, "그림", f"{vid}_재현.png")): continue
        S_ = TS.status(OUT, vid)
        if S_["state"] != "완료" and not os.environ.get("TT_SHOW_ALL"): continue
        v = json.load(open(os.path.join(OUT, "값", f"{vid}.json"), encoding="utf-8"))
        W, H = v.get("canvas", [1080, 1920]); vr = S_.get("vr") or {}
        st = ('<b class="okc">완료 · 100% 일치</b>' if S_["match"] else
              f'<b class="badc">완료 · 일치 안 됨</b> <small>검수 {vr.get("n_items", "?")}개 중 {vr.get("n_diff", "?")}개 다름</small>')
        cards.append(f'''<div class="card {'wide' if W > H else 'tall'}"><div class="hd"><a href="#{e(vid)}">{e(title_of(vid))[:40]}</a><br><small>{"롱폼" if W > H else "쇼츠"}</small> {st}</div>
<div class="opic" style="aspect-ratio:{W}/{H}"><img src="그림/{e(vid)}_원본.png"><img class="top" src="그림/{e(vid)}_재현.png" style="opacity:.5"><img class="col" src="그림/{e(vid)}_색겹침.png" onerror="this.remove()"></div>
<div class="ctl">재현 <input type="range" min="0" max="100" value="50" oninput="this.closest('.card').querySelector('.top').style.opacity=this.value/100;this.nextElementSibling.textContent=this.value"><span>50</span>%
<label><input type="checkbox" onchange="this.closest('.card').classList.toggle('showcol',this.checked)"> 색으로 겹침</label> <button onclick="const t=this.closest('.card').querySelector('.top');const r=this.closest('.card').querySelector('input');if(t._b){{clearInterval(t._b);t._b=null;t.style.opacity=r.value/100;this.textContent='깜빡이기'}}else{{t._b=setInterval(()=>t.style.opacity=t.style.opacity==='1'?'0':'1',500);this.textContent='멈춤'}}">깜빡이기</button></div></div>''')
    return len(cards), ('<h2 style="margin:4px 0 8px">한눈에 겹쳐 보기 — 할 일을 다 마친 영상 ' + str(len(cards)) + '편 <small>(제목을 누르면 아래 자세한 표로)</small></h2><div class="ov">' + "".join(cards) + "</div>") if cards else ""


if __name__ == "__main__":
    OUT = sys.argv[1]
    open(os.path.join(OUT, "한눈에.html"), "w", encoding="utf-8").write(
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=비교.html"><title>비교.html 로 옮김</title></head>'
        '<body>한 화면으로 합쳤습니다 — <a href="비교.html">비교.html</a></body></html>')
    print("한눈에.html → 비교.html 로 넘김")
