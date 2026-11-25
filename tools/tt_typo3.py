# tt_typo3 — 썸네일 속 타이틀 재현 3판(INFO-20261124-006). 격자는 맞추는 방법: 원본에서 글자에 맞춘 선을 뽑고,
# 다시 그린 그림(Chrome)에서 같은 선을 뽑아, 어긋난 만큼 값을 고쳐 다시 그리기를 모든 선 1px 안(또는 더 안 줄 때)까지 되풀이한다.
#   선 = 줄마다 위·아래·기준선, 글자마다 왼·오른·위·아래 끝 (자간 빈칸·행간 빈칸은 이 선들의 차이)
#   고치는 값 = 글자마다 자리·가로·세로 비율, 줄마다 굵기(덧댄 두께)·테두리 두께, 덩어리마다 색
# 글자 잘못 읽기도 여기서 푼다: RapidOCR(여러 변형) + Windows 글자 인식(Windows.Media.Ocr) + 그 영상의 제목·태그·설명란 낱말로
#   후보 글자를 만들고, 후보마다 같은 글꼴로 그려 원본 글자 모양과 가장 많이 겹치는 것을 고른다.
# 이 PC 안에서만(외부 AI·웹 없음). 그림은 내부 비교용.
#   python -I -X utf8 tt_typo3.py --ids 목록.tsv --img-dir <thumbs> --out <결과 폴더> --list 영상목록.json [--only id,id]
import argparse, difflib, glob, html, json, os, re, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_typo as T
import tt_typo2 as T2
import tt_fontid as FID
from tt_typo import np, cv2, imread, imwrite, hexc, lab, dE

GLYPH_PASS = 1.0   # 허용 범위 없음(운영자 2026-11-24 「100%로 맞아야」) — 전에는 0.94 · 완성 그림에서 글자마다 원본과 화소 그대로 겹침(봐주기 없음) — 맞는 글꼴은 0.95~0.98(YlzIy1udFfw 「깐족대던」), 다른 글꼴은 0.82~0.88(운영자 지적 2026-11-24 「겹쳐 보면 안 맞는데 통과」)
PASS_PX = 0.0      # 0px(똑같음)만 통과 — 판정은 mx == 0. 운영자 2026-11-24 「오차 범위 있으면 100% 일치로 다 바꿔」 · 이전 메모: 0.25px 단위로 재므로 0.25 미만 = 0px(똑같음). 운영자 2026-11-24 「100% 일치여야 일치」 — 전에는 0.5 · 모든 선 어긋남 0.5px 미만(원본 크기에서 0px, OP-20261124-024)
CRIT3 = ("통과 = 허용 범위 없이 원본과 똑같음(운영자 2026-11-24 「100% 일치여야 일치」): 글꼴을 찾음 · 원본 크기(1:1)에서 모든 선(줄 위·아래·기준선, 글자마다 왼·오른·위·아래 끝) 어긋남 0px(0.25px 단위로 잼) · "
         "완성 그림에서 글자마다 모양 겹침 1.00 · 글자 색 #RRGGBB 같음 · 실측 견주기(글자 높이·너비·자간·행간·획 굵기·기울기·색·그라데이션·테두리) 모든 항목 값이 같음 · 글자 맞음")
WINOCR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winocr.ps1")

# ---------- 글자 읽기 ----------
def win_ocr(img):
    d = tempfile.mkdtemp(prefix="ttocr_", dir=T.CFG.TMP); p = os.path.join(d, "l.png")
    cv2.imwrite(p, img)
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", WINOCR, p.replace("/", "\\")],
                           capture_output=True, timeout=60)
        out = r.stdout.decode("utf-8", "ignore").strip()
    except Exception: out = ""
    try: os.remove(p); os.rmdir(d)
    except Exception: pass
    return " ".join(x.strip() for x in out.splitlines() if x.strip())

def nospace(s): return re.sub(r"\s", "", s)

def in_titles(text, titles):
    """이 줄이 제목 줄(값/글자고르기.json 「제목줄」)인가: 같거나, 제목 줄 안에 들어 있는 조각(2자 이상)이면 제목.
    (2026-11-25 「바가지 관광지 TOP7」 한 줄이 「바가지 관광지」·「TOP7」로 나뉘어 읽혀, 둘 다 제목 글꼴 하나로 맞추지 않고 1,600여 개를 따로 뒤졌음)"""
    t = nospace(text or "")
    return bool(t) and any(t == x or (len(t) >= 2 and t in x) for x in (nospace(y) for y in titles))

def overrides(out, vid):
    """Claude가 그림을 직접 보고 적은 고침(값/글자고르기.json[vid]): 넣기·빼기·고쳐읽기{읽힌 글자: 맞는 글자}·글꼴정하기{줄 글자: 글꼴 이름}."""
    p = os.path.join(out, "값", "글자고르기.json")
    if not os.path.exists(p): return {}
    return json.load(open(p, encoding="utf-8")).get(vid, {}) or {}

AUTO_TITLES = {}
def titles_for(out, vid):
    """제목 줄: Claude가 적은 값/글자고르기.json 「제목줄」이 있으면 그것, 없으면 자동으로 고른 줄(입구로 들어온 새 영상)."""
    return overrides(out, vid).get("제목줄") or AUTO_TITLES.get(vid) or []

def auto_titles(lines):
    """「제목줄」이 없는 새 영상: 글자 높이가 가장 큰 줄의 55% 이상인 줄을 제목 줄로(로고·출처·작은 이름표를 뺌).
    2026-11-25 입구 시험(조니 뎁 쇼츠)에서 짐작 규칙이 로고 「또 다른 시선」(11.7px)까지 제목으로 넣고 줄마다 글꼴이 갈림(실측).
    크기가 비슷한 장면 자막은 이 규칙으로 못 거름 — AI 눈 확인에서 「제목줄」을 적어 다시 돌림."""
    hs = [(r, r["ink"][3] - r["ink"][1]) for r in lines if r.get("ink") and r.get("text") and sum(ch.isalnum() for ch in r["text"]) >= 1
          and "자막" not in (r.get("role") or "")]   # 자리로 자막(아래 글)이라 본 줄은 빼기 — 2026-11-25 재시험에서 「전무후무한」(아래 글(자막))이 제목으로 들어감(실측)
    if not hs: return []
    m = max(h for _, h in hs)
    return [r["text"] for r, h in hs if h >= 0.55 * m]

def candidates(ocr_texts, src_text):
    """읽은 글자들과 영상 제목·태그·설명란으로 후보 글자를 만든다."""
    cands = []
    for t in ocr_texts:
        if t and t not in cands: cands.append(t)
    base = nospace(ocr_texts[0]); n = len(base)
    toks = [t for t in re.split(r"[\s#,\[\]()'\"「」|·:/]+", src_text) if t]
    # ① 제목 등에서 같은 길이 안팎의 이어진 글자 조각 가운데 닮은 것
    flat = nospace(" ".join(toks))
    for L in range(max(1, n - 2), n + 3):
        for i in range(0, max(0, len(flat) - L) + 1):
            sub = flat[i:i + L]
            r = difflib.SequenceMatcher(None, base, sub, autojunk=False).ratio()
            if r >= 0.6 and sub not in cands: cands.append(sub)
    # ② 읽은 글자의 부분을 제목 낱말로 바꿔 끼우기(닮은 낱말 하나씩)
    for t in list(cands[:3]):
        words = t.split()
        for wi, w in enumerate(words):
            for k in range(1, len(w) + 1):
                for s0 in range(0, len(w) - k + 1):
                    piece = w[s0:s0 + k]
                    if len(piece) < 2: continue
                    for tok in toks:
                        for j in range(0, len(tok) - len(piece) + 1):
                            q = tok[j:j + len(piece)]
                            if q != piece and difflib.SequenceMatcher(None, piece, q).ratio() >= 0.5:
                                nw = words[:wi] + [w[:s0] + q + w[s0 + k:]] + words[wi + 1:]
                                c = " ".join(nw)
                                if c not in cands: cands.append(c)
    return cands[:60]

def confirm(text, sources):
    """그린 글자 한 자마다 다른 출처(Windows 글자 인식, 처음 읽음, 영상 제목·태그·설명란)의 2자 넘게 이어 맞는 조각에 드는가."""
    t = nospace(text); ok = [False] * len(t)
    for src in sources:
        if not src: continue
        sm = difflib.SequenceMatcher(None, t.lower(), nospace(src).lower(), autojunk=False)
        for a, b, n in sm.get_matching_blocks():
            if n >= 2:
                for i in range(a, a + n): ok[i] = True
    return ok

def score_text(c, text, F, rounds=10):
    chars = list(text)
    try: p = T2.init_params(c, chars, F)
    except Exception: p = None
    if p is None: return 0.0
    p, s, _, _ = T2.optimize(c, chars, F, p, rounds=rounds)
    return s

def resolve_read(r, im, src_text, c, F):
    """후보마다 같은 글꼴로 그려 원본과 겹침 → 가장 큰 것. 처음 읽은 것보다 0.01 넘게 나아야 바꾼다."""
    X0, Y0, X1, Y1 = r["_crop"]
    crop = im[Y0:Y1, X0:X1]
    big = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    w1 = win_ocr(big); w2 = win_ocr(255 - big)
    texts = [r["text"]] + [t for t in (r.get("ocr_first"), w1, w2) if t]
    cands = candidates(texts, src_text)
    sc = []
    for t in cands:
        if not nospace(t): continue
        sc.append((score_text(c, t, F), t))
    sc.sort(key=lambda x: -x[0])
    base = next((s for s, t in sc if t == r["text"]), 0.0)
    info = dict(read=r["text"], win_ocr=[w1, w2], first=r.get("ocr_first"), tried=len(sc), top=[dict(text=t, score=round(s, 3)) for s, t in sc[:6]], base=round(base, 3))
    info["_cands"] = [t for _, t in sc[:12]]
    # 다른 출처(Windows 글자 인식 두 번, 처음 읽음, 영상 제목·태그·설명란)로 글자마다 확인되는 후보를 먼저 고른다
    # (그려 겹친 점수만 보면 「NEON」의 N을 「이」로 바꾸는 일이 생김 — 2026-11-24 M7QfZAVX61A)
    # 바꿀 수 있는 후보 = 처음 읽음 그대로이거나, 다른 글자 인식(Windows 두 번) 전체와 처음 읽음보다 더 닮았거나,
    # 영상 제목·태그·설명란에 그대로 들어 있는 것. 글자 조각만 맞는 후보(「제이블랙NEON」 → 「제이이블랙EON」)는 막는다.
    def sim(a_, b_): return difflib.SequenceMatcher(None, nospace(a_).lower(), nospace(b_).lower(), autojunk=False).ratio()
    base_t = r["text"]; others = [x for x in (w1, w2, r.get("ocr_first")) if x]
    def allowed(t):
        if t == base_t: return True
        if nospace(t) and nospace(t) in nospace(src_text or ""): return True
        # 모든 글자 인식 결과(처음 읽음 포함)와의 평균 닮음이 처음 읽음보다 높아야 함 — 한 인식 결과 그대로인 후보가
        # 자기 자신과 닮아 늘 통과하던 구멍을 막음(JA5roRAtF7c 「어떻게 혼자도망쳐요」 → 「이떻게 원자 도항치요」)
        allr = list(dict.fromkeys(nospace(x) for x in others + [base_t]))
        return float(np.mean([sim(t, o) for o in allr])) > float(np.mean([sim(base_t, o) for o in allr])) + 0.01
    # 모양 증거가 아주 뚜렷하면(처음 읽음보다 0.10 넘게 잘 맞고, Windows 글자 인식 결과와 0.8 넘게 닮음) 통과
    # (처음 읽음은 자기 자신과 닮음 1.0을 받아, 띄어쓰기·괄호가 빠진 처음 읽음을 못 고치던 것 — M7QfZAVX61A 「드디어사상최초공개?」 0.49 → 「드디어 사상 최초공개(?)」 0.83)
    def strong(s_, t): return s_ > base + 0.10 and any(sim(t, o) >= 0.8 for o in (w1, w2) if o)
    full = [(s_, t) for s_, t in sc if allowed(t) or strong(s_, t)]
    info["confirmed_top"] = [dict(text=t, score=round(s_, 3)) for s_, t in full[:4]]
    pick = full[0] if full else (sc[0] if sc else None)
    if pick and pick[1] != r["text"] and pick[0] > base + 0.01:
        info["chosen"] = pick[1]
    return info

# ---------- 글자마다 모형 ----------
def gbox(c, size, ch):
    ft, _ = T2.pfont(c, size)
    return ft.getbbox(ch, anchor="ls")   # 원점(펜·기준선) 기준 잉크 상자

def model_from_fit(r):
    c, p = r["_c"], r["_p"]; X0, Y0 = r["_crop"][:2]
    G = []; pen = p["x0"]
    for i, ch in enumerate(r["_chars"]):
        _, _, _, adv = T2.glyph(c, p["size"], ch)
        if ch != " ":
            G.append(dict(i=i, ch=ch, x=X0 + pen + p["dx"][i], y=Y0 + p["by"] + p["dy"][i], sx=p["hs"], sy=1.0, sh=float(p.get("sh", 0.0))))
        pen += adv * p["hs"] + p["ls"]
    return G

def model_box(c, size, g, e):
    l, t, rr, b = gbox(c, size, g["ch"])
    return (g["x"] + l * g["sx"] - e, g["x"] + rr * g["sx"] + e, g["y"] + t * g["sy"] - e, g["y"] + b * g["sy"] + e)

def snap(c, size, g, target, e):
    """글자 g의 잉크 상자가 target(왼, 오른, 위, 아래)이 되게 자리·비율을 푼다."""
    l, t, rr, b = gbox(c, size, g["ch"])
    if rr <= l or b <= t: return
    L, R, Tt, B = target
    sx = (R - L - 2 * e) / (rr - l); sy = (B - Tt - 2 * e) / (b - t)
    g["sx"] = float(np.clip(sx, 0.75, 1.35)); g["sy"] = float(np.clip(sy, 0.75, 1.35))
    g["x"] = L + e - l * g["sx"]; g["y"] = Tt + e - t * g["sy"]

def raster_model(L, shape):
    """PIL로 모형을 그려 글자 번호 지도(그림 전체 좌표)를 낸다 — 원본·재현 화소를 글자에 나눠 줄 때 쓴다."""
    H, W = shape; idm = np.full((H, W), -1, np.int32)
    for li, r in enumerate(L):
        c, size = r["_c"], r["_size"]
        for gi, g in enumerate(r["_G"]):
            bm, ox, oy, _ = T2.glyph(c, size, g["ch"])
            if bm is None: continue
            h, w = bm.shape; nw, nh = max(1, int(round(w * g["sx"]))), max(1, int(round(h * g["sy"])))
            bm = cv2.resize(bm, (nw, nh), interpolation=cv2.INTER_LINEAR)
            gx = 0.0; sh = g.get("sh", 0.0); oys = oy * g["sy"]
            if abs(sh) > 1e-3:
                o0, o1 = -sh * oys, -sh * (oys + nh - 1); lo = min(o0, o1); hi = max(o0, o1)
                bm = cv2.warpAffine(bm, np.float32([[1, -sh, -sh * oys - lo], [0, 1, 0]]), (nw + int(np.ceil(hi - lo)) + 2, nh), flags=cv2.INTER_LINEAR)
                nw = bm.shape[1]; gx = lo
            x = int(round(g["x"] + ox * g["sx"] + gx)); y = int(round(g["y"] + oys))
            a0, b0, a1, b1 = max(0, y), max(0, x), min(H, y + nh), min(W, x + nw)
            if a1 <= a0 or b1 <= b0: continue
            sub = bm[a0 - y:a1 - y, b0 - x:b1 - x] > 127
            idm[a0:a1, b0:b1][sub] = li * 1000 + gi
    return idm

def near_only(gr, RA, L, shape):
    """색상으로 나눈 재현 화소 중, 모형에서 가장 가까운 글자와 번호가 같은 것만 남긴다
    (두 글자 색이 섞인 가장자리가 엉뚱한 글자 색으로 읽혀 멀리 떨어진 글자 상자를 늘리는 것을 막음)."""
    near = assign(RA > 0.03, raster_model(L, shape))
    return np.where(gr == near, gr, -1)

def assign_blobs(OF, idm, grow=2):
    """원본 화소를 글자에 나눌 때, 채움에서 서로 붙은 덩어리는 통째로 한 글자에 준다(덩어리 안 다수결).
    가장자리 반쯤 칠해진 화소는 가장 가까운 채움 화소의 글자를 따른다 — 이웃 글자 가장자리 화소가
    모형 자리 어긋남 때문에 엉뚱한 글자 상자에 붙어 원본 폭이 넓게 재지는 것을 막음(JA5roRAtF7c 「가」·「망」).
    두 글자가 붙은 덩어리(두 번째 글자 몫이 15% 넘음)는 그대로 화소마다 나눔."""
    per = assign(T2.grow(OF, grow), idm)
    n, lbl = cv2.connectedComponents(OF.astype(np.uint8), connectivity=8)
    core = per.copy(); core[~OF] = -1
    for i in range(1, n):
        m = lbl == i; v = per[m]; v = v[v >= 0]
        if not len(v): continue
        ks, cs = np.unique(v, return_counts=True); o = np.argsort(-cs)
        if len(ks) > 1 and cs[o[1]] > 0.15 * cs.sum(): continue
        core[m] = ks[o[0]]
    src = core >= 0
    if not src.any(): return per
    _, nl = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(src); table = np.full(nl.max() + 1, -1, np.int32); table[nl[ys, xs]] = core[ys, xs]
    out = table[nl]; out[per < 0] = -1
    return out

def assign(mask, idm):
    src = idm >= 0
    if not src.any(): return np.full(mask.shape, -1, np.int32)
    _, lbl = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(src); table = np.full(lbl.max() + 1, -1, np.int32); table[lbl[ys, xs]] = idm[ys, xs]
    out = table[lbl]; out[~mask] = -1
    return out

def boxes_of(mask, gmap, keys):
    out = {}
    for k in keys:
        m = gmap == k
        if m.sum() < 3: continue
        ys, xs = np.where(m); out[k] = (int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1)
    return out

def sp_boxes(A, gmap, keys, th=0.12):
    """반쯤 칠해진 가장자리 화소까지 써서 0.25px 단위로 글자 끝을 잰다(4배 확대와 같은 정밀도).
    A = 화소마다 글자 정도(0~1). 줄(행)마다 처음·끝 화소의 칠해진 정도로 끝 자리를 소수까지 낸다."""
    out = {}
    for k in keys:
        P = (gmap == k) & (A > th)
        if P.sum() < 3: continue
        ys, xs = np.where(P); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        sub = np.where(P[y0:y1 + 1, x0:x1 + 1], A[y0:y1 + 1, x0:x1 + 1], 0.0)
        def edges(M):
            lo, hi = [], []
            for line in M:
                nz = np.nonzero(line)[0]
                if len(nz): lo.append(nz[0] + 1 - line[nz[0]]); hi.append(nz[-1] + line[nz[-1]])
            return min(lo), max(hi)
        l, r = edges(sub); t, b = edges(sub.T)
        out[k] = (float(x0 + l), float(x0 + r), float(y0 + t), float(y0 + b))
    return out

def alpha_orig(im, OF, gsoft, L, keys):
    """원본 화소마다 글자 정도: 바깥 색(테두리 색, 없으면 바탕 색)에서 그 글자 안쪽 색까지 어디쯤인가."""
    A = np.zeros(OF.shape, np.float32); f = im.astype(np.float32)
    for k in keys:
        li = k // 1000; r = L[li]; P = gsoft == k
        if not P.any(): continue
        core = T2.core_of(P & OF)
        if core.sum() < 3: continue
        cin = np.median(f[core], 0); cout = np.array(T._hex2bgr(r["_oc"] if r.get("_ow") else r["bg_color"]), np.float32)
        v = cin - cout; nn = float(v @ v)
        if nn < 100: A[P] = OF[P]; continue
        A[P] = np.clip(((f[P] - cout) @ v) / nn, 0, 1)
    return A

def lines_of(L, bo, br):
    """격자 선: 줄마다 위·아래·기준선, 글자마다 왼·오른·위·아래 끝 — (이름, 원본, 재현, 차이)."""
    out = []
    for li, r in enumerate(L):
        ks = [li * 1000 + gi for gi in range(len(r["_G"]))]
        ko = [k for k in ks if k in bo and k in br]
        if not ko: continue
        o_top = min(bo[k][2] for k in ko); r_top = min(br[k][2] for k in ko)
        o_bot = max(bo[k][3] for k in ko); r_bot = max(br[k][3] for k in ko)
        o_base = float(np.median([bo[k][3] for k in ko])); r_base = float(np.median([br[k][3] for k in ko]))
        tag = f"{li+1}줄"
        out += [dict(line=li, kind="줄", name=f"{tag} 위", o=o_top, r=r_top), dict(line=li, kind="줄", name=f"{tag} 아래", o=o_bot, r=r_bot),
                dict(line=li, kind="줄", name=f"{tag} 기준선", o=o_base, r=r_base)]
        for k in ko:
            ch = r["_G"][k % 1000]["ch"]
            for j, nm in enumerate(("왼", "오른", "위", "아래")):
                out.append(dict(line=li, kind="글자", g=k % 1000, name=f"{tag} 「{ch}」 {nm}", o=bo[k][j], r=br[k][j], axis="x" if j < 2 else "y"))
    # 원본에서 이웃 글자와 붙은(빈칸 1px 이하) 쪽 끝은 어디까지가 어느 글자인지 알 수 없어 「잴 수 없음」으로 표시하고 판정에서 뺀다
    for li, r in enumerate(L):
        ko = sorted([li * 1000 + gi for gi in range(len(r["_G"])) if li * 1000 + gi in bo and li * 1000 + gi in br])
        for a_, b_ in zip(ko, ko[1:]):
            if bo[b_][0] - bo[a_][1] <= 1.0:
                for d in out:
                    if d["line"] == li and d.get("g") == a_ % 1000 and d["name"].endswith(" 오른"): d["touch"] = True
                    if d["line"] == li and d.get("g") == b_ % 1000 and d["name"].endswith(" 왼"): d["touch"] = True
    q = lambda v: round(float(v), 2)   # 0.01px까지 적음(전에는 0.25px 단위로 반올림 = 0.12px까지 0으로 봐줌 — 판 1.4에서 없앰)
    for d in out: d["o"] = q(d["o"]); d["r"] = q(d["r"]); d["d"] = round(d["r"] - d["o"], 2)
    return out

# ---------- SVG ----------
def svg3(im, L, bgfile, mode):
    """mode: color(배경+그림자+테두리+채움) / fill(검은 바탕, 채움만 흰색) / union(채움+테두리 흰색)"""
    H, W = im.shape[:2]; defs, body, faces = [], [], {}; pids = set()
    for li, r in enumerate(L):
        c = r["_c"]; size = r["_size"]; fam = "f%d" % (abs(hash((c[1], c[2]))) % 10 ** 6); faces[fam] = c
        e = r["_e"]; ow = r.get("_ow") or 0
        P = PATHS.get(f'{c[1]}|{c[2]}', {})
        for gi, g in enumerate(r["_G"]):
            d = P.get("g", {}).get(g["ch"])
            if d:   # 글꼴 윤곽선으로 그림 — Chrome의 정수 픽셀 맞춤(힌팅) 없이 소수 자리 그대로
                pid = f'p{abs(hash((c[1], c[2], g["ch"]))) % 10 ** 9}'
                if pid not in pids:
                    pids.add(pid); defs.append(f'<path id="{pid}" d="{d}" vector-effect="non-scaling-stroke"/>')
                kk = size / P["upm"]
                # 기울임(줄 하나에 한 벌): 기준선에서 위로 갈수록 오른쪽으로 — 찾기 단계(tt_typo2.layout)와 같은 식. 전에는 마지막 그림에서 빠져 있었음(df6jENnHjOE)
                tr = f'translate({g["x"]:.3f} {g["y"]:.3f}) matrix(1 0 {-g.get("sh", 0.0):.5f} 1 0 0) scale({kk*g["sx"]:.6f} {-kk*g["sy"]:.6f})'
                el = lambda attrs: f'<use href="#{pid}" transform="{tr}" stroke-linejoin="round" {attrs}/>'
                k = 1.0   # non-scaling-stroke: 획 두께는 화면 px 그대로
            else:
                tr = f'translate({g["x"]:.3f} {g["y"]:.3f}) matrix(1 0 {-g.get("sh", 0.0):.5f} 1 0 0) scale({g["sx"]:.4f} {g["sy"]:.4f})'
                chx = html.escape(g["ch"])
                el = lambda attrs, chx=chx, tr=tr: f'<text font-family="{fam}" font-size="{size:.2f}" transform="{tr}" stroke-linejoin="round" {attrs}>{chx}</text>'
                k = 2 / (g["sx"] + g["sy"])
            if mode == "fill":
                sw = f' stroke="#fff" stroke-width="{2*e*k:.3f}"' if e > 0.05 else ""
                body.append(el(f'fill="#fff"{sw}')); continue
            if mode == "ids":
                hc = ID_COL[(li * 1000 + gi) % len(ID_COL)] if False else id_color(li, gi, L)
                sw = f' stroke="{hc}" stroke-width="{2*e*k:.3f}"' if e > 0.05 else ""
                body.append(el(f'fill="{hc}"{sw}')); continue
            if mode == "union":
                body.append(el(f'fill="#fff" stroke="#fff" stroke-width="{2*(e+ow)*k:.3f}"')); continue
            sp = next((s for s in r["_spans"] if s["i0"] <= g["i"] <= s["i1"]), r["_spans"][-1])
            col = sp["color"]
            if sp.get("grad"):
                gid = f"g{li}_{r['_spans'].index(sp)}"
                if gid not in "".join(defs):
                    iy0, iy1 = r["_ink_y"]
                    defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="{iy0}" x2="0" y2="{iy1}">'
                                f'<stop offset="0.15" stop-color="{sp["grad"]["start"]}"/><stop offset="0.85" stop-color="{sp["grad"]["end"]}"/></linearGradient>')
                col = f"url(#{gid})"
            if r.get("shadow"):
                s_ = r["shadow"]
                body.append(f'<g transform="translate({s_["dx"]} {s_["dy"]})">' + el(f'fill="{s_["color"]}" stroke="{s_["color"]}" stroke-width="{2*(ow+e)*k:.3f}"') + '</g>')
            if ow:
                body.append(el(f'fill="{r["_oc"]}" stroke="{r["_oc"]}" stroke-width="{2*(ow+e)*k:.3f}"'))
            sw = f' stroke="{col}" stroke-width="{2*e*k:.3f}"' if e > 0.05 else ""
            body.append(el(f'fill="{col}"{sw}'))
    ff = "".join("@font-face{font-family:%s;src:url('file:///%s');}" % (k, c[1]) for k, c in faces.items())
    ffv = "".join(f"text[font-family={k}]{{font-variation-settings:'wght' {c[2]};}}" for k, c in faces.items() if c[2])
    bg = f'<image href="{bgfile}" x="0" y="0" width="{W}" height="{H}"/>' if mode == "color" else f'<rect width="{W}" height="{H}" fill="#000"/>'
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{ff}{ffv}text{{text-rendering:geometricPrecision}}html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#000}}</style></head>'
            f'<body><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{"".join(defs)}</defs>{bg}{"".join(body)}</svg></body></html>')

def jpeg_like(img, src_path):
    """재현 그림을 원본 JPEG과 같은 양자화 표·색 나눔(4:2:0 등)으로 압축했다가 푼다 — 같은 압축 잡음을 거친 뒤 견주려고."""
    from PIL import Image, JpegImagePlugin
    import io
    o = Image.open(src_path); rgb = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)); buf = io.BytesIO()
    q = getattr(o, "quantization", None)
    if o.format == "JPEG" and q:
        sub = JpegImagePlugin.get_sampling(o)
        rgb.save(buf, "JPEG", qtables=q, subsampling=sub if sub >= 0 else 2)
    else: rgb.save(buf, "JPEG", quality=90)
    return cv2.cvtColor(np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB")), cv2.COLOR_RGB2BGR)

ID_COL = []
def id_keys(L): return [li * 1000 + gi for li, r in enumerate(L) for gi in range(len(r["_G"]))]
def id_color(li, gi, L):
    ks = id_keys(L); n = len(ks); j = ks.index(li * 1000 + gi)
    import colorsys
    # 이웃 글자끼리 색상이 멀도록 섞어 놓는다
    order = list(range(0, n, 2)) + list(range(1, n, 2)); h = order.index(j) / n
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))

def decode_ids(img, L, th=0.03):
    """ids 그림 → (글자 정도 A 0~1, 글자 번호 지도). 색상이 가장 가까운 글자로."""
    import colorsys
    ks = id_keys(L); n = len(ks)
    order = list(range(0, n, 2)) + list(range(1, n, 2))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV_FULL).astype(np.float32)
    A = hsv[..., 2] / 255; hue = hsv[..., 0] / 256
    hues = np.array([order.index(j) / n for j in range(n)], np.float32)
    d = np.abs(hue[..., None] - hues[None, None, :]); d = np.minimum(d, 1 - d)
    gm = np.array(ks, np.int32)[np.argmin(d, axis=2)]
    gm[A <= th] = -1
    return A, gm

PATHS = {}
SYS_PY = T.CFG.FONTTOOLS_PY   # fontTools가 있는 파이썬(기본 = 지금 파이썬, tt_config.py)
def load_paths(L):
    req = {}
    for r in L:
        c = r["_c"]; key = f"{c[1]}|{c[2]}"
        if key in PATHS and all(ch in PATHS[key]["g"] for ch in r["_chars"] if ch != " "): continue
        q = req.setdefault(key, dict(file=c[1], wght=c[2], chars=""))
        q["chars"] += "".join(ch for ch in r["_chars"] if ch != " ")
    if not req: return
    d = tempfile.mkdtemp(prefix="ttgp_", dir=T.CFG.TMP); a, b = os.path.join(d, "q.json"), os.path.join(d, "r.json")
    json.dump(list(req.values()), open(a, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        subprocess.run([SYS_PY, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_glyphpath.py"), a, b], timeout=120, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for k, v in json.load(open(b, encoding="utf-8")).items():
            PATHS.setdefault(k, dict(upm=v["upm"], g={}))["g"].update(v["g"])
    except Exception as ex:
        print(f"  윤곽선 뽑기 실패 — 글자(text)로 그림: {ex}", flush=True)

def shoot(im, L, bgurl, mode, RD, G, vid):
    H, W = im.shape[:2]
    hf = os.path.join(RD, f"{vid}{'' if mode == 'color' else '_' + mode}.html"); png = os.path.join(G, f"{vid}_{ {'color': '재현', 'fill': '재현채움', 'union': '재현테두리', 'ids': '재현글자번호'}[mode] }.png")
    open(hf, "w", encoding="utf-8").write(svg3(im, L, bgurl, mode)); T.chrome_shot(hf, png, W, H)
    return imread(png)

# ---------- 한 장 ----------
def is_title(r, H, im=None, vid=None, out=None):
    """재현할 글자 = 크리에이터가 얹은 글자 전부(제목·자막·출처 등, 자리 상관없음). 장면 속 글자(간판·옷·물건)는 뺀다
    (운영자 2026-11-24 「제목 외에 보이는 모든 글자, 크리에이터가 쓴 글자만, 간판 글자는 하지 말고」).
    얹은 글자 표시: 뒤에 띠·상자가 있음 / 테두리가 있음 / 글자 속 색이 고름(사진 속 글자는 빛·질감으로 얼룩짐).
    Claude가 그림을 직접 보고 고친 목록(값/글자고르기.json {영상: {"빼기": [글자...], "넣기": [글자...]}})이 있으면 그것이 먼저."""
    t = (r.get("text") or "").replace(" ", "")
    if out and vid:
        p = os.path.join(out, "값", "글자고르기.json")
        if os.path.exists(p):
            ov = json.load(open(p, encoding="utf-8")).get(vid, {})
            if any(x.replace(" ", "") and x.replace(" ", "") in t for x in ov.get("빼기", [])): return False
            if any(x.replace(" ", "") and x.replace(" ", "") in t for x in ov.get("넣기", [])): return True
    if r["back"] != "없음(그림 위)" or r.get("outline"): return True
    if im is not None and r.get("_crop") is not None:
        ix0, iy0, ix1, iy1 = r["ink"]; F = r["_fill_mask"]
        C = im[iy0:iy0 + F.shape[0], ix0:ix0 + F.shape[1]].astype(np.float32)   # 채움 지도는 잉크 상자 크기
        if F.shape == C.shape[:2]:
            core = cv2.erode(F.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            if core.sum() >= 30:
                sd = float(np.std(lab(C[core]), 0).mean())
                r["fill_std"] = round(sd, 1)
                if sd < 9.0: return True   # 고른 색 = 얹은 글자. 얼룩져도(그라데이션 등) 아래 위치 규칙으로 한 번 더 봄
    return r["role"] == "위 제목"

def other_color_text(C, F, r):
    """한 줄 글자가 두 색 넘게(예: 「깐족대던」 분홍 + 「시바견의 최후」 흰색) 칠해졌는데 한 색만 뗀 경우:
    글자 높이 띠 안에서 색을 6묶음으로 나눠, 이미 뗀 글자 자리(가로)와 거의 안 겹치고 띠 폭 대부분을 덮지 않는(바탕 아님)
    묶음 중 띠의 2% 넘는 것을 글자로 더한다. 바탕색과 Lab 40 안인 묶음은 뺀다."""
    ys, xs = np.nonzero(F)
    if len(xs) < 50: return None, None
    y0, y1 = ys.min(), ys.max() + 1; fx0, fx1 = xs.min(), xs.max()
    band = C[y0:y1].astype(np.uint8); H_, W_ = band.shape[:2]
    Lb = cv2.cvtColor(band, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    _, lb, cen = cv2.kmeans(Lb, 6, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    lb = lb.reshape(H_, W_)
    try: bgL = cv2.cvtColor(np.uint8([[T._hex2bgr(r["bg_color"])]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    except Exception: bgL = None
    Fb = F[y0:y1]; fL = np.median(Lb.reshape(H_, W_, 3)[Fb], 0)
    add = np.zeros_like(F); names = []
    for k in range(len(cen)):
        m = lb == k
        if m.mean() < 0.02: continue
        cols = np.nonzero(m.mean(0) > 0.05)[0]
        if len(cols) == 0 or (cols.max() - cols.min()) > 0.8 * W_: continue          # 띠 폭 대부분 = 바탕
        if float(np.linalg.norm(cen[k] - fL)) < 25: continue                         # 이미 뗀 글자 색
        if bgL is not None and float(np.linalg.norm(cen[k] - bgL)) < 40: continue
        ov = max(0, min(cols.max(), fx1) - max(cols.min(), fx0)) / max(1, cols.max() - cols.min())
        if ov > 0.3: continue                                                         # 뗀 글자 자리와 겹침 = 테두리·번짐
        k_, lab_, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
        m = np.isin(lab_, [i for i in range(1, k_) if st[i, 4] >= 15])
        if m.sum() < 100: continue
        add[y0:y1] |= m
        bgr = cv2.cvtColor(np.uint8([[cen[k]]]), cv2.COLOR_LAB2BGR)[0, 0]
        names.append(f"#{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X} x {cols.min()}~{cols.max()}")
    if not add.any(): return None, None
    return F | add, ", ".join(names)

def tighten_fill(C, F):
    """채움(F)에 번짐·테두리와 섞인 색이 들어가 글자끼리 붙은 경우: 글자 한가운데(가장자리에서 먼) 화소의 색을 기준으로
    Lab 거리 30 안 화소만 남기고, 15화소 밑 점을 버리고, 줄 높이 0.1배 제곱보다 작은 구멍은 메운다.
    덩어리 수가 늘거나(붙은 글자가 떨어짐) 구멍이 크게 줄 때만 바꾼다."""
    if F.sum() < 100: return None
    Lb = cv2.cvtColor(C.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    dt = cv2.distanceTransform(F.astype(np.uint8), cv2.DIST_L2, 5)
    core = F & (dt >= max(1.5, 0.5 * float(dt.max())))
    if core.sum() < 10: return None
    ref = np.median(Lb[core], 0)
    G = F & (np.linalg.norm(Lb - ref, axis=2) < 30)
    k, lab_, st, _ = cv2.connectedComponentsWithStats(G.astype(np.uint8))
    G = np.isin(lab_, [i for i in range(1, k) if st[i, 4] >= 15])
    ys, xs = np.nonzero(G)
    if len(ys) < 100: return None
    lim = (0.1 * (ys.max() - ys.min() + 1)) ** 2
    cs, hi = cv2.findContours(G.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = G.astype(np.uint8)
    if hi is not None: cv2.drawContours(out, [c for c, x in zip(cs, hi[0]) if x[3] >= 0 and cv2.contourArea(c) < lim], -1, 1, -1)
    G = out > 0
    def nblob(m):
        k, _, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8)); return int((st[1:, 4] >= 40).sum())
    def nhole(m):
        cs, hi = cv2.findContours(m.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE); return 0 if hi is None else int((hi[0][:, 3] >= 0).sum())
    if nblob(G) > nblob(F) or nhole(F) > 3 * max(1, nhole(G)) + 10: return G
    return None

def band_only(F, text=""):
    """줄 채움에서 글자 높이 띠 밖에 있는 조각(사진 속 흰 간판·잡티)을 뺀다.
    띠 = 줄마다 잉크 화소 수가 가장 많은 줄의 25% 넘는 줄 가운데 가장 긴 이어진 구간(빈 줄 3개까지 이음).
    조각(이어진 덩어리)이 띠와 한 줄도 겹치지 않고 2화소 넘게 떨어져 있을 때만 뺀다(받침 ㅇ·밑줄을 빼던 잘못 — 눈으로 봄 2026-11-25).
    줄 글자에 밑줄(_)이 있으면 띠 아래 조각은 남긴다. 빼는 양이 잉크의 30%를 넘으면 띠를 잘못 잡은 것으로 보고 손대지 않는다.
    (2026-11-25 「바가지 관광지 TOP7」 첫 줄 위에 사진 간판 조각이 붙어 글자 모양 견주기가 핑크퐁 아기상어를 1등으로 고름 — 눈으로 봄)"""
    rows = F.sum(1)
    if rows.max() == 0: return F, None
    on = rows > 0.25 * rows.max()
    best = (0, -1, -1); s = None; gap = 0
    for y, v in enumerate(list(on) + [False] * 4):
        if v:
            if s is None: s = y
            gap = 0; e = y
        elif s is not None:
            gap += 1
            if gap > 3:
                if e - s > best[0]: best = (e - s, s, e)
                s = None; gap = 0
    _, b0, b1 = best
    if b0 < 0: return F, None
    n, lab_, st, _ = cv2.connectedComponentsWithStats(F.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool); keep[0] = False; cut = 0; px = 0
    for i in range(1, n):
        y0, h = st[i, cv2.CC_STAT_TOP], st[i, cv2.CC_STAT_HEIGHT]
        above = y0 + h - 1 < b0 - 2; below = y0 > b1 + 2
        if above or (below and "_" not in text): cut += 1; px += int(st[i, cv2.CC_STAT_AREA])
        else: keep[i] = True
    if not cut or px > 0.3 * F.sum(): return F, None
    return keep[lab_] & F, (cut, px)

def script_of(ch):
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F or 0x1100 <= o <= 0x11FF: return "한"
    if ch.isascii() and ch.isalnum(): return "영"
    return None

def split_runs(r, F, w, log):
    """줄 글자를 한글·영문 덩어리로 나눔(둘 다 2자 이상일 때만). 덩어리마다 (줄 사본, 그 덩어리 자리만 남긴 채움)."""
    chars = r["_chars"]; runs = []
    for i, ch in enumerate(chars):
        sc = script_of(ch)
        if runs and (sc is None or sc == runs[-1][0]): runs[-1][1].append(i)
        else: runs.append([sc or "?", [i]])
    runs = [x for x in runs if x[0] in ("한", "영")] if all(x[0] in ("한", "영", "?") for x in runs) else runs
    if len(runs) < 2 or any(sum(1 for i in idx if chars[i].strip()) < 2 for _, idx in runs) or len({k for k, _ in runs}) < 2:
        return [(r, F)]
    if len(w["p"].get("dx", [])) != len(chars):   # 읽기를 고쳐(정답 줄 등) 글자 수가 바뀌면 그 글자로 다시 맞춘 뒤 나눈다(M7Q 오류 2026-11-24)
        w = T2.fit_line(chars, F, log)[0]
    lay = {i: (x, x + g.shape[1]) for i, g, x, y, _ in T2.layout(w["c"], chars, w["p"])}
    cuts = []
    for a, b in zip(runs, runs[1:]):
        ra = max(lay[i][1] for i in a[1] if i in lay); lb = min(lay[i][0] for i in b[1] if i in lay)
        cuts.append(int(round((ra + lb) / 2)))
    edges = [0] + cuts + [F.shape[1]]; out = []
    for k, (sc, idx) in enumerate(runs):
        rr = dict(r)   # 원래 줄은 건드리지 않는다(나누기를 취소하면 원래 줄 그대로 돌려줘야 함)
        keep = np.zeros(F.shape[1], bool); keep[edges[k]:edges[k + 1]] = True
        rr["_chars"] = [chars[i] for i in idx]; rr["text"] = "".join(rr["_chars"]).strip(); rr["_chars"] = list(rr["text"])
        rr["_uni"] = r["_uni"] & keep[None, :] if r.get("_uni") is not None else None
        rr["script"] = sc
        out.append((rr, F & keep[None, :]))
    # 자른 자리가 어긋나 한 덩어리의 채움이 비거나 너무 적으면(대충 맞춘 글꼴이 틀려 글자 자리를 잘못 잡은 경우) 나누지 않는다
    tot = max(1, int(F.sum()))
    if any(int(f.sum()) < max(50, 0.05 * tot * len(x["_chars"]) / max(1, len(chars))) for x, f in out):
        log.append("덩어리 나누기 취소 — 나눈 쪽 채움이 비어 있음(자를 자리 어긋남): " + " / ".join(f"「{x['text']}」 {int(f.sum())}화소" for x, f in out))
        return [(r, F)]
    log.append("한 줄을 글자 덩어리로 나눠 따로 글꼴 찾기: " + " / ".join(f"「{x[0]['text']}」" for x in out))
    return out

def split_fill_outline(im, r, F):
    """1판 글자 떼기가 채움에 테두리를 섞었으면 다시 나눈다: 채움 화소를 두 색으로 나눠, 바깥(글자 밖)과 더 많이 맞닿는 쪽이
    뚜렷하게(맞닿는 비율 차이 0.25 넘게) 많고 두 색 차이가 ΔE 40 넘으면 그쪽을 테두리로 본다."""
    X0, Y0, X1, Y1 = r["_crop"]
    C = im[Y0:Y1, X0:X1].astype(np.float32)
    if F.sum() < 50: return F, None
    px = lab(C[F]); _, lb, cen = cv2.kmeans(px.astype(np.float32), 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    if float(np.linalg.norm(cen[0] - cen[1])) < 40: return F, None
    M = [np.zeros_like(F) for _ in range(2)]
    ys, xs = np.where(F)
    for k in range(2): M[k][ys[lb.ravel() == k], xs[lb.ravel() == k]] = True
    out = cv2.dilate((~F).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    touch = []
    for k in range(2):
        edge = M[k] & (cv2.dilate((~M[k]).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        touch.append((edge & out).sum() / max(1, edge.sum()))
    fi = int(np.argmin(touch)); oi = 1 - fi
    if touch[oi] - touch[fi] < 0.25 or M[fi].sum() < 0.15 * F.sum() or M[oi].sum() < 0.15 * F.sum(): return F, None
    # 테두리라면 거의 모두 채움 바로 곁에 있다. 채움에서 떨어진 화소가 많으면 테두리가 아니라 다른 색 글자(03JG-F0BEdU 빨간 「260억」)
    ys_ = np.nonzero(F.any(1))[0]; hh = (ys_.max() - ys_.min() + 1) if len(ys_) else 10
    rr_ = max(3, int(round(0.15 * hh)))
    near_ = cv2.dilate(M[fi].astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rr_ + 1, 2 * rr_ + 1))) > 0
    if (M[oi] & near_).sum() < 0.7 * M[oi].sum(): return F, None
    fill = cv2.morphologyEx(M[fi].astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    return fill, dict(color=hexc(np.median(C[M[oi]], 0)), union=F | r["_uni"])

# ---------- 산돌구름 먼저(운영자 2026-11-24 「산돌구름부터」·「산돌구름에 보내는 작업이 먼저」, 10장 제한 풀림) ----------
SANDOLL_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_sandoll.mjs")
def sandoll_names(png, outj):
    """글자 줄 그림 한 장 → 산돌구름 이미지 폰트 검색 후보 이름(순서대로). 결과 화면·견본 그림은 받지 않고 글만 읽는다."""
    if not os.path.exists(outj):
        try: subprocess.run(["node", SANDOLL_JS, "run", png, outj], timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: return []
    if not os.path.exists(outj): return []
    js = json.load(open(outj, encoding="utf-8")); names = []
    for key in ("text", "text_free"):   # 「전체」 칸 + 「무료」 칸(후보 늘리기)
        t = (js.get(key) or "").splitlines()
        try: i = t.index("무료", t.index("전체")) + 1; j = t.index("검색 결과가 마음에 들지 않는다면?", i)
        except ValueError: continue
        names += [x.strip() for x in t[i:j] if x.strip() and x.strip() not in names]
    return names

def _norm_font(n):
    n = re.sub(r"\(.*?\)", "", n.lower()).replace("배달의민족", "배민").replace("hfc:", "")
    for w in ("ttf", "otf", "체", " ", "_", "-", "regular"): n = n.replace(w, "")
    return n

_STYLE = re.compile(r"(extrabold|ultrabold|semibold|demibold|bold|black|heavy|extralight|ultralight|light|medium|thin|hairline|normal|book|italic|굵은|볼드|\d+)")
def _fam_font(n):
    """글꼴 이름에서 굵기 낱말을 뺀 집안 이름 — 「Bold」뿐인 이름이 모든 Bold 글꼴과 짝지어지던 잘못(2026-11-25 산돌 「Sandoll 격동고딕」 → 이 PC Bold 글꼴 170여 개, 실측) 막기"""
    return _STYLE.sub("", _norm_font(n))

def sandoll_local(names, chars):
    """산돌 후보 이름 → 이 PC에 있는 같은 글꼴 파일(있는 것만). 이름 비교는 띄어쓰기·체·TTF 등을 빼고."""
    pool = [c for c in FID.pool_fonts() if FID.covers(c[3], chars)]
    out = []
    for nm in names:
        k = _norm_font(nm); kf = _fam_font(nm)
        if len(kf) < 2: continue
        for c in pool:
            # 이름표의 모든 이름(한글·영문)과 견줌 — 산돌은 한글 이름, 파일은 영문 이름인 경우가 많음
            hit = False
            for nm2 in [c[0]] + FID.aliases(c[1]):
                ck = _norm_font(nm2); cf = _fam_font(nm2)
                if len(cf) < 2: continue   # 이름이 「Regular」「Bold」뿐인 글꼴 등은 비교하지 않음
                if k == ck or (len(kf) >= 3 and len(cf) >= 3 and (kf in cf or cf in kf)) or difflib.SequenceMatcher(None, k, ck).ratio() >= 0.85: hit = True; break
            if hit:
                if tuple(c[:3]) not in out: out.append(tuple(c[:3]))
    return out

def _status(out, vid, stage, secs, done=None):
    """진행 파일(값/_진행.json): 감시(tools/tt_watchdog.mjs)가 멈춤·시간 초과·프로세스 죽음을 알아채게 한다(운영자 2026-11-24)."""
    try:
        p = os.path.join(out, "값", "_진행.json"); tmp = p + ".tmp"
        json.dump(dict(vid=vid, stage=stage, secs=round(secs, 1), pid=os.getpid(), at=time.time(), done=done), open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, p)
    except Exception: pass

def run_one(vid, path, out, src_text, log, max_rounds=24):
    t0 = time.time()
    im, lines = T.analyze(vid, path, out, keep_small=True)
    H, W = im.shape[:2]
    for t_, why_ in T.DROPS:
        log.append(f"글 「{t_}」 {why_[3:]}" if why_.startswith("@넓힘") else f"글 「{t_}」 줄 찾기에서 버림({why_})")
    L = []; pend = []
    if not overrides(out, vid).get("제목줄"):
        AUTO_TITLES[vid] = auto_titles([r for r in lines if "_fit" in r])
        log.append(f"제목줄이 정해져 있지 않아 자동으로 고름(가장 큰 글자 높이의 55% 이상): {AUTO_TITLES[vid]}")
    for r in lines:
        if "_fit" not in r:
            log.append(f"「{r.get('text')}」 줄은 글자 맞춤 값이 없어 건너뜀(잉크 {r.get('ink')})"); continue
        # 제목만 비교(운영자 2026-11-25 「화면 속 글자는 처음에 비교 대상 아니게 거르도록」): 값/글자고르기.json 「제목줄」이 있으면
        # 그 제목 줄과 닮은(0.5 이상) 줄·제목 줄 조각만 남기고, 인용·이름표·나라 이름·숫자 막대 같은 다른 글자는 읽기·글꼴 찾기 전에 뺀다.
        # (전에는 11-24 지시대로 크리에이터가 얹은 글자를 모두 재현 — 「전세계가 빚더미인데…」에서 제목 아닌 줄마다 글꼴 찾기 46~77초, 실측)
        # 제목 줄이 정해져 있으면 그것이 판정이다 — 「장면 글자」 짐작(뒤 띠·색 고름·자리)보다 먼저.
        # (2026-11-25 「한국이 미국 야구 다 망쳐놨다」 노란 셋째 줄·「배구 일본반응」 노란 둘째 줄이 「그림 위 아래 자막」으로 짐작돼 말없이 빠짐 — 눈으로 봄)
        tl_ = titles_for(out, vid) or []
        if tl_:
            sm_ = max(difflib.SequenceMatcher(None, nospace(r.get("text") or ""), nospace(x_)).ratio() for x_ in tl_)
            if sm_ < 0.5 and not in_titles(r.get("text"), tl_):
                log.append(f"「{r.get('text')}」 줄은 제목이 아니라 비교하지 않음(제목 줄과 닮음 {sm_:.2f})"); continue
        elif not is_title(r, H, im, vid, out):
            log.append(f"「{r.get('text')}」 줄은 장면 글자로 보고 건너뜀(뒤 {r.get('back')} · 색 고름 {r.get('fill_std')} · 자리 {r.get('role')})"); continue
        X0, Y0, X1, Y1 = r["_crop"]
        # ① 글자 줄을 잘라 산돌구름에 먼저 보낸다(읽기·글꼴 찾기보다 먼저)
        if False:   # 산돌구름 자동 검색은 공유본에서 뺌(사이트 약관 — 자동 사용 금지). 산돌 글꼴 이름은 사람이 사이트에서 직접 찾아 값/글자고르기.json 「눈후보」에 적는다
            sd = os.path.join(out, "그림", "산돌"); os.makedirs(sd, exist_ok=True)
            k_ = f"{vid}_{r['ink'][1]}"; png_ = os.path.join(sd, k_ + ".png")
            if not os.path.exists(png_): imwrite(png_, im[Y0:Y1, X0:X1])
            t_s = time.time(); r["sandoll"] = sandoll_names(png_, os.path.join(sd, k_ + ".json"))
            log.append(f"산돌구름 「{r['text']}」 후보 {len(r['sandoll'])}개({time.time() - t_s:.0f}초): " + ", ".join(r["sandoll"][:5]))
        F = np.zeros((Y1 - Y0, X1 - X0), bool)
        ix0, iy0, ix1, iy1 = r["ink"]; fm = r["_fill_mask"]
        F[iy0 - Y0:iy0 - Y0 + fm.shape[0], ix0 - X0:ix0 - X0 + fm.shape[1]] = fm
        F2, sp = split_fill_outline(im, r, F)
        if sp:
            log.append(f"「{r['text']}」 채움에 섞인 테두리 {sp['color']}를 따로 뗌")
            F = F2; r["_uni"] = sp["union"]; r["outline"] = dict(color=sp["color"], width_px=1.0, split=True)
        F3, add = other_color_text(im[Y0:Y1, X0:X1], F, r)
        if F3 is not None:
            log.append(f"「{r['text']}」 한 줄에 다른 색 글자가 더 있어 함께 뗌: {add}")
            F = F3
        F2 = tighten_fill(im[Y0:Y1, X0:X1], F) if F3 is None else None   # 여러 색 줄은 한 색 기준 좁히기를 하지 않음
        if F2 is not None:
            log.append(f"「{r['text']}」 채움을 글자 한가운데 색 가까운 화소로 좁힘(번짐·이웃 색 뺌): {int(F.sum())}→{int(F2.sum())}화소")
            r["_uni"] = r["_uni"] | F; F = F2
        F4, cut_ = band_only(F, r.get("text") or "")
        if cut_:
            log.append(f"「{r['text']}」 글자 높이 띠 밖의 조각 {cut_[0]}개({cut_[1]}화소)를 뺌(사진 속 간판·잡티)")
            if "_uni" in r: r["_uni"] = r["_uni"] & ~(F & ~F4)
            F = F4
        r["_F"] = F; r["_chars"] = list(r["text"])
        w, fine, coarse = T2.fit_line(r["_chars"], F, log)
        # 글자 읽기 풀기
        rd = resolve_read(r, im, src_text, w["c"], F)
        r["read3"] = rd
        if rd.get("chosen"):
            r["text"] = rd["chosen"]; r["_chars"] = list(r["text"])
        # 한 줄에 한글 덩어리와 영문 덩어리가 섞이면 따로 다른 글꼴일 수 있다(산돌구름도 「제이블랙」·「NEON」을 나눠 찾음) → 덩어리마다 따로 찾는다
        # 줄 앞뒤의 문장부호가 다른 글자 인식·제목·태그·설명란 어디에도 없으면 잡티로 보고 뺌(JA5roRAtF7c 「…도망쳐요 :」)
        t0_ = r["text"]
        # 줄 앞뒤 문장부호: 뺀 것·짝 따옴표를 채운 것을 같은 글꼴로 그려 겹쳐 보고 가장 잘 맞는 것을 고른다
        # (글자 인식 결과만 보고 빼면 진짜 따옴표까지 빠짐 — df6jENnHjOE 「역전 '금빛섬광'」의 끝 따옴표가 빠져 「광」 상자가 12px 넓어짐)
        # 따옴표가 아닌 부호(:;, 등)는 전처럼: 다른 글자 인식·제목·태그·설명란 어디에도 없으면 잡티로 뺌(JA5roRAtF7c 「…도망쳐요 :」)
        seen_ = "".join(x for x in (rd.get("win_ocr") or []) if x) + (src_text or "")
        while r["text"] and r["text"][-1] in ":;,.·-_|`~" and r["text"][-1] not in seen_: r["text"] = r["text"][:-1].rstrip()
        while r["text"] and r["text"][0] in ":;,.·-_|`~" and r["text"][0] not in seen_: r["text"] = r["text"][1:].lstrip()
        t1_ = r["text"]; QS = "'\"‘’“”"
        cs_ = [t1_]; t_ = t1_
        while t_ and t_[-1] in QS: t_ = t_[:-1].rstrip(); cs_.append(t_)
        t_ = t1_
        while t_ and t_[0] in QS: t_ = t_[1:].lstrip(); cs_.append(t_)
        for q in ("'", '"', "‘", "’", "“", "”"):
            if t1_.endswith(q) and t1_.count(q) == 1:
                ws_ = [i + 1 for i, ch in enumerate(t1_) if ch == " "]
                cs_ += [t1_[:i] + q + t1_[i:] for i in [0] + ws_]
        # 둥근 따옴표(‘ ’ “ ”)도 그려 본다(df6jENnHjOE 원본은 ‘금빛섬광’) · 줄 끝에 글자 인식이 놓친 ! ? 가 있을 수 있다(KXjpoqbodRc 「체크!」)
        for x in list(cs_):
            if x.count("'") == 2: i_ = x.index("'"); j_ = x.rindex("'"); cs_.append(x[:i_] + "‘" + x[i_ + 1:j_] + "’" + x[j_ + 1:])
            if x.count('"') == 2: i_ = x.index('"'); j_ = x.rindex('"'); cs_.append(x[:i_] + "“" + x[i_ + 1:j_] + "”" + x[j_ + 1:])
        if t1_ and t1_[-1] not in "!?":
            cs_ += [t1_ + "!", t1_ + "?"]
        cs_ = [x for x in dict.fromkeys(cs_) if nospace(x)]
        if len(cs_) > 1:
            sc_ = sorted(((score_text(w["c"], x, F), x) for x in cs_), key=lambda z: -z[0])
            base_ = next(v for v, x in sc_ if x == t1_)
            if sc_[0][1] != t1_ and sc_[0][0] > base_ + (0.02 if sc_[0][1][:-1] == t1_ else 0.005): r["text"] = sc_[0][1]   # 끝 부호 덧붙이기는 더 뚜렷해야
            r["read3"]["punct"] = [dict(text=x, score=round(v, 3)) for v, x in sc_[:5]]
        if r["text"] != t0_:
            log.append(f"「{t0_}」 줄 앞뒤 문장부호를 모양으로 고침 → 「{r['text']}」"); r["_chars"] = list(r["text"])
        if not nospace(r["text"]):   # 부스러기(「-」 등)를 문장부호로 지우고 나니 빈 줄 — 글꼴을 그릴 글자가 없으니 건너뜀(2026-11-24 롱폼 시험 「캐나다 이웃 부대찌개 반응」 오류)
            log.append(f"「{t0_}」 줄은 문장부호만 있어 지우고 나니 비어서 건너뜀"); continue
        # Claude가 원본을 보고 적은 정답 줄(값/글자고르기.json 「정답줄」) — 읽은 줄과 가장 닮은 정답(0.5 넘게)으로 바꾼다.
        # 읽기 틀린 글자를 그대로 그리지 않기 위해(운영자 2026-11-24 「다른 글자가 들어가 있는데」 — 03JG 260억→600억·챙긴→생긴)
        ans_ = overrides(out, vid).get("정답줄") or []
        if ans_:
            sim_ = sorted(((difflib.SequenceMatcher(None, nospace(r["text"]), nospace(x_)).ratio(), x_) for x_ in ans_), reverse=True)
            # 정답 줄이 있는데 어느 정답과도 닮지 않은 줄(0.5 미만)은 깨진 읽기·장면 글자 — 그리지 않는다.
            # 이미 앞 줄이 가져간 정답에만 닮은 줄도 같은 글자를 두 번 그리게 되므로 버린다
            # (2026-11-25 「전세계가 빚더미인데…」 썸네일: 「좋(미국01 교`1`」·「저入H [[」를 줄로 잡아 글꼴 찾기에 각 70초 넘게 씀, 실측)
            if sim_[0][0] < 0.5 or any(t_[0].get("text") == sim_[0][1] for t_ in pend):
                log.append(f"「{r['text']}」 줄은 Claude 정답 줄에 없어(가장 닮은 「{sim_[0][1]}」 {sim_[0][0]:.2f}{', 이미 그린 줄' if sim_[0][0] >= 0.5 else ''}) 건너뜀"); continue
            if sim_[0][1] != r["text"]:
                before_ = r["text"]
                log.append(f"Claude 정답 줄로 고침: 「{r['text']}」 → 「{sim_[0][1]}」(닮음 {sim_[0][0]:.2f})"); r["text"] = sim_[0][1]; r["_chars"] = list(r["text"])
                r.setdefault("read3", {}); r["read3"]["claude"] = r["text"]
                # 대책(2026-11-24 「얀코스」를 「안코스」로 잘못 적은 일): Claude 정답 글자 중 어느 글자 인식·영상 제목/설명에도 2자 넘게 이어 맞지 않는 글자는
                # 「다시 볼 글자」로 적는다 — Claude가 키운 그림으로 다시 확인한 뒤에만 정답으로 믿는다
                rd0 = r.get("read3") or {}
                srcs_ = [before_, rd0.get("first"), src_text] + list(rd0.get("win_ocr") or []) + list(rd0.get("_cands") or [])[:5]
                ok_ = confirm(r["text"], srcs_)
                rv_ = "".join(ch for ch, o in zip(nospace(r["text"]), ok_) if not o)
                r["read3"]["claude_recheck"] = rv_
                if rv_: log.append(f"다시 볼 글자(Claude 정답이 글자 인식·제목과 엇갈림): 「{r['text']}」의 {rv_}")
            else:
                r.setdefault("read3", {}); r["read3"]["claude"] = r["text"]
        for k_, v_ in (overrides(out, vid).get("고쳐읽기") or {}).items():
            if nospace(k_) == nospace(r["text"]) and v_ != r["text"]:
                log.append(f"Claude가 그림을 보고 고쳐 읽음: 「{r['text']}」 → 「{v_}」"); r["text"] = v_; r["_chars"] = list(v_)
                r.setdefault("read3", {}); r["read3"]["claude"] = v_
        parts = split_runs(r, F, w, log)
        for pi, (r_, F_) in enumerate(parts): pend.append((r_, F_, pi, len(parts), w))
    # 제목 글꼴은 「효과가 가장 적고 글자가 가장 많은」 제목 줄에서 먼저 찾는다(운영자 2026-11-25) — 테두리·기울기 없는 줄, 글자 수 × 글자 높이가 큰 줄.
    # 그 줄을 맨 앞에 두면 아래 「제목줄」 처리가 그 줄 글꼴 하나로 나머지 제목 줄을 맞춘다. 전에는 먼저 읽힌 줄(대개 맨 위)로 정해
    # 「전세계가 빚더미인데…」 둘째 줄이 나빠짐(최소 0.77, 실측 2026-11-25)
    titles0_ = [nospace(x_) for x_ in (titles_for(out, vid) or [])]
    def clean_(t_):
        r_, F_ = t_[0], t_[1]
        if not in_titles(r_["text"], titles0_): return -1
        # 글자 수는 글자(한글·영문·숫자)만 센다 — 따옴표·말줄임표 같은 부호는 모양 견주기에서 0점이 나와 글꼴 찾기를 망침
        # (2026-11-25 「배구 일본반응」 「“어디서도 연락 안 왔는데…”」를 골라 최소 0.0, 실측)
        k_ = sum(ch.isalnum() for ch in r_["text"]) * max(1, int(F_.any(1).sum()))
        if r_.get("outline"): k_ *= 0.5
        if abs(T2.slant_of(F_)) > 0.05: k_ *= 0.7
        return k_
    # 짐작(테두리 잡힘 여부) 대신 실제로 잰다: 제목 줄마다 글자 모양 견주기를 미리 돌려 1등 점수가 가장 높은 줄 = 글자가 가장 깨끗하게
    # 잘린 줄(테두리·그림자·잡티가 덜 섞인 줄)을 기준 줄로 한다. 저장한 글자 모양을 쓰므로 줄마다 1~2초.
    # (2026-11-25 「배구 일본반응」: 흰 줄은 남색 테두리를 못 잡아 모양이 지저분(1등 0.84)한데 짐작으로 기준 줄이 됨 — 노란 줄은 0.97, 실측)
    # 기준 줄 후보는 제목의 주된 글자(한글이 있으면 한글)가 들어 있고, 글자 수가 가장 많은 줄의 절반 이상인 줄만.
    # 글자가 적고 단순한 줄(영문·숫자 몇 자)은 모양 점수만 높게 나와 한글 제목 글꼴을 못 가름
    # (2026-11-25 「바가지 관광지 TOP7」 「TOP7」 4자가 0.990으로 기준 줄이 됨, 실측)
    def _hang(s_): return sum('가' <= ch <= '힣' for ch in s_)
    _hmax = max([_hang(t_[0]["text"]) for t_ in pend] or [0])
    _nmax = max([sum(ch.isalnum() for ch in t_[0]["text"]) for t_ in pend] or [0])
    def clean_score_(t_):
        if clean_(t_) <= 0: return -1.0
        n_ = sum(ch.isalnum() for ch in t_[0]["text"])
        if (_hmax and _hang(t_[0]["text"]) == 0) or n_ * 2 < _nmax: return -1.0
        r_, F_, w_ = t_[0], t_[1], t_[4]
        ch_ = r_["_chars"]
        try:
            import tt_glyphrank as GR
            cands_ = [c for c in FID.pool_fonts() if FID.covers(c[3], ch_)]
            _w = T2.fit_line(ch_, F_, [])[0]
            rk_ = GR.rank(ch_, F_, cands_, (_w["c"], _w["p"]), None)
            return rk_[0][0] if rk_ else 0.0
        except Exception: return 0.0
    if titles0_ and len(pend) > 1:
        t_s = time.time(); cs_ = [clean_score_(t_) for t_ in pend]
        log.append(f"기준 줄 고르기(글자 모양 1등 점수 = 글자가 깨끗하게 잘린 정도, {time.time() - t_s:.0f}초): " + " · ".join(f"「{t_[0]['text']}」 {c_:.3f}" for t_, c_ in zip(pend, cs_)))
        a_ = max(range(len(pend)), key=lambda j: (cs_[j], clean_(pend[j])))
        if cs_[a_] > 0:
            log.append(f"제목 글꼴을 찾을 줄: 「{pend[a_][0]['text']}」(글자가 가장 깨끗하게 잘린 줄)")
            pend.insert(0, pend.pop(a_))
    for r, F, pi, nparts_, w in pend:
        X0, Y0, X1, Y1 = r["_crop"]
        os.makedirs(os.path.join(out, "그림"), exist_ok=True)
        np.save(os.path.join(out, "그림", f'{vid}_채움_{len(L)}_{pi}.npy'), F)   # 글꼴 대조(나란히 재기)용 원본 채움
        # Claude가 그림을 보고 고른 비슷한 글꼴 후보(값/글자고르기.json 「눈후보」 {줄 글자: [글꼴 이름...]}) — 산돌 후보 앞에 둔다.
        # 맞는지는 아래에서 똑같이 재서 1.00이어야 찾음(눈으로 고른 이름을 그대로 믿지 않음)
        eye_ = next((v_ for k_, v_ in (overrides(out, vid).get("눈후보") or {}).items() if nospace(k_) == nospace(r["text"])), [])
        eyl = sandoll_local(eye_, r["_chars"]) if eye_ else []
        if eye_: log.append(f"Claude 눈 후보 {len(eye_)}개 중 이 PC에 있는 글꼴 {len(eyl)}개: " + ", ".join(c[0] for c in eyl[:6]))
        sdl = eyl + [c for c in sandoll_local(r.get("sandoll") or [], r["_chars"]) if c not in eyl]
        if r.get("sandoll"): log.append(f"산돌 후보 중 이 PC에 있는 글꼴 {len(sdl)}개: " + ", ".join(c[0] for c in sdl[:5]))
        # 같은 썸네일 앞 줄에서 확정된 글꼴도 빠른 후보로(제목 두 줄이 같은 글꼴인 경우가 많음)
        prev = [x["_c"] for x in L if x.get("font2", {}).get("confirmed")]
        force_ = next((v_ for k_, v_ in (overrides(out, vid).get("글꼴정하기") or {}).items() if nospace(k_) == nospace(r["text"])), None)
        # 제목 하나 = 글꼴 하나(운영자 2026-11-24): 값/글자고르기.json 「제목줄」에 든 줄은 앞의 제목 줄이 고른 글꼴 하나로만 맞춘다
        titles_ = [nospace(x_) for x_ in (titles_for(out, vid) or [])]
        tfont_ = next(((x["font2"]["best"], x["font2"].get("file")) for x in L if in_titles(x.get("text", ""), titles_) and x.get("font2")), None) if in_titles(r["text"], titles_) and not force_ else None
        fid = FID.identify(r["_chars"], F, log, prefer=[tuple(c) for c in FID.prefer_list()], fast=None if (force_ or tfont_) else ((sdl + [tuple(c) for c in prev]) or None), force=force_, only=tfont_,
                           need=[ch for x_ in (titles_for(out, vid) or []) for ch in x_ if not ch.isspace()] if (in_titles(r["text"], titles_) and not tfont_) else None)
        # 숫자·영문만 있는 덩어리는 제목 글꼴로 안 맞으면 전체 글꼴에서 따로 찾고 더 잘 맞는 쪽을 쓴다(운영자 2026-11-25 「숫자만 따로 찾기 허용」).
        # 한글은 그대로 제목 글꼴 하나. (조니 뎁 편 「260」: 페이퍼로지 굵기 9개 모두 최소 0.72~0.76, 숫자만 찾으면 0.915 — 실측·눈으로 봄)
        if tfont_ and not fid.get("confirmed") and not any('가' <= ch <= '힣' for ch in r["_chars"]) and any(ch.isalnum() for ch in r["_chars"]):
            fid2 = FID.identify(r["_chars"], F, log, prefer=[tuple(c) for c in FID.prefer_list()], fast=(sdl or None))
            if fid2["best"]["gmean"] > fid["best"]["gmean"]:
                log.append(f"「{r['text']}」 숫자·영문 덩어리는 제목 글꼴({fid['best']['c'][0]} 평균 {fid['best']['gmean']})보다 {fid2['best']['c'][0]}(평균 {fid2['best']['gmean']})가 잘 맞아 그 글꼴로 그림(운영자 허용 — 숫자만 따로)")
                fid = fid2
            else:
                log.append(f"「{r['text']}」 숫자·영문만 따로 찾아도 제목 글꼴이 더 잘 맞음 — 제목 글꼴 그대로")
        # 글꼴로 다시 읽기: 1등 글꼴로 읽기 후보를 다시 그려 겹쳐 보고, 지금 글자보다 뚜렷이(0.02 넘게) 잘 맞는 후보가 있으면
        # 그 글자로 바꿔 글꼴을 다시 찾는다(글자 인식끼리 엇갈리고 제목에도 없을 때 — JA5roRAtF7c 2줄)
        if not fid["confirmed"] and not (r.get("read3") or {}).get("claude") and (r.get("read3") or {}).get("_cands") and nparts_ == 1:   # Claude 정답이 있으면 글꼴로 다시 읽기를 하지 않음(JA5r 「어떻게 혼자도망쳐요」→「이떻게 원자 도항치요」로 나빠짐)
            bc = fid["best"]["c"]; cur = score_text(bc, r["text"], F, rounds=20); alt = None
            for t in r["read3"]["_cands"]:
                if nospace(t) == nospace(r["text"]): continue
                sc_ = score_text(bc, t, F, rounds=20)
                if sc_ > cur + 0.02 and (alt is None or sc_ > alt[0]): alt = (sc_, t)
            if alt:
                log.append(f"글꼴 {bc[0]}로 다시 읽음: 「{r['text']}」({cur:.3f}) → 「{alt[1]}」({alt[0]:.3f})")
                r["text"] = alt[1]; r["_chars"] = list(r["text"]); r["read3"]["reread"] = dict(font=bc[0], before=round(cur, 3), after=round(alt[0], 3), text=alt[1])
                fid = FID.identify(r["_chars"], F, log)
        b = fid["best"]; w = dict(c=b["c"], p=b["p"], s=b["iou"])
        r["_c"], r["_p"] = w["c"], w["p"]; r["_size"] = w["p"]["size"]; r["_e"] = w["p"]["e"]
        r["font2"] = dict(best=b["c"][0], file=os.path.basename(b["c"][1]), weight=b["c"][2], score=b["gmean"], gmin=b["gmin"],
                          confirmed=fid["confirmed"], why=fid["why"], gap=fid["gap"], glyphs=b["glyphs"],
                          second=(dict(name=fid["second"]["c"][0], score=fid["second"]["gmean"]) if fid["second"] else None),
                          top=[dict(name=t["name"], score=t["gmean"], gmin=t["gmin"]) for t in fid["top"]], tried=fid["tried"], secs=fid["secs"])
        r["_G"] = model_from_fit(r)
        # 테두리
        fill_r = T2.raster(T2.layout(w["c"], r["_chars"], w["p"]), F.shape, w["p"]["e"])
        r["_ow"] = None
        U = r["_uni"]; O = U & ~T2.grow(F, 1.0)
        if r.get("outline") and O.sum() >= 5:
            ow, _ = T2.fit_outline(fill_r, U)
            dto = cv2.distanceTransform(O.astype(np.uint8), cv2.DIST_L2, 5)
            Oc = O & (dto >= max(1.0, 0.45 * float(dto.max())))
            C = im[Y0:Y1, X0:X1].astype(np.float32); oc = np.median(C[Oc if Oc.sum() >= 3 else O], 0)
            if ow >= 1.0 and dE(oc, T._hex2bgr(r["bg_color"])) >= 12:
                r["_ow"] = ow; r["_oc"] = hexc(oc); r["_Ocore_full"] = (Oc if Oc.sum() >= 3 else O)
        # 색(글자마다 안쪽 → 같은 색 묶음)
        _, idm = T2.raster(T2.layout(w["c"], r["_chars"], w["p"]), F.shape, w["p"]["e"], ids=True)
        gmap = T2.glyph_assign(F, idm)
        r["_spans"] = T2.colors(im[Y0:Y1, X0:X1].astype(np.float32), F, gmap, r["_chars"])
        if not r["_spans"]:
            r["_spans"] = [dict(color="#FFFFFF", grad=None, i0=0, i1=len(r["_chars"]) - 1, chars=r["text"], _m=F)]
        r["_ink_y"] = (r["ink"][1], r["ink"][3])
        L.append(r)
    # 한 줄을 덩어리로 나눴는데 어느 덩어리가 동점으로 못 정해졌고, 그 1등이 같은 줄 다른 덩어리에서 확정된 글꼴과 모양이 같으면
    # 「같은 줄과 같은 글꼴」로 확정한다(M7QfZAVX61A 「NEON」: 도현·KBL 점프체 동점, 같은 줄 「제이블랙」 = 도현 확정)
    for r in L:
        f = r["font2"]
        if f.get("confirmed") or f.get("gmin", 0) < FID.CONFIRM_GLYPH: continue
        for o in L:
            if o is r or o["_crop"] != r["_crop"] or not o["font2"].get("confirmed"): continue
            try: same = FID.same_shape(r["_c"], o["_c"], r["_chars"]) >= 1.0
            except Exception: same = False
            if same:
                f["confirmed"] = True; f["why"] = None; f["by_line"] = o["font2"]["best"]
                log.append(f"「{r['text']}」 모양 동점이지만 같은 줄 「{o['text']}」에서 확정된 {o['font2']['best']}와 같은 글꼴이라 확정")
                break
    L.sort(key=lambda r: r["ink"][1])
    Gd = os.path.join(out, "그림"); RD = os.path.join(out, "재현"); os.makedirs(Gd, exist_ok=True); os.makedirs(RD, exist_ok=True)
    imwrite(os.path.join(Gd, f"{vid}_원본.png"), im)
    # 원본 채움·채움+테두리 (그림 전체 좌표)
    OF = np.zeros((H, W), bool); OU = np.zeros((H, W), bool)
    for r in L:
        X0, Y0, X1, Y1 = r["_crop"]; OF[Y0:Y1, X0:X1] |= r["_F"]; OU[Y0:Y1, X0:X1] |= (r["_uni"] | r["_F"])
    # 배경: 타이틀 줄만 지운다(그림 속 다른 글자는 그대로 둔다)
    mask = np.zeros((H, W), np.uint8)
    for r in L:
        X0, Y0, X1, Y1 = r["_crop"]; u = (r["_uni"] | r["_F"]).astype(np.uint8) * 255
        sh = r.get("shadow")
        if sh: u = np.maximum(u, np.roll(np.roll(u, sh["dy"], 0), sh["dx"], 1))
        mask[Y0:Y1, X0:X1] = np.maximum(mask[Y0:Y1, X0:X1], u)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    bgim = cv2.inpaint(im, mask, 5, cv2.INPAINT_TELEA); imwrite(os.path.join(Gd, f"{vid}_배경.png"), bgim)
    bgurl = f"../그림/{vid}_배경.png"
    keys = [li * 1000 + gi for li, r in enumerate(L) for gi in range(len(r["_G"]))]
    load_paths(L)
    # 원본 글자 상자(처음 모형으로 나눔) → 바로 그 상자에 맞춰 놓고 시작
    idm0 = raster_model(L, (H, W)); go0 = assign_blobs(OF, idm0)
    bo = sp_boxes(alpha_orig(im, OF, go0, L, keys), go0, keys); BO = dict(bo)
    # ---- 되풀이: Chrome으로 그림 → 선 재기 → 고치기 ----
    hist = []; best = None; stall = 0; delta = {}
    for rd in range(1, max_rounds + 1):
        RA, gr = decode_ids(shoot(im, L, bgurl, "ids", RD, Gd, vid), L); RF = RA > 0.5
        gr = near_only(gr, RA, L, (H, W))
        bo = BO; br = sp_boxes(RA, gr, keys)
        ln = lines_of(L, bo, br)
        mx = max((abs(d["d"]) for d in ln if not d.get("touch")), default=99); mean = float(np.mean([abs(d["d"]) for d in ln])) if ln else 99
        # 굵기: 원본·재현 획 두께(글자 안쪽 거리)
        strokes = []
        for li, r in enumerate(L):
            X0, Y0, X1, Y1 = r["_crop"]
            so = T.stroke_w(OF[Y0:Y1, X0:X1]); sr = T.stroke_w(RF[Y0:Y1, X0:X1] & T2.grow(OF[Y0:Y1, X0:X1], 3))
            strokes.append((so, sr))
        hist.append(dict(round=rd, max=mx, mean=round(mean, 2), strokes=[(round(a or 0, 2), round(b or 0, 2)) for a, b in strokes]))
        log.append(f"되풀이 {rd}: 선 최대 {mx}px · 평균 {mean:.2f}px")
        state = (mx, mean)
        if best is None or state < best[0]:
            best = (state, [[dict(g) for g in r["_G"]] for r in L], [r["_e"] for r in L], [r.get("_ow") for r in L], ln); stall = 0
        else: stall += 1
        if mx == 0 or stall >= 5: break
        # 고치기: Chrome과 PIL 모형의 차이(δ)를 빼고 원본 상자에 다시 맞춘다
        for li, r in enumerate(L):
            so, sr = strokes[li]
            if so and sr and rd <= 3: r["_e"] = float(np.clip(r["_e"] + (so - sr) / 2 * 0.8, 0, 6))
            ks = [li * 1000 + gi for gi in range(len(r["_G"])) if li * 1000 + gi in bo and li * 1000 + gi in br]
            if not ks: continue
            # 줄 하나의 가로·세로 비율: 글자 너비·높이 비(원본/재현)의 가운데값 — 모든 글자에 같게(글자마다 늘리지 않음)
            fx = float(np.median([(bo[k][1] - bo[k][0]) / max(1e-3, br[k][1] - br[k][0]) for k in ks]))
            fy = float(np.median([(bo[k][3] - bo[k][2]) / max(1e-3, br[k][3] - br[k][2]) for k in ks]))
            for gi, g in enumerate(r["_G"]):
                k = li * 1000 + gi
                if k not in bo or k not in br: continue
                # Chrome이 그린 끝 = 자리 + 글꼴 속 끝 × 비율 → 글꼴 속 끝을 거꾸로 풀고, 새 비율로 가운데가 원본 가운데에 오게 자리만 옮긴다
                Lr, Rr, Tr, Br = br[k]; Lo, Ro, To, Bo = bo[k]
                l = (Lr - g["x"]) / g["sx"]; rr = (Rr - g["x"]) / g["sx"]; t = (Tr - g["y"]) / g["sy"]; b = (Br - g["y"]) / g["sy"]
                g["sx"] = float(np.clip(g["sx"] * fx, 0.7, 1.4)); g["sy"] = float(np.clip(g["sy"] * fy, 0.7, 1.4))
                g["x"] = (Lo + Ro) / 2 - (l + rr) / 2 * g["sx"]; g["y"] = (To + Bo) / 2 - (t + b) / 2 * g["sy"]
    # 가장 좋았던 모형으로 되돌림
    (_, _), Gs, Es, Ows, ln = best
    for r, Gm, e, ow in zip(L, Gs, Es, Ows): r["_G"] = Gm; r["_e"] = e; r["_ow"] = ow
    # 테두리 두께: 채움+테두리 바깥 끝을 맞춘다
    ohist = []
    for _ in range(3):
        if not any(r.get("_ow") for r in L): break
        RU = shoot(im, L, bgurl, "union", RD, Gd, vid).max(2) > 127
        ch = False
        for r in L:
            if not r.get("_ow"): continue
            X0, Y0, X1, Y1 = r["_crop"]
            a = OU[Y0:Y1, X0:X1]; b = RU[Y0:Y1, X0:X1] & T2.grow(a, 4)
            # 바깥 끝까지의 평균 거리 차이: 넓이 차이 / 둘레 길이
            per = max(1, int((cv2.dilate(a.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0).sum() - a.sum()))
            d = (b.sum() - a.sum()) / per
            ohist.append(round(float(d), 2))
            if abs(d) > 0.3: r["_ow"] = float(max(0.5, r["_ow"] - d)); ch = True
        if not ch: break
    # 색: 원본 안쪽 색과 재현 색 차이만큼 고쳐 다시 — 재현은 압축하지 않은 그림 그대로 견줌(운영자 2026-11-24 「압축 안 하면 되잖아」),
    # #RRGGBB가 똑같아질 때까지(허용 범위 없음)
    chist = []
    for cr in range(10):
        rep = shoot(im, L, bgurl, "color", RD, Gd, vid)
        worst = -99; cols = []
        if cr == 0: imq = jpeg_like(im, path)   # 원본을 같은 JPEG으로 한 번 더 압축한 것 — 압축만으로 생기는 색 흔들림
        for li, r in enumerate(L):
            X0, Y0, X1, Y1 = r["_crop"]
            Co = im[Y0:Y1, X0:X1].astype(np.float32); Cr = rep[Y0:Y1, X0:X1].astype(np.float32); Cq = imq[Y0:Y1, X0:X1].astype(np.float32)
            drift = lambda m_: dE(np.median(Co[m_], 0), np.median(Cq[m_], 0))
            for s in r["_spans"]:
                cm = T2.core_of(s["_m"])
                if cm.sum() < 3: continue
                a, b = np.median(Co[cm], 0), np.median(Cr[cm], 0); d = dE(a, b)
                noise = max(1.0, float(np.median(np.linalg.norm(lab(Co[cm]) - lab(np.array([a]))[0], axis=1)))) + drift(cm)
                cols.append(dict(line=li, what=f'{li+1}줄 채움 「{s["chars"]}」', o=hexc(a), r=hexc(b), dE=round(d, 1), noise=round(noise, 1))); worst = max(worst, d)
                if hexc(a) != hexc(b) and not s.get("grad"):
                    s["color"] = hexc(np.clip(np.array(T._hex2bgr(s["color"]), np.float32) + (a - b), 0, 255))
                if s.get("grad"):
                    ys = np.where(cm)[0]
                    for key, sel in (("start", ys <= np.percentile(ys, 20)), ("end", ys >= np.percentile(ys, 80))):
                        mm = np.zeros_like(cm); idx = np.where(cm); mm[idx[0][sel], idx[1][sel]] = True
                        if mm.sum() >= 3:
                            a2, b2 = np.median(Co[mm], 0), np.median(Cr[mm], 0); d2 = dE(a2, b2)
                            n2 = max(1.0, float(np.median(np.linalg.norm(lab(Co[mm]) - lab(np.array([a2]))[0], axis=1)))) + drift(mm)
                            cols.append(dict(line=li, what=f'{li+1}줄 그라데이션 {"위" if key=="start" else "아래"}', o=hexc(a2), r=hexc(b2), dE=round(d2, 1), noise=round(n2, 1))); worst = max(worst, d2)
                            if hexc(a2) != hexc(b2): s["grad"][key] = hexc(np.clip(np.array(T._hex2bgr(s["grad"][key]), np.float32) + (a2 - b2), 0, 255))
            if r.get("_ow") and r.get("_Ocore_full") is not None:
                oc = r["_Ocore_full"]
                if oc.sum() >= 3:
                    a, b = np.median(Co[oc], 0), np.median(Cr[oc], 0); d = dE(a, b)
                    noise = max(1.0, float(np.median(np.linalg.norm(lab(Co[oc]) - lab(np.array([a]))[0], axis=1)))) + drift(oc)
                    cols.append(dict(line=li, what=f"{li+1}줄 테두리", o=hexc(a), r=hexc(b), dE=round(d, 1), noise=round(noise, 1))); worst = max(worst, d)
                    if hexc(a) != hexc(b): r["_oc"] = hexc(np.clip(np.array(T._hex2bgr(r["_oc"]), np.float32) + (a - b), 0, 255))
        chist.append(round(worst, 1))
        if all(c["o"] == c["r"] for c in cols) or (len(chist) >= 4 and chist[-1] >= chist[-4]): break
    final_cols = cols
    # 마지막으로 고친 색으로 한 번 더 찍은 그림이 위의 rep — 색표는 그 그림에서 잰 값
    rep = imread(os.path.join(Gd, f"{vid}_재현.png"))   # 압축하지 않은 재현 그대로(견주기·화면 모두)
    RA, gr_ = decode_ids(shoot(im, L, bgurl, "ids", RD, Gd, vid), L); RF = RA > 0.5
    gr_ = near_only(gr_, RA, L, (H, W))
    idm = raster_model(L, (H, W))
    bo = BO; br = sp_boxes(RA, gr_, keys)
    ln = lines_of(L, bo, br)
    # 글자마다 모양 겹침
    go = assign(OF, idm0); gr = np.where(RF, gr_, -1); gl = []
    for li, r in enumerate(L):
        for gi, g in enumerate(r["_G"]):
            k = li * 1000 + gi; a = go == k; b = gr == k
            u = (a | b).sum(); gl.append(dict(line=li, ch=g["ch"], iou=round(float((a & b).sum() / u), 3) if u else 0.0))
    # 차이 그림
    imwrite(os.path.join(Gd, f"{vid}_차이.png"), T2.diff_image(im, rep, (OF, RF)))
    mx = max((abs(d["d"]) for d in ln if not d.get("touch")), default=99); cmax = max((c["dE"] for c in final_cols), default=99)
    cover = max((c["dE"] - c.get("noise", 0) for c in final_cols), default=99)
    gmin = min((g["iou"] for g in gl), default=0)
    reads = []
    for r in L:
        rd = r.get("read3") or {}
        ok = confirm(r["text"], [x for x in (rd.get("win_ocr") or [])] + [rd.get("first"), rd.get("read") if rd.get("chosen") else None, src_text, rd.get("claude")])
        t = nospace(r["text"])
        # 글꼴이 확정된 줄은, 확정 글꼴로 그린 그 글자가 원본과 1.00으로 겹치면 글자도 맞은 것으로 본다(허용 범위 없음)(YlzIy1udFfw 「깐」)
        gs = r["font2"].get("glyphs") or []
        if r["font2"].get("confirmed") and len(gs) == len(t):
            ok = [o or (gs[i][1] >= 1.0) for i, o in enumerate(ok)]
        reads.append(dict(text=r["text"], unconfirmed="".join(ch for ch, o in zip(t, ok) if not o), changed=bool(rd.get("chosen"))))
    read_ok = all(not x["unconfirmed"] for x in reads)
    res = dict(video_id=vid, canvas=[W, H], lines_max_px=mx, color_max_dE=cmax, glyph_min_iou=gmin,
               font_confirmed=all(r["font2"]["confirmed"] for r in L),
               passed=bool(all(r["font2"]["confirmed"] for r in L) and mx == 0 and all(c["o"].upper() == c["r"].upper() for c in final_cols) and read_ok and gmin >= GLYPH_PASS), color_over_noise=round(cover, 1), read_ok=read_ok, reads=reads,
               scale=dict(src=os.path.basename(path), size=f"{W}x{H}", zoom="1:1(늘리거나 줄이지 않음)", unit="0.01px(가장자리 반쯤 칠해진 화소로 잼, 반올림 봐주기 없음 · 전에는 0.25px 단위 = 4배 확대와 같은 정밀도)"),
               grid=ln, colors=final_cols, glyphs=gl, rounds=hist, outline_rounds=ohist, color_rounds=chist, log=log, secs=round(time.time() - t0),
               lines=[dict(text=r["text"], role=r["role"], read3=r.get("read3"), font=r["font2"], size_px=round(r["_size"], 2),
                           size_1080=round(r["_size"] * 1920 / H, 1), slant=round(float(r["_p"].get("sh", 0.0)), 3), width_ratio=round(float(r["_p"].get("hs", 1.0)), 3),
                           spacing_px=round(float(r["_p"].get("ls", 0.0)), 2), bold_px=round(r["_e"], 2), outline_px=round(r["_ow"], 2) if r.get("_ow") else 0,
                           outline_color=r.get("_oc") if r.get("_ow") else None, shadow=r.get("shadow"), back=r["back"], bg_color=r["bg_color"],
                           spans=[{k: v for k, v in s.items() if k != "_m"} for s in r["_spans"]],
                           glyphs=[dict(ch=g["ch"], x=round(g["x"], 2), y=round(g["y"], 2), sx=round(g["sx"], 3), sy=round(g["sy"], 3)) for g in r["_G"]])
                      for r in L])
    why = []
    for r in L:
        if not r["font2"]["confirmed"]:
            why.append(f'「{r["text"]}」 글꼴 못 찾음 — 가장 가까운 {r["font2"]["best"]} 글자 겹침 평균 {r["font2"]["score"]}·최소 {r["font2"]["gmin"]} ({r["font2"]["why"]}), 후보 {r["font2"]["tried"]}개')
    if mx > 0:
        worst = sorted([d for d in ln if not d.get("touch")], key=lambda d: -abs(d["d"]))[:3]
        why.append("선 어긋남 남음: " + ", ".join(f'{d["name"]} {d["d"]:+.0f}px' for d in worst))
    if any(c["o"].upper() != c["r"].upper() for c in final_cols): why.append("색 #RRGGBB 다름: " + ", ".join(f'{c["what"]} {c["o"]}→{c["r"]}' for c in final_cols if c["o"].upper() != c["r"].upper())[:300])
    if not read_ok:
        why.append("다른 출처로 확인 못 한 글자: " + ", ".join(f'「{x["text"]}」의 {x["unconfirmed"]}' for x in reads if x["unconfirmed"]))
    res["why"] = why
    json.dump(res, open(os.path.join(out, "값", f"{vid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True); ap.add_argument("--img-dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--list", required=True); ap.add_argument("--only"); ap.add_argument("--skip-done", action="store_true"); ap.add_argument("--org", default="thumbtitle")
    a = ap.parse_args()
    for d in ("값", "그림", "재현"): os.makedirs(os.path.join(a.out, d), exist_ok=True)
    meta = {v["id"]: v for v in json.load(open(a.list, encoding="utf-8"))["vids"]}
    ids = [l.split("\t")[0].strip() for l in open(a.ids, encoding="utf-8-sig") if l.strip()]
    ids = [v for v in ids if v and v != "video_id"]
    if a.only: ids = [v for v in ids if v in a.only.split(",")]
    if a.skip_done: ids = [v for v in ids if not os.path.exists(os.path.join(a.out, "값", f"{v}.json"))]
    for vid in ids:
        T2.wait_mem()
        tall = glob.glob(os.path.join(os.path.dirname(a.img_dir.rstrip("/\\")), "thumbs_세로", "*", vid + ".jpg"))   # 세로 원본 크기 표지(oardefault, Research가 받은 크기 그대로) 먼저
        p = tall + glob.glob(os.path.join(a.img_dir, "*", vid + ".jpg")) + glob.glob(os.path.join(a.img_dir, vid + ".jpg"))
        if not p: print(f"{vid}: 그림 없음", flush=True); continue
        m = meta.get(vid, {}); src = " ".join([m.get("t", ""), " ".join(eval(m["g"]) if isinstance(m.get("g"), str) and m["g"].startswith("[") else (m.get("g") or [])), m.get("d", "")])
        class _Log(list):   # 단계마다 바로 찍어 진행이 보이게(운영자 2026-11-24 「제대로 확인도 안 하고 대충 이만큼 걸려요만」)
            t0 = time.time()
            def append(self, x):
                super().append(x); print(f"  [{vid[:4]} +{time.time() - self.t0:5.0f}초] {str(x)[:150]}", flush=True)
                _status(a.out, vid, str(x)[:200], time.time() - self.t0)
        log = _Log()
        _status(a.out, vid, "시작", 0.0)
        try:
            r = run_one(vid, p[0], a.out, src, log)
            print(f"{vid}: {'통과' if r['passed'] else '못 통과'} · 선 최대 {r['lines_max_px']}px · 색 차이 {r['color_max_dE']} · 글자 겹침 최소 {r['glyph_min_iou']} · "
                  f"{' / '.join(l['text'] for l in r['lines'])} · {r['secs']}초 · {' | '.join(r['why'])}", flush=True)
            _status(a.out, vid, "끝", r.get("secs", 0), done="끝")
        except Exception as e:
            import traceback; traceback.print_exc(); print(f"{vid}: 오류 — {e}", flush=True)
            _status(a.out, vid, f"오류 — {e}", 0.0, done="오류")
        # 한 장 끝날 때마다 비교 화면(비교.html)을 최신으로 다시 만든다(운영자 2026-11-24: 화면이 늦게 바뀌어 헷갈림)
        try:
            import subprocess
            try: subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_measure_cmp.py"), a.out, "--only", vid], timeout=300)   # 원본·재현 실측 견주기
            except Exception as ex: print("실측 견주기 실패:", ex)
            try: subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_verify.py"), a.out, "--cross", vid], timeout=600)   # 독립 검수(만든 쪽 코드·값을 안 보는 도구) — 운영자 2026-11-24
            except Exception as ex: print(f"{vid}: 독립 검수 실패 {ex}", flush=True)
            try: subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_color_overlay.py"), a.out, "--only", vid], timeout=300)   # 색 겹침 그림(화면 확인용)
            except Exception as ex: print(f"{vid}: 색겹침 실패 {ex}", flush=True)
            try: subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_overview_html.py"), a.out] + (["--meta", os.environ["TT_META"]] if os.environ.get("TT_META") else []), timeout=120)   # 한눈에.html
            except Exception as ex: print(f"{vid}: 한눈에 실패 {ex}", flush=True)
            cmd = [sys.executable, "-I", "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_compare_html3.py"), a.out, "--name", "비교.html"]
            if os.environ.get("TT_META"): cmd += ["--meta", os.environ["TT_META"]]
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except Exception: pass

if __name__ == "__main__":
    if "--org" not in sys.argv: sys.argv += ["--org", "thumbtitle"]
    from tt_typo import gate
    gate("tt-typo3", "보통", 1800)
    main()
