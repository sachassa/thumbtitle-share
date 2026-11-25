# tt_compare_html3 — tt_typo3 결과로 비교 HTML 3판(INFO-20261124-006, OP-20261124-024).
#   python -I -X utf8 tt_compare_html3.py <결과 폴더> [--only id,id] [--name 한장.html] [--meta 영상표.json]
# 원본에서 뽑은 격자 선(줄 위·아래·기준선, 글자 왼·오른 끝)을 원본·재현 둘 다 같은 자리에 그린다. 조금이라도(0.01px라도) 어긋난 선은 빨강 — 허용 범위 없음.
# 장마다 맨 위: 원본 크기·배율·잰 단위, 선 최대 어긋남 px, 색 차이, 판정. 내부용(남의 썸네일).
import glob, html, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_status as TS
import tt_overview_html as OVW
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tt_typo3 import PASS_PX, GLYPH_PASS

OUT = sys.argv[1]
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
ONLY = arg("--only"); NAME = arg("--name", "비교.html")
META = {r["id"]: r for r in json.load(open(arg("--meta"), encoding="utf-8"))} if arg("--meta") else {}
e = lambda s: html.escape(str(s if s is not None else ""))
def cls(d): return "ok" if d == 0 else "bad"
def sw(h): return f'<span class="sw" style="background:{e(h)}"></span>{e(h)}' if h else "—"

vals = []
for p in sorted(glob.glob(os.path.join(OUT, "값", "*.json"))):
    if os.path.basename(p) in ("눈확인.json", "글자고르기.json") or os.path.basename(p).startswith("_") or p.endswith("_실측.json") or p.endswith("_검수.json"): continue
    v = json.load(open(p, encoding="utf-8"))
    if not isinstance(v, dict) or "video_id" not in v or "canvas" not in v: continue   # 재현 결과가 아닌 값 파일(정밀·편집·맞춤 등)은 건너뜀(2026-11-25 입구 시험에서 오류로 멈춤, 실측)
    if ONLY and v["video_id"] not in ONLY.split(","): continue
    vals.append(v)
npass = 0   # 아래에서 장마다 「똑같음」 판정으로 셈
# 눈으로 본 것(Claude가 원본·재현을 직접 보고 적음, DEC-20261124-007) — 값/눈확인.json {영상 id: 한 줄}
EYE = json.load(open(os.path.join(OUT, "값", "눈확인.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "값", "눈확인.json")) else {}

secs = []; pend = []
for v in vals:
    vid = v["video_id"]; W, H = v["canvas"]; m = META.get(vid, {})
    # 선 그림(그림 좌표)
    gl = []
    by_line = {}
    for d in v["grid"]: by_line.setdefault(d["line"], []).append(d)
    for li, ds in by_line.items():
        xs = [d["o"] for d in ds if d.get("axis") == "x"]; ys = [d["o"] for d in ds if d.get("axis") == "y"]
        x0, x1 = (min(xs) - 6, max(xs) + 6) if xs else (0, W); y0, y1 = (min(ys) - 6, max(ys) + 6) if ys else (0, H)
        for d in ds:
            c = "touch" if d.get("touch") else ("ok" if d["d"] == 0 else "bad")
            if d["kind"] == "줄":   # 가로선은 그림 끝에서 끝까지(일직선으로 대 보기)
                gl.append(f'<line class="{c}" x1="0" y1="{d["o"]}" x2="{W}" y2="{d["o"]}"><title>{e(d["name"])} 원본 {d["o"]} · 재현 {d["r"]} · 차이 {d["d"]:+}</title></line>')
            elif d.get("axis") == "x":
                gl.append(f'<line class="{c}" x1="{d["o"]}" y1="{y0}" x2="{d["o"]}" y2="{y1}"><title>{e(d["name"])} 원본 {d["o"]} · 재현 {d["r"]} · 차이 {d["d"]:+}</title></line>')
    # 원본 그림에는 한 색(노랑)으로, 재현·겹쳐 보기에는 같은 자리 선을 맞음(하늘)·어긋남(빨강)으로 그린다
    gsvg_src = f'<svg class="guide src" viewBox="0 0 {W} {H}" preserveAspectRatio="none">{"".join(gl)}</svg>'
    gsvg = f'<svg class="guide" viewBox="0 0 {W} {H}" preserveAspectRatio="none">{"".join(gl)}</svg>'
    # 글자 줄 부분만 잘라 크게(운영자 2026-11-24 「썸네일이 커서 겹치기를 못 봄」): 줄 위·아래 끝에서 줄 높이 0.4배씩 더
    ys_ = [d["o"] for d in v["grid"] if d["kind"] == "줄"]
    pad = 0.4 * (max(ys_) - min(ys_)) / max(1, len(by_line)) if ys_ else 0
    cy0 = max(0, int(min(ys_) - pad)) if ys_ else 0; cy1 = min(H, int(max(ys_) + pad)) if ys_ else H; ch_ = max(1, cy1 - cy0)
    def strip(inner):
        return (f'<div class="pic" style="aspect-ratio:{W}/{ch_}"><div class="in" style="top:{-cy0 / ch_ * 100:.4f}%;height:{H / ch_ * 100:.4f}%">{inner}</div></div>')
    def fig(src, cap, extra="", base=False):
        return f'<figure><figcaption>{cap}</figcaption>{strip(f"""<img src="{src}">{extra}{gsvg_src if base else gsvg}""")}</figure>'
    # 장마다 문서 틀(운영자 요청 2026-11-24 「템플릿 정해서 칸 만들고 정리된 문서 형태로」):
    #   ① 요약 표(결과·글꼴·자리·모양·색·눈으로 본 것) ② 줄마다 표(글자·글꼴 찾음·글꼴 이름·크기·색·테두리·굵기·기울기·가로 비율·자간·모양 맞음·자리 어긋남) ③ 그림 셋
    def yn(ok, a="맞음", b="다름"): return f'<b class="ok">{a}</b>' if ok else f'<b class="bad">{b}</b>'
    gls = v.get("glyphs", []); gmin = min((g_["iou"] for g_ in gls), default=0)
    nf = sum(1 for l in v["lines"] if l["font"].get("confirmed")); nl = len(v["lines"])
    mxp = v["lines_max_px"]; cov = v.get("color_over_noise", 99)
    worst = [g_ for g_ in gls if g_["iou"] < GLYPH_PASS]
    eye = EYE.get(vid, "아직 안 봄")
    # 통과 = 모든 실측 항목이 똑같고(일치), 자리 0px, 모양 1.00, 색 같음, 글꼴 모두 찾음, 읽기 맞음
    _mp = os.path.join(OUT, "값", f"{vid}_실측.json")
    _ms = json.load(open(_mp, encoding="utf-8"))["lines"] if os.path.exists(_mp) else None
    _vp = os.path.join(OUT, "값", f"{vid}_검수.json")
    _vr = json.load(open(_vp, encoding="utf-8")) if os.path.exists(_vp) else None
    STRICT = bool(_vr) and bool(_vr.get("all_ok")) and bool(_ms) and all(x.get("ok") is not False for row in _ms for x in row.values()) and mxp == 0 and gmin >= 1.0 and nf == nl and v.get("read_ok")              and all(c_["o"].upper() == c_["r"].upper() for c_ in v.get("colors", []))
    # 안 된 사유(운영자 2026-11-24 「일치 안 되면 안 된 사유 칸 추가해서 기입해」) — 사실은 그대로, 짐작은 「(추정)」
    notf = [(i_, l_) for i_, l_ in enumerate(v["lines"]) if not l_["font"].get("confirmed")]
    def lf(i_): return v["lines"][i_]["font"]
    def font_cause(i_): return "" if lf(i_).get("confirmed") else f'{i_+1}줄 글꼴 못 찾음 → 다른 글꼴({lf(i_)["best"]})로 그려서'
    r_font = "<br>".join(f'{i_+1}줄 「{e(l_["text"])}」: {e(l_["font"].get("why") or "")} — 1등 {e(l_["font"]["best"])} 평균 {l_["font"].get("score")}·최소 {l_["font"].get("gmin")}' for i_, l_ in notf)
    badg = sorted([d for d in v["grid"] if d.get("d") and not d.get("touch")], key=lambda d: -abs(d["d"]))
    def by_line(items, fmt):
        out = []
        for li in sorted({x["line"] for x in items}):
            xs = [x for x in items if x["line"] == li]
            out.append(f'{li+1}줄: {fmt(xs)} — ' + (e(font_cause(li)) or "글꼴은 찾았으나 맞추기가 끝까지 못 감"))
        return "<br>".join(out)
    r_pos = by_line(badg, lambda xs: f'{len(xs)}곳 어긋남(가장 큰 곳 {e(xs[0]["name"].split(" ", 1)[-1])} {xs[0]["d"]:+}px)')
    r_shape = by_line(sorted(worst, key=lambda g_: g_["iou"]), lambda xs: f'{len(xs)}자 덜 맞음(가장 낮은 「{e(xs[0]["ch"])}」 {xs[0]["iou"]:.2f})')
    badc = [c_ for c_ in v.get("colors", []) if c_["o"].upper() != c_["r"].upper()]
    r_col = ("<br>".join(f'{e(c_["what"])}: {sw(c_["o"])} → {sw(c_["r"])} (ΔE {c_["dE"]})' for c_ in badc) + '<br><small>색 맞추기를 되풀이해도 같은 #RRGGBB에 못 닿음(추정: 원본 JPEG 얼룩으로 대표색이 흔들림)</small>') if badc else ''
    r_read = "<br>".join(f'「{e(x["text"])}」에서 다른 출처로 확인 못 한 글자: {e(x["unconfirmed"])}' for x in v.get("reads", []) if x.get("unconfirmed"))
    _ms_bad = sum(1 for row in (_ms or []) for x in row.values() if x.get("ok") is False)
    r_all = " · ".join(n for n, r in zip(["글꼴 못 찾음", "자리", "모양", "색", "읽기"], [r_font, r_pos if mxp else "", r_shape if worst else "", r_col, r_read]) if r)
    if _ms_bad: r_all += (" · " if r_all else "") + f"실측 {_ms_bad}개 다름(아래 표)"
    if _vr and _vr.get("floor"): r_all = (f'판정 {_vr["floor"]["판정"]}: {_vr["floor"]["까닭"]}' + (" · " if r_all else "") + r_all)   # docs/검수기준.md
    if _vr and not _vr.get("all_ok"): r_all += (" · " if r_all else "") + f'독립 검수 {_vr["n_items"]}개 중 {_vr["n_diff"]}개 다름(아래 표)'
    if not _vr: r_all += (" · " if r_all else "") + "독립 검수 아직 안 함"
    def srow(th, okv, txt, why): return f'<tr><th>{th}</th><td>{okv}{txt}</td><td class="why">{why}</td></tr>'
    summ = ('<table class="sum"><tr><th>항목</th><th>결과</th><th>안 된 사유</th></tr>'
            + srow("결과", yn(STRICT, "통과", "못 통과"), "", "" if STRICT else r_all)
            + srow("글꼴 찾음", yn(nf == nl, f"{nl}줄 모두 찾음", f"{nl}줄 중 {nf}줄 찾음"), "", r_font)
            + srow("글자 자리", yn(mxp == 0), f' — 가장 많이 어긋난 곳 {mxp}px <small>(0px이어야 맞음, 0.01px까지 잼)</small>', r_pos if mxp else "")
            + srow("글자 모양", yn(gmin >= 1.0), f' — 가장 덜 맞는 글자 {min(gls, key=lambda g_: g_["iou"])["ch"] if gls else "—"} {gmin:.2f} <small>(1.00이어야 맞음)</small>{" · 덜 맞는 글자 " + str(len(worst)) + "개" if worst else ""}', r_shape if worst else "")
            + srow("글자 색", yn(not badc), f' — 가장 큰 색 차이 ΔE {v["color_max_dE"]} <small>(#RRGGBB가 같아야 맞음)</small>', r_col)
            + srow("글자 읽기", yn(v.get("read_ok", False), "맞음", "확인 못 한 글자 있음"), "", r_read)
            + f'<tr><th>눈으로 본 것</th><td colspan="2">{e(eye)}</td></tr></table>')
    def lwhy(i, l, lg, lgm, lmx):
        w = []
        if not l["font"].get("confirmed"): w.append(f'글꼴 못 찾음: {e(l["font"].get("why") or "")}')
        if lgm < 1.0: w.append("모양 덜 맞는 글자 " + ", ".join(f'「{e(g_["ch"])}」{g_["iou"]:.2f}' for g_ in sorted(lg, key=lambda g_: g_["iou"])[:4] if g_["iou"] < 1.0))
        if lmx: w.append(f'자리 최대 {lmx}px 어긋남' + (" (글꼴이 달라서)" if not l["font"].get("confirmed") else " (글꼴은 찾았으나 맞추기가 0px까지 못 감)"))
        ux = next((x["unconfirmed"] for x in v.get("reads", []) if x["text"] == l["text"] and x.get("unconfirmed")), "")
        if ux: w.append(f'확인 못 한 글자 「{e(ux)}」')
        return "<br>".join(w)
    rows = ""
    for i, l in enumerate(v["lines"]):
        f = l["font"]; lg = [g_ for g_ in gls if g_["line"] == i]
        lgm = min((g_["iou"] for g_ in lg), default=0)
        lmx = max((abs(d["d"]) for d in v["grid"] if d["line"] == i and not d.get("touch")), default=0)
        cols_ = " ".join(sw(s_["color"]) + (f' <small>그라데이션 {e(s_["grad"]["start"])}→{e(s_["grad"]["end"])}</small>' if s_.get("grad") else "") for s_ in l.get("spans", []))
        ol = f'{l["outline_px"]}px {sw(l["outline_color"])}' if l.get("outline_px") else "없음"
        sl = l.get("slant"); slt = "—" if sl is None else ("없음" if abs(sl) < 0.02 else f'{round(abs(sl) * 100)}% {"오른쪽" if sl > 0 else "왼쪽"}으로')
        wr = l.get("width_ratio"); wrt = "—" if wr is None else f'{round(wr * 100)}%'
        sp = l.get("spacing_px"); spt = "—" if sp is None else f'{sp:+.1f}px'
        rows += (f'<tr><td>{i+1}</td><td class="big">{e(l["text"])}</td><td>{yn(f.get("confirmed"), "찾음", "못 찾음")}</td>'
                 f'<td>{e(f["best"])}{"" if f.get("confirmed") else " <small>(가장 가까운 것)</small>"}</td>'
                 f'<td>{l["size_px"]:.0f}px</td><td>{cols_}</td><td>{ol}</td><td>{l["bold_px"]:.1f}px</td><td>{slt}</td><td>{wrt}</td><td>{spt}</td>'
                 f'<td class="{"ok" if lgm >= 1.0 else "bad"}">{lgm:.2f}</td><td class="{"ok" if lmx == 0 else "bad"}">{lmx}px</td><td class="why">{lwhy(i, l, lg, lgm, lmx)}</td></tr>')
    ltab = ('<table class="lines"><tr><th>줄</th><th>글자</th><th>글꼴</th><th>글꼴 이름</th><th>크기</th><th>글자 색</th><th>테두리</th><th>덧댄 굵기</th><th>기울기</th><th>가로 비율</th><th>자간</th>'
            '<th>모양 맞음<br><small>가장 낮은 글자, 1.00이어야</small></th><th>자리 어긋남<br><small>0px이어야</small></th><th>안 된 사유</th></tr>' + rows + '</table>')
    # 실측 견주기 표: 원본·재현을 같은 방법으로 직접 잰 값(값/<id>_실측.json, tt_measure_cmp.py) — 줄마다 원본 | 재현 | 차이 | 일치
    mp = os.path.join(OUT, "값", f"{vid}_실측.json")
    MS = json.load(open(mp, encoding="utf-8"))["lines"] if os.path.exists(mp) else []
    for c_ in v.get("colors", []):   # 색 묶음마다(한 줄에 두 색이면 따로)
        if c_["line"] < len(MS):
            MS[c_["line"]]["글자 색 " + c_["what"].split(" ", 2)[-1].replace("채움 ", "")] = dict(o=c_["o"], r=c_["r"], d=c_["dE"], ok=(c_["o"].upper() == c_["r"].upper()), unit="ΔE")
    def mwhy(li, k, x):
        if x is None or x.get("ok") is not False: return ""
        fc = (f'{li+1}줄 글꼴 못 찾음 → 다른 글꼴({e(lf(li)["best"])})로 그림' if li < len(v["lines"]) and not lf(li).get("confirmed") else "")
        if "색" in k: return "대표색 #RRGGBB가 다름 — 색 맞추기로 같은 값에 못 닿음" + (f"; {fc}(획 모양이 달라 섞이는 화소가 다름, 추정)" if fc else "")
        if "기울기" in k: return fc or "기울기 맞추기가 같은 값까지 못 감"
        if "테두리" in k: return fc or "테두리 굵기 맞추기가 같은 값까지 못 감"
        return fc or "글꼴은 찾았으나 크기·자간·자리 맞추기가 0.01px까지 못 감"
    def cell(x, k, li=0):
        if x is None: return '<td></td><td></td><td></td><td></td><td></td>'
        fo = lambda z: (sw(z) if isinstance(z, str) and z.startswith("#") else ("—" if z is None else e(z)))
        dd = "—" if x.get("d") is None else (f'{x["d"]:+}' if isinstance(x["d"], (int, float)) and x.get("unit") != "ΔE" else f'{x["d"]}')
        ok = x.get("ok"); oks = "—" if ok is None else ('<b class="ok">일치</b>' if ok else '<b class="bad">다름</b>')
        return f'<td>{fo(x.get("o"))}</td><td>{fo(x.get("r"))}</td><td>{dd} <small>{e(x.get("unit", ""))}</small></td><td>{oks}</td><td class="why">{mwhy(li, k, x)}</td>'
    mtab = ""
    if MS:
        keys = list(dict.fromkeys(k for row in MS for k in row))
        hd = "".join(f'<th colspan="5">{i+1}줄 「{e(v["lines"][i]["text"])}」</th>' for i in range(len(MS)))
        hd2 = "".join('<th>원본</th><th>재현</th><th>차이</th><th>일치</th><th>안 된 사유</th>' for _ in MS)
        body = "".join(f'<tr><th>{e(k)}</th>' + "".join(cell(row.get(k), k, li) for li, row in enumerate(MS)) + '</tr>' for k in keys)
        nd = sum(1 for row in MS for x in row.values() if x.get("ok") is False); nt = sum(1 for row in MS for x in row.values() if x.get("ok") is not None)
        mtab = (f'<h3>원본·재현 실측 견주기 — {nt}개 중 <span class="{"ok" if nd == 0 else "bad"}">{nd}개 다름</span> '
                '<small>(두 그림을 같은 방법으로 직접 잼 · <b>값이 똑같을 때만 일치</b>: 길이·굵기·기울기는 소수 둘째 자리까지, 색은 #RRGGBB까지 같아야 함)</small></h3>'
                f'<table class="ms"><tr><th rowspan="2">항목</th>{hd}</tr><tr>{hd2}</tr>{body}</table>')
    # 독립 검수 표(값/<id>_검수.json, tools/tt_verify.py — 만든 쪽 코드·값을 보지 않고 원본·완성 그림을 같은 방법으로 잰 값). HTML의 판정은 이것으로 한다.
    vp = os.path.join(OUT, "값", f"{vid}_검수.json")
    VR = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else None
    vtab = '<h3 class="bad">독립 검수 결과 없음 — 판정 못 함</h3>'
    if VR:
        VL = []
        for vl in VR["lines"]:
            row = {k: dict(o=x.get("o"), r=x.get("r"), d=x.get("d"), ok=x.get("ok"), unit="ΔE" if isinstance(x.get("o"), str) and str(x.get("o")).startswith("#") else "") for k, x in vl["items"].items()}
            gs_ = vl.get("glyphs", [])
            if gs_:
                wg = min(gs_, key=lambda g_: g_["f1"])
                row["글자 겹침 F1(가장 낮은 글자)"] = dict(o=1.0, r=round(wg["f1"], 3), d=round(wg["f1"] - 1.0, 3), ok=all(g_["ok"] for g_ in gs_), unit=f'「{wg["ch"]}」 · {sum(1 for g_ in gs_ if not g_["ok"])}/{len(gs_)}자 다름')
            VL.append(row)
        vkeys = list(dict.fromkeys(k for row in VL for k in row))
        vhd = "".join(f'<th colspan="5">{i+1}줄 「{e(VR["lines"][i]["text"])}」</th>' for i in range(len(VL)))
        vhd2 = "".join('<th>원본</th><th>재현</th><th>차이</th><th>일치</th><th>안 된 사유</th>' for _ in VL)
        vbody = "".join(f'<tr><th>{e(k)}</th>' + "".join(cell(row.get(k), k, li) for li, row in enumerate(VL)) + '</tr>' for k in vkeys)
        pdis = VR.get("producer_disagree", [])
        said_same = [x for x in pdis if x.get("kind") == "said_same_but_differs" or "ok" in str(x.get("what", "")).lower()]
        vtab = (f'<h3>독립 검수(서브에이전트 도구, 만든 쪽 코드·값 안 봄) — {VR["n_items"]}개 중 <span class="{"ok" if VR["n_diff"] == 0 else "bad"}">{VR["n_diff"]}개 다름</span>'
                f' · 만든 쪽이 적은 값과 검수 값이 다른 곳 {len(pdis)}건 <small>(판정은 이 표로 함 · 값이 똑같을 때만 일치)</small></h3>'
                f'<details open><summary>검수 표 펼치기/접기</summary><table class="ms"><tr><th rowspan="2">항목</th>{vhd}</tr><tr>{vhd2}</tr>{vbody}</table></details>')
    ov = ('<figure><figcaption>겹쳐 보기 — 재현 투명도 <input type="range" min="0" max="100" value="50" oninput="this.closest(&quot;figure&quot;).querySelector(&quot;.top&quot;).style.opacity=this.value/100;this.nextElementSibling.textContent=this.value"> <span>50</span>%</figcaption>'
          + strip(f'<img src="그림/{vid}_원본.png"><img class="top" src="그림/{vid}_재현.png" style="opacity:.5">{gsvg}') + '</figure>')
    npass += bool(STRICT or (_vr and _vr.get("match")))
    # 완료(100% 일치)가 아닌 장은 화면에 내지 않는다(운영자 2026-11-24 「다 안 끝난 거면 그냥 안 보이게 해, 헷갈리잖아」) — 상태 줄만
    if TS.status(OUT, vid)["state"] != "완료" and not os.environ.get("TT_SHOW_ALL"):   # 할 일 다 안 한 것은 목록으로만(운영자 2026-11-24)
        continue
    secs.append(f'''<section id="{e(vid)}"><h2>{e(m.get("title") or vid)} <small><a href="https://www.youtube.com/watch?v={e(vid)}" target="_blank">{e(vid)}</a></small></h2>
<div class="doc">{summ}{ltab}</div>{vtab}<details><summary>만든 쪽이 스스로 잰 값(견주기용, 판정에 안 씀)</summary>{mtab}</details>
<div class="four">{fig(f"그림/{vid}_원본.png", f'원본 — <a href="그림/{vid}_원본.png" target="_blank">썸네일 전체</a>', base=True)}{fig(f"그림/{vid}_재현.png", f'재현 — <a href="그림/{vid}_재현.png" target="_blank">썸네일 전체</a>')}{fig(f"그림/{vid}_재현_JPEG.png", '참고 — 재현을 원본과 같은 JPEG로 저장해 본 것(판정에는 안 씀, 색 번짐 견주기용)') if os.path.exists(os.path.join(OUT, "그림", f"{vid}_재현_JPEG.png")) else ""}{ov}{fig(f"그림/{vid}_색겹침.png", '색으로 겹침 — <b style="color:#f0f">자홍</b> 원본에만 · <b style="color:#0a0">초록</b> 재현에만 · 흰색 둘 다 · 테두리 <b style="color:#f80">주황</b> 원본에만 · <b style="color:#05f">파랑</b> 재현에만 · 회색 둘 다') if os.path.exists(os.path.join(OUT, "그림", f"{vid}_색겹침.png")) else ""}</div></section>''')

_tt = lambda v: (META.get(v) or {}).get("title") or v
n_ov, OV_HTML = OVW.overview_block(OUT, [v_["video_id"] for v_ in vals], _tt)
page = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>타이틀 재현 3판</title><style>{OVW.CSS}
body{{font-family:"Malgun Gothic",sans-serif;margin:0;background:#f4f4f4;color:#222;font-size:14px;--w:900px}} header{{background:#fff;border-bottom:1px solid #ddd;padding:8px 16px;position:sticky;top:0;z-index:5}}
h1{{font-size:17px;margin:0 0 4px}} h2{{font-size:15px;margin:0 0 4px}} .meta{{color:#555;margin:2px 0 6px}} .fl{{margin:4px 0;padding-left:18px}}
main{{padding:12px 16px}} section{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;margin-bottom:16px}}
.four{{display:flex;flex-direction:column;gap:8px}} figure{{margin:0}} figcaption{{font-size:12px;color:#555;height:24px;line-height:24px}} figcaption input{{width:120px;vertical-align:middle}}
.pic{{position:relative;width:var(--w);border:1px solid #ccc;overflow:hidden}} .pic .in{{position:absolute;left:0;width:100%}} .pic img{{width:100%;height:100%;display:block}} .pic .top{{position:absolute;left:0;top:0}}
.guide{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}} body.nogrid .guide{{display:none}}
.guide line{{stroke-width:1;vector-effect:non-scaling-stroke}} .guide line.ok{{stroke:#00e5ff}} .guide line.touch{{stroke:#bbb;stroke-dasharray:4 3}} .guide.src line{{stroke:#ffd400 !important;stroke-width:1 !important}} .guide line.bad{{stroke:#ff1744;stroke-width:2}}
.ok{{color:#047857}} .doc{{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin:6px 0 10px}} table{{border-collapse:collapse}} td,th{{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:middle}} th{{background:#f3f4f6;white-space:nowrap}} .sum th{{width:90px}} .ms td,.ms th{{font-size:13px;padding:3px 6px}} .ms tr th:first-child{{text-align:left}} h3{{font-size:14px;margin:10px 0 4px}} .lines td{{white-space:nowrap}} .lines td.big{{font-size:16px;font-weight:bold}} .sw{{display:inline-block;width:12px;height:12px;border:1px solid #999;vertical-align:middle;margin-right:3px}} .bad{{color:#b91c1c}} td.why{{font-size:12px;color:#7f1d1d;white-space:normal;min-width:200px;max-width:520px}} .sum td.why{{min-width:420px}} .bar label{{margin-right:14px}} .bar input[type=range]{{width:220px;vertical-align:middle}} small{{color:#666}}
</style></head><body><header><h1>썸네일 속 타이틀 재현 — 완료 {n_ov}편 (그중 일치 {npass}편 — 100% 또는 JPEG 바닥) / 전체 {len(vals)}편 <small>({datetime.now():%m-%d %H:%M} · 내부용)</small></h1>
<div class="bar"><label><input type="checkbox" id="g" checked> 격자 선</label>
<label>보기 크기 <select id="z"><option value="600">작게</option><option value="900" selected>보통</option><option value="1080">원본 크기(1:1)</option><option value="1600">크게</option></select></label></div>
<small>선: 원본 글자 끝 자리를 원본(노랑)·재현에 같은 자리로 그음 — 하늘 = 똑같음(0px), 빨강 = 조금이라도 어긋남, 회색 점선 = 옆 글자와 붙어 잴 수 없음</small><div>{OVW.CONTROLS}</div></header>{TS.list_html(OUT, _tt, e)}<main>{OV_HTML}{"<h2 style='margin:16px 0 8px'>영상별 자세한 표</h2>" if secs else ""}{"".join(secs) or "<p><b>아직 할 일을 다 마친 영상이 없습니다.</b> 재현·독립 검수·색 겹침·Claude 눈 확인을 다 마친 영상만 나옵니다(일치 안 됨도 나옴).</p>"}</main>
<script>const b=document.body;document.getElementById('g').onchange=e=>b.classList.toggle('nogrid',!e.target.checked);document.getElementById('z').onchange=e=>b.style.setProperty('--w',e.target.value+'px');</script></body></html>'''
open(os.path.join(OUT, NAME), "w", encoding="utf-8").write(page)
print(f"{NAME} — {len(vals)}장 · 통과 {npass}")
