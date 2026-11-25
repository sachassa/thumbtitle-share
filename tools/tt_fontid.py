# tt_fontid — 썸네일 타이틀 한 줄의 원본 글꼴을 알아낸다(OP-20261124-027: 글꼴 확정이 첫 관문).
#   ① 후보 = 이 PC 글꼴 + 받은 무료 글꼴 + 눈누 글꼴 전부(tt_config.FONT_POOL, _cmap.json으로 그 줄 글자가 다 있는 것만)
#   ② 모두를 같은 높이·너비로 그려 겹침(IoU) → 위 15개
#   ③ 위 15개는 줄 하나에 한 벌(크기·자간·가로 비율·굵기·자리) 맞추고, 글자마다 위치만(늘리지 않음) 다듬은 뒤
#      글자마다 모양 겹침(봐주기 없는 F1 = 2·겹친 화소/(원본+재현 화소))을 잰다
#   ④ 확정 = 모든 글자 0.95 이상 + 2등(다른 가족) 평균보다 0.02 넘게 높음. 못 넘으면 「글꼴 못 찾음」
# 메모리: 글꼴을 하나씩 열고 재면 바로 닫는다(한 번에 천여 개를 열지 않음).
import base64, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_typo2 as T2
from tt_typo import np, cv2

POOL = T2.T.CFG.FONT_POOL
CONFIRM_GLYPH = 1.0; CONFIRM_GAP = 0.02   # 글꼴 찾음 = 글자마다 원본과 1.00(운영자 2026-11-24 「느슨한 기준이 어딨어? 100% 일치」) — 전에는 0.95
NEAR_GLYPH = 0.95   # 이보다 낮으면 추천(대체) 글꼴을 더 넓게 찾는다
HS_TRY = (0.7, 0.8, 0.9, 1.0, 1.15, 1.3)

_NAMES = None
def aliases(path):
    """글꼴 파일의 이름표에 적힌 모든 이름(한글·영문). 파일: <글꼴 폴더>/_이름.json(tt_fontnames.py)."""
    global _NAMES
    if _NAMES is None:
        np_ = os.path.join(POOL, "_이름.json")
        _NAMES = json.load(open(np_, encoding="utf-8")) if os.path.exists(np_) else {}
    return _NAMES.get(path, [])

def pool_fonts():
    """(이름, 경로, 굵기) 목록 + 글자 비트표. 기존 후보(58) + 눈누.
    중복 빼기(2026-11-24): 이름·굵기·글자표가 모두 같은 파일은 하나만(.woff2 → .woff → 그 밖 순) — 전에는 약 250개를 두 번씩 그림.
    이름은 이름표의 한글 이름을 먼저 씀(산돌구름 후보 이름과 짝짓기)."""
    out = [(n, p, w, None) for n, p, w in T2.CANDS]
    cm_p = os.path.join(POOL, "_cmap.json")
    cm = json.load(open(cm_p, encoding="utf-8")) if os.path.exists(cm_p) else {}
    rank = lambda p: {".woff2": 0, ".woff": 1}.get(os.path.splitext(p)[1].lower(), 2)
    seen = set()
    for p, v in sorted(cm.items(), key=lambda kv: rank(kv[0])):
        if "error" in v: continue
        al = aliases(p); ko = next((n for n in al if any("가" <= ch <= "힣" for ch in n)), None)
        fam = ko or v.get("family") or (al[0] if al else None) or os.path.basename(p)
        st = v.get("style") or ""
        name = fam if (st and fam.lower().endswith(st.lower())) else f'{fam} {st}'.strip()
        key = (name.lower(), v.get("cov"))
        if key in seen: continue
        seen.add(key)
        cov = base64.b64decode(v["cov"])
        if v.get("vf") and v.get("wght"):
            lo, hi = v["wght"][0], v["wght"][-1]
            for w in sorted({max(lo, min(hi, x)) for x in (400, 700, 900)}): out.append((f"{name} {int(w)}", p, int(w), cov))
        else: out.append((name, p, None, cov))
    return out

def covers(cov, chars):
    if cov is None: return True
    return all(ord(ch) < 65536 and (cov[ord(ch) >> 3] >> (ord(ch) & 7)) & 1 for ch in chars if ch != " ")

def glyph_scores(c, chars, F, p):
    """글자마다 모양 겹침(봐주기 없음 — 전에는 1px 봐준 F1, 운영자 2026-11-24 「느슨·오차 범위 있으면 100% 일치로 다 바꿔」)."""
    lay = T2.layout(c, chars, p)
    Rm, idm = T2.raster(lay, F.shape, p["e"], ids=True)
    gF = T2.glyph_assign(F, idm); gR = T2.glyph_assign(Rm, idm)
    sc = []
    for i, ch in enumerate(chars):
        if ch == " ": continue
        a = gF == i; b = gR == i
        if a.sum() < 5 or b.sum() < 5: sc.append((ch, 0.0)); continue
        sc.append((ch, round(T2.f1_exact(a, b), 3)))
    return sc

def best_init(cc, chars, F, sh=0.0):
    best = None
    for hs in HS_TRY:
        p = T2.init_params(cc, chars, F, hs, sh)
        if not p: continue
        sc = T2.score(cc, chars, p, F)
        if best is None or sc > best[0]: best = (sc, p)
    return best[1] if best else T2.init_params(cc, chars, F)

def same_shape(a, b, chars):
    def norm(g):
        m = g > 127; ys, xs = np.nonzero(m)
        if len(xs) == 0: return None
        return cv2.resize(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8) * 255, (96, 96), interpolation=cv2.INTER_AREA) > 127
    v = []
    for ch in {c for c in chars if c.strip()}:
        ga = T2.glyph(a, 200, ch)[0]; gb = T2.glyph(b, 200, ch)[0]
        if ga is None or gb is None: continue
        A, B = norm(ga), norm(gb)
        if A is None or B is None: continue
        v.append(T2.f1_exact(A, B))
    return float(np.mean(v)) if v else 0.0

def family(name):
    return name.split(" ")[0].lower()

_WT = {"thin", "hairline", "extralight", "ultralight", "light", "regular", "normal", "book", "medium", "semibold", "demibold", "bold",
       "extrabold", "ultrabold", "black", "heavy", "extrablack", "ultra", "ttf", "otf", "r", "b", "l", "m", "eb", "el", "sb"}
def weight_family(name):
    """굵기 낱말(숫자·Medium·Bold…)을 뗀 글꼴 이름 — 같은 글꼴의 굵기 파일끼리 묶을 때. 첫 낱말만 보면 「배달의민족 도현」·「배달의민족 주아」가 섞임."""
    return " ".join(w for w in re.split(r"\s+", name.lower()) if w not in _WT and not re.fullmatch(r"\d+", w)).strip()

def prefer_list():
    """HFC(한글 글꼴 분류기, Production) 가 준 이름 → 받아 둔 글꼴 파일. 파일 tt_config.HFC_PREFER(선택) = [{"name":..., "path":..., "wght":...}]"""
    pp = T2.T.CFG.HFC_PREFER
    if not os.path.exists(pp): return []
    return [(f'HFC:{x["name"]}', x["path"], x.get("wght")) for x in json.load(open(pp, encoding="utf-8")) if x.get("path") and os.path.exists(x["path"])]

def fit_fine(cc, chars, F, SH):
    p = best_init(cc, chars, F, SH); s0 = T2.score(cc, chars, p, F)
    p, s, hist, n = T2.optimize(cc, chars, F, p, rounds=40)
    p, s2 = T2.refine_glyphs(cc, chars, F, p)
    p, s3, _, _ = T2.optimize(cc, chars, F, p, rounds=20)
    gs = glyph_scores(cc, chars, F, p); vals = [v for ch_, v in gs if ch_.isalnum()] or [v for _, v in gs]   # 순위는 글자로만(부호 0점이 순위를 망침, 2026-11-25 「배구 일본반응」)
    T2._FC.clear(); T2._GC.clear()
    return dict(c=cc, p=p, iou=round(s3, 3), first=round(s0, 3), glyphs=gs, gmin=min(vals) if vals else 0, gmean=round(float(np.mean(vals)), 3) if vals else 0)

def coarse_key(F, chars):
    import hashlib
    h = hashlib.sha1(np.ascontiguousarray(F).astype(np.uint8).tobytes()); h.update(str(F.shape).encode()); h.update("".join(chars).encode("utf-8"))
    return h.hexdigest()

def coarse_cache_get(F, chars):
    d = os.environ.get("TT_COARSE_DIR")
    if not d: return None
    p = os.path.join(d, coarse_key(F, chars) + ".json")
    if not os.path.exists(p): return None
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return None

def coarse_all(F, chars, cc, SH):
    """대충 겹치기 점수 한 글꼴(가로 비율 여러 가지 중 가장 좋은 것) — identify 와 묶음 계산이 같은 함수를 쓴다."""
    s = 0.0
    for hs in HS_TRY:
        try:
            p = T2.init_params(cc, chars, F, hs, SH)
            if p: s = max(s, T2.score(cc, chars, p, F))
        except Exception: pass
    return s

def identify(chars, F, log=None, top_n=15, prefer=None, mid_n=80, fast=None, extra_n=25, force=None, only=None, ref=None, need=None):
    """fast = 산돌구름 후보 중 이 PC에 있는 글꼴. 이것만 먼저 자세히 맞춰 보고, 1등이 글자마다 1.00이며
    모양이 다른 다른 산돌 후보보다 0.02 넘게 높으면 그대로 확정하고 1,800개 전체 비교를 건너뛴다(시간 줄이기, 운영자 2026-11-24)."""
    t0 = time.time(); text = "".join(chars)
    cands = [c for c in pool_fonts() if covers(c[3], chars)]
    # need = 같은 제목의 다른 줄 글자까지(제목 하나 = 글꼴 하나): 그 글자가 다 있는 글꼴만 후보로. 없으면 다음 줄을 이 글꼴로 못 맞춰
    # 1,600여 개를 다시 뒤짐(2026-11-25 「제이블랙」 편 — 「HFC:배민 도현체」에 「블」·「랙」·영문이 없음, 실측)
    if need and not only:
        c2 = [c for c in cands if covers(c[3], need)]
        if c2:
            if log is not None and len(c2) < len(cands): log.append(f"다른 제목 줄 글자까지 다 있는 글꼴만 후보로: {len(cands)} → {len(c2)}개")
            cands = c2
            okp = {c[1] for c in cands}
            if fast: fast = [c for c in fast if c[1] in okp]
            if prefer is not None: prefer = [c for c in prefer if c[1] in okp]
    SH = T2.slant_of(F)   # 줄 기울기(원본에서 잼) — 모든 후보를 같은 기울기로 그려 비교
    if log is not None and abs(SH) > 0.02: log.append(f"줄 기울기 {SH} (가로 밀림/높이)")
    if only:   # 제목 하나 = 글꼴 하나(운영자 2026-11-24): 같은 제목의 앞 줄 글꼴 하나로만 맞추고(굵기·비율·크기는 효과 값) 전체 비교를 하지 않음
        # 이름 또는 파일로 찾는다 — 같은 파일이 이름 둘로 들어 있음(「HFC:배민 도현체(산돌 1등)」 = 「배달의민족 도현 Regular」 DoHyeon-Regular.ttf).
        # 이름으로만 찾아 둘째 줄이 제목 글꼴을 못 찾고 1,641개를 다시 뒤짐(2026-11-25 「제이블랙」 편, 실측)
        o_name, o_file = only if isinstance(only, tuple) else (only, None)
        oc = next((c for c in cands if c[0] == o_name), None) or next((c for c in cands if o_file and os.path.basename(c[1]) == o_file), None)
        if oc is not None:
            # 같은 글꼴의 다른 굵기 파일도 대 본다(굵기는 효과 값 — 글꼴은 하나). 덧굵기만으로는 가는 줄·굵은 줄을 못 맞춤
            # (2026-11-25 조니 뎁 편: 페이퍼로지 5 Medium으로 맞춘 첫 줄 평균 0.72, 원본은 더 가는 굵기로 보임 — 실측·눈으로 봄)
            wf = weight_family(oc[0]); sib = [c for c in cands if c is not oc and wf and weight_family(c[0]) == wf][:12]
            bs = []
            for cc in [oc] + sib:
                try: bs.append(fit_fine(cc[:3], chars, F, SH))
                except Exception: continue
            bs.sort(key=lambda x: (-x["gmean"], -x["gmin"])); b = bs[0]
            if log is not None and len(bs) > 1: log.append(f"「{text}」 같은 글꼴 굵기 {len(bs)}개 대 봄: " + " · ".join(f"{x['c'][0]} {x['gmean']}" for x in bs[:4]))
            res = dict(same_as=[], rank1={}, rank2={}, confirmed=b["gmin"] >= CONFIRM_GLYPH, best=b, second=None, gap=0.0, tried=len(bs), pool=len(bs),
                       secs=round(time.time() - t0, 1), why=None if b["gmin"] >= CONFIRM_GLYPH else "제목 글꼴 하나로 맞춤 — 글자마다 겹침 1.00 못 됨", fast=True,
                       top=[dict(name=b["c"][0], file=os.path.basename(b["c"][1]), gmean=b["gmean"], gmin=b["gmin"], iou=b["iou"], first=b["first"])])
            if log is not None: log.append(f"글꼴 알아내기 「{text}」: 제목 글꼴 하나({o_name})로만 맞춤({res['secs']}초) → 평균 {b['gmean']}·최소 {b['gmin']}")
            return res
        if log is not None: log.append(f"제목 글꼴 {o_name}에 「{text}」 글자가 다 없어 전체 비교")
    if fast:
        ff = []
        for cc in list(dict.fromkeys(tuple(c[:3]) for c in fast))[:10]:
            try: ff.append(fit_fine(cc, chars, F, SH))
            except Exception: continue
        ff.sort(key=lambda x: (-x["gmean"], -x["gmin"]))
        if ff and ff[0]["gmin"] >= CONFIRM_GLYPH:
            b = ff[0]
            oth = next((f for f in ff[1:] if family(f["c"][0]) != family(b["c"][0]) and same_shape(b["c"], f["c"], chars) < 1.0), None)
            gap = round(b["gmean"] - (oth["gmean"] if oth else 0), 3); gmn = round(b["gmin"] - (oth["gmin"] if oth else 0), 3)
            if oth is None or gap > CONFIRM_GAP or gmn > CONFIRM_GAP:
                res = dict(same_as=[], rank1={}, rank2={}, confirmed=True, best=b, second=oth, gap=gap, tried=len(ff), pool=len(ff), secs=round(time.time() - t0, 1),
                           why=None, fast=True, top=[dict(name=f["c"][0], file=os.path.basename(f["c"][1]), gmean=f["gmean"], gmin=f["gmin"], iou=f["iou"], first=f["first"]) for f in ff])
                if log is not None: log.append(f"글꼴 알아내기 「{text}」: 산돌 후보 {len(ff)}개만 맞춰 확정({res['secs']}초, 전체 비교 건너뜀) → {b['c'][0]} 평균 {b['gmean']}·최소 {b['gmin']}")
                return res
        if log is not None: log.append(f"산돌 후보만으로는 확정 못 함 → 전체 {len(cands)}개 비교")
        prefer = list(prefer or []) + [f["c"] for f in ff]
    # 후보 줄 세우기 = 글자 대 글자 모양(tt_glyphrank, 운영자 2026-11-25 「근데 왜 대충 겹쳐?」): 원본 줄을 글자마다 나눠 잉크 상자로 맞추고
    # 글꼴마다 저장해 둔 같은 글자 모양과 견줌. 전에는 줄 전체를 같은 높이·너비로 대충 겹치고(약 50초) 위 80개를 짧게 맞춤(약 30초) — 실측 2026-11-25
    import tt_glyphrank as GR
    if ref is None:
        _w = T2.fit_line(chars, F, [])[0]; ref = (_w["c"], _w["p"])
    coarse = GR.rank(chars, F, cands, ref, log)
    mid = coarse
    # 분류기가 고른 이름은 대충 점수와 상관없이 반드시 자세히 잰다(맨 앞)
    pref = [tuple(c) for c in (prefer if prefer is not None else prefer_list())]
    if need and not only:
        _okp = {c[1] for c in cands}; pref = [c for c in pref if c[1] in _okp]
    rank1 = {cc[1] + "|" + str(cc[2]): i + 1 for i, (_, cc) in enumerate(coarse)}
    rank2 = {cc[1] + "|" + str(cc[2]): i + 1 for i, (_, cc) in enumerate(mid)}
    picks = [(None, c) for c in pref] + [x for x in mid if tuple(x[1]) not in pref][:top_n]
    fine = []
    for s0, cc in picks:
        if s0 is None:
            try: s0 = T2.score(cc, chars, best_init(cc, chars, F, SH), F)
            except Exception: continue
        try:
            p = best_init(cc, chars, F, SH)
            p, s, hist, n = T2.optimize(cc, chars, F, p, rounds=40)
            p, s2 = T2.refine_glyphs(cc, chars, F, p)          # 글자 위치만(크기·비율은 줄 하나에 한 벌)
            p, s3, _, _ = T2.optimize(cc, chars, F, p, rounds=20)
            gs = glyph_scores(cc, chars, F, p)
        except Exception: continue
        vals = [v for ch_, v in gs if ch_.isalnum()] or [v for _, v in gs]   # 순위는 글자로만(부호 0점이 순위를 망침, 2026-11-25 「배구 일본반응」)
        fine.append(dict(c=cc, p=p, iou=round(s3, 3), first=round(s0, 3), glyphs=gs,
                         gmin=min(vals) if vals else 0, gmean=round(float(np.mean(vals)), 3) if vals else 0))
        T2._FC.clear(); T2._GC.clear()
    fine.sort(key=lambda x: (-x["gmean"], -x["gmin"]))
    # 못 찾을 것 같으면(1등이 글자마다 0.95 못 넘음) 추천 글꼴을 최대한 같게: 자세히 맞출 후보를 top_n개 더 늘려 본다(운영자 2026-11-24
    # 「폰트 진짜 못 찾은 건 최대한 같은 폰트로 수정까지」)
    if fine and fine[0]["gmin"] < NEAR_GLYPH and extra_n:
        done = {tuple(f["c"]) for f in fine}
        more = [x for x in mid if tuple(x[1]) not in done][:extra_n]
        for s0, cc in more:
            try: fine.append(fit_fine(cc, chars, F, SH))
            except Exception: continue
            T2._FC.clear(); T2._GC.clear()
        if log is not None: log.append(f"추천 글꼴 찾기: 못 찾음이라 후보 {len(more)}개 더 자세히 맞춤")
        fine.sort(key=lambda x: (-x["gmean"], -x["gmin"]))
    if not fine:   # 자세히 재기가 모두 실패(글꼴 파일 문제 등) — 대충 겹침 1등을 그대로 두고 「못 찾음」
        for s0, cc in (mid or coarse)[:5]:
            try:
                p = best_init(cc, chars, F, SH); gs = glyph_scores(cc, chars, F, p); vals = [v for ch_, v in gs if ch_.isalnum()] or [v for _, v in gs]   # 순위는 글자로만(부호 0점이 순위를 망침, 2026-11-25 「배구 일본반응」)
                fine.append(dict(c=cc, p=p, iou=round(s0, 3), first=round(s0, 3), glyphs=gs, gmin=min(vals) if vals else 0, gmean=round(float(np.mean(vals)), 3) if vals else 0))
                break
            except Exception: continue
    if force:
        fz = [f for f in fine if f["c"][0] == force]
        if not fz:
            cz = [c for c in cands if c[0] == force]
            if cz:
                try: fz = [fit_fine(tuple(cz[0][:3]), chars, F, SH)]; fine.append(fz[0])
                except Exception: fz = []
        if fz:
            fine.remove(fz[0]); fine.insert(0, fz[0])
            if log is not None: log.append(f"Claude가 그림을 보고 고른 글꼴로: {force} (평균 {fz[0]['gmean']}·최소 {fz[0]['gmin']})")
    if not fine: raise RuntimeError(f"「{text}」 후보 글꼴을 하나도 그리지 못함")
    best = fine[0]
    # 2등 = 「모양이 다른」 글꼴 중 가장 높은 것. 이름이 달라도 같은 글꼴(다른 곳에서 받은 같은 파일 등)은
    # 같은 값으로 그렸을 때 화소까지 똑같이(1.00) 겹칠 때만 같은 글꼴로 친다.
    def same(f):
        """같은 글꼴인가: 글자마다 크기 200으로 그려 잉크 상자로 잘라 96x96로 맞추고 봐주기 없는 겹침 — 1.00이어야 같은 글꼴(전에는 1px 봐준 0.97)
        (도현 두 파일 = 1.0, 비슷한 굵은 고딕끼리 = 0.84~0.92로 확인함)."""
        if family(f["c"][0]) == family(best["c"][0]): return True
        try: return same_shape(best["c"], f["c"], chars) >= 1.0
        except Exception: return False
    other = None; same_as = []
    for f in fine[1:]:
        if same(f): same_as.append(f["c"][0]); continue
        other = f; break
    T2._FC.clear(); T2._GC.clear()
    gap = round(best["gmean"] - (other["gmean"] if other else 0), 3)
    gap_min = round(best["gmin"] - (other["gmin"] if other else 0), 3)
    # 확정: 글자마다 0.95 이상 + 모양이 다른 2등보다 평균 또는 가장 낮은 글자 점수가 0.02 넘게 높음
    # (JA5roRAtF7c: 1등 10자 모두 1.0, 2등 평균 0.983·최소 0.956 — 평균 차이만 보면 확정 못 함)
    ok = best["gmin"] >= CONFIRM_GLYPH and (gap > CONFIRM_GAP or gap_min > CONFIRM_GAP)
    res = dict(same_as=same_as, rank1=rank1, rank2=rank2, confirmed=ok, best=best, second=other, gap=gap, tried=len(cands), pool=len(coarse), secs=round(time.time() - t0, 1),
               why=None if ok else (f"글자마다 겹침 최소 {best['gmin']} < {CONFIRM_GLYPH}" if best["gmin"] < CONFIRM_GLYPH else f"2등({other['c'][0] if other else '-'})과 차이 평균 {gap}·최소 {gap_min} ≤ {CONFIRM_GAP}"),
               top=[dict(name=f["c"][0], file=os.path.basename(f["c"][1]), gmean=f["gmean"], gmin=f["gmin"], iou=f["iou"], first=f["first"]) for f in fine])
    if log is not None: log.append(f"글꼴 알아내기 「{text}」: 후보 {len(cands)}개(그 줄 글자가 다 있는 것) {res['secs']}초 → {best['c'][0]} 글자 겹침 평균 {best['gmean']}·최소 {best['gmin']} · {'확정' if ok else '못 찾음'}")
    return res
