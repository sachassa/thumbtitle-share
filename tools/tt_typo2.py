# tt_typo2 — 썸네일 속 타이틀 재현 2판(INFO-20261124-005). 1판(tt_typo)의 글자 읽기·줄 떼기는 그대로 쓰고,
#   ① 글꼴을 점수로 고른다(후보 글꼴마다 그려 원본 글자 모양과 겹침 IoU, 1·2등을 적음)
#   ② 글자 하나하나의 자리를 원본에 맞춘다(줄 위·아래 끝, 글자마다 왼·오른 끝 — 격자로 견줌)
#   ③ 크기·자간·가로 비율·굵기(글꼴 굵기 단계와 덧댄 두께 따로)·테두리 두께를 「그리기→차이 재기→고치기」로 차이가 더 줄지 않을 때까지 되풀이
#   ④ 색은 글자 안쪽 픽셀(가장자리 뺌)의 가운데값, 같은 색 글자는 한 덩어리로 묶고 그라데이션·테두리·그림자 색은 따로
#   ⑤ 사람이 고친 글자(고친글자.tsv)가 있으면 그것으로 그린다 — 읽기 오류와 재현 오류를 따로 센다
# 이 PC 안에서만 돈다(외부 AI·웹 없음). 그림은 내부 비교용.
#   python -I -X utf8 tt_typo2.py --ids 목록.tsv --img-dir <썸네일 폴더> --out <결과 폴더> [--fix 고친글자.tsv] [--limit N]
import argparse, glob, html, json, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_typo as T   # 1판: 읽기·줄 재기·Chrome 찍기 (문지기는 1판 __main__에만 있어 여기서 따로 부른다)
from tt_typo import np, cv2, Image, ImageDraw, ImageFont, imread, imwrite, hexc, lab, dE

FONT_DIR2 = T.CFG.FONT_EXTRA   # 받은 무료·상업 가능 글꼴(fonts/free_fonts.json, tt_setup.py fonts-free)

def candidates():
    out = []
    for name, f, w in T.CANDS:
        p = T.font_path(f)
        if p: out.append((name, p, w))
    for p in sorted(glob.glob(FONT_DIR2 + "/*")):
        try: ft = ImageFont.truetype(p, 20); fam, sty = ft.getname()
        except Exception: continue
        fam = fam if fam and fam != "WebSubsetFont" else os.path.splitext(os.path.basename(p))[0]
        if "[wght]" in p:
            for w in (700, 900): out.append((f"{fam} {w}", p.replace("\\", "/"), w))
        else: out.append((f"{fam} {sty}".strip(), p.replace("\\", "/"), None))
    return out
CANDS = candidates()

# ---------- 글자 그리기(PIL) ----------
_FC, _GC = {}, {}
def pfont(c, size):
    key = (c[1], c[2], round(size * 4) / 4)
    if key not in _FC:
        if len(_FC) > 400: _FC.clear(); _GC.clear()
        ft = ImageFont.truetype(c[1], key[2])
        if c[2]:
            try: ft.set_variation_by_axes([c[2]])
            except Exception: pass
        _FC[key] = ft
    return _FC[key], key

def glyph(c, size, ch):
    """글자 하나 → (그림 0~255, 원점(펜·기준선)에서 왼쪽 위까지 x, y, 나아갈 폭)"""
    ft, key = pfont(c, size); k = key + (ch,)
    if k not in _GC:
        adv = ft.getlength(ch)
        l, t, r, b = ft.getbbox(ch, anchor="ls")
        if r <= l or b <= t: _GC[k] = (None, 0, 0, adv)
        else:
            im = Image.new("L", (r - l + 2, b - t + 2), 0)
            ImageDraw.Draw(im).text((1 - l, 1 - t), ch, font=ft, fill=255, anchor="ls")
            _GC[k] = (np.asarray(im, np.float32), l - 1, t - 1, adv)
    return _GC[k]

def layout(c, chars, p):
    """p = size, ls(자간 px), hs(가로 비율), x0, by(첫 펜 자리·기준선), dx/dy(글자마다 더 옮김) → 글자마다 (i, 그림, x, y, 펜)"""
    out = []; pen = p["x0"]
    for i, ch in enumerate(chars):
        g, ox, oy, adv = glyph(c, p["size"], ch)
        if ch != " " and g is not None:
            if abs(p["hs"] - 1) > 1e-3:
                g = cv2.resize(g, (max(1, int(round(g.shape[1] * p["hs"]))), g.shape[0]), interpolation=cv2.INTER_LINEAR)
            gx = 0.0
            sh = p.get("sh", 0.0)
            if abs(sh) > 1e-3:
                # 기울임(줄 하나에 한 벌): 기준선에서 위로 갈수록 오른쪽으로 sh × 높이만큼 민다
                h, w = g.shape; o0, o1 = -sh * oy, -sh * (oy + h - 1)
                lo = min(o0, o1); hi = max(o0, o1)
                M = np.float32([[1, -sh, -sh * oy - lo], [0, 1, 0]])
                g = cv2.warpAffine(g, M, (w + int(np.ceil(hi - lo)) + 2, h), flags=cv2.INTER_LINEAR)
                gx = lo
            out.append((i, g, pen + ox * p["hs"] + gx + p["dx"][i], p["by"] + oy + p["dy"][i], pen))
        pen += adv * p["hs"] + p["ls"]
    return out

def raster(lay, shape, e=0.0, ids=False):
    H, W = shape; cv = np.zeros(shape, np.float32); idm = np.full(shape, -1, np.int16) if ids else None
    for i, g, x, y, _ in lay:
        xi, yi = int(round(x)), int(round(y)); h, w = g.shape
        a0, b0 = max(0, yi), max(0, xi); a1, b1 = min(H, yi + h), min(W, xi + w)
        if a1 <= a0 or b1 <= b0: continue
        sub = g[a0 - yi:a1 - yi, b0 - xi:b1 - xi]
        np.maximum(cv[a0:a1, b0:b1], sub, out=cv[a0:a1, b0:b1])
        if ids: idm[a0:a1, b0:b1][sub > 127] = i
    m = cv > 127
    if e > 0.05: m = grow(m, e)
    return (m, idm) if ids else m

def grow(m, e):
    if e <= 0.05 or not m.any(): return m
    d = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 5)
    return m | (d <= e + 0.5)

def iou(a, b):
    u = (a | b).sum(); return float((a & b).sum() / u) if u else 0.0

def bbox(m):
    ys, xs = np.where(m)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None

# ---------- 맞추기 ----------
def slant_of(F):
    """원본 글자 덩어리의 기울기: 거꾸로 기울여 세로획이 가장 곧게 서는(세로 합이 가장 뾰족한) 값."""
    ys, xs = np.nonzero(F)
    if len(xs) < 50: return 0.0
    yb = ys.max(); best = (0.0, -1)
    for sh in np.arange(-0.35, 0.3501, 0.025):
        x2 = np.round(xs + sh * (ys - yb)).astype(int); x2 -= x2.min()
        col = np.bincount(x2); v = float((col.astype(np.float64) ** 2).sum())
        if v > best[1]: best = (float(sh), v)
    return round(best[0], 3)

def init_params(c, chars, F, hs=1.0, sh=0.0):
    L, Tt, R, B = bbox(F); n = len(chars)
    p = dict(size=100.0, ls=0.0, hs=float(hs), sh=float(sh), x0=0.0, by=0.0, dx=[0.0] * n, dy=[0.0] * n, e=0.0)
    m = bb_of(layout(c, chars, p))
    if m is None: return None
    p["size"] = max(6.0, 100.0 * (B - Tt) / max(1, m[3] - m[1]))
    m = bb_of(layout(c, chars, p))
    if m is None: return None
    if n > 1: p["ls"] = max(-p["size"] * 0.3, min(p["size"] * 0.6, ((R - L) - (m[2] - m[0])) / (n - 1)))
    m = bb_of(layout(c, chars, p))
    p["x0"] = L - m[0]; p["by"] = B - m[3]
    return p

def bb_of(lay):
    if not lay: return None
    x0 = min(x for _, g, x, y, _ in lay); y0 = min(y for _, g, x, y, _ in lay)
    x1 = max(x + g.shape[1] for _, g, x, y, _ in lay); y1 = max(y + g.shape[0] for _, g, x, y, _ in lay)
    # 그림 둘레 1px 빈칸과 흐린 가장자리를 뺀 잉크 상자
    m = raster([(i, g, x - x0, y - y0, pn) for i, g, x, y, pn in lay], (int(y1 - y0) + 3, int(x1 - x0) + 3))
    b = bbox(m)
    return None if b is None else (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0)

def score(c, chars, p, F):
    return iou(F, raster(layout(c, chars, p), F.shape, p["e"]))

def optimize(c, chars, F, p, rounds=40):
    """좌표 하강: 값 하나씩 ± 걸음으로 바꿔 겹침이 늘면 받아들인다. 한 바퀴 내내 안 늘면 걸음을 반으로. 더 안 늘면 멈춤."""
    steps = dict(size=p["size"] * 0.03, ls=max(0.5, p["size"] * 0.02), hs=0.03, x0=1.5, by=1.5, e=0.75)
    if "sh" in p: steps["sh"] = 0.02
    best = score(c, chars, p, F); hist = [round(best, 4)]; n = 0
    for n in range(1, rounds + 1):
        moved = False
        for k in steps:
            for sgn in (1, -1):
                q = dict(p); q[k] = p[k] + sgn * steps[k]
                if k == "e" and q[k] < 0: continue
                if k == "hs" and not (0.7 <= q[k] <= 1.4): continue
                if k == "sh" and not (-0.4 <= q[k] <= 0.4): continue
                s = score(c, chars, q, F)
                if s > best + 1e-4: p, best, moved = q, s, True; break
        hist.append(round(best, 4))
        if not moved:
            steps = {k: v / 2 for k, v in steps.items()}
            if steps["x0"] < 0.2: break
    return p, best, hist, n

def refine_glyphs(c, chars, F, p, passes=2):
    """글자 하나씩 왼·오른·위·아래로 옮겨 원본 글자 자리에 맞춘다."""
    best = score(c, chars, p, F); p = dict(p, dx=list(p["dx"]), dy=list(p["dy"]))
    for _ in range(passes):
        moved = False
        for i, ch in enumerate(chars):
            if ch == " ": continue
            for ddx, ddy in [(1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2), (3, 0), (-3, 0)]:
                q = dict(p, dx=list(p["dx"]), dy=list(p["dy"])); q["dx"][i] += ddx; q["dy"][i] += ddy
                if abs(q["dx"][i]) > p["size"] * 0.25 or abs(q["dy"][i]) > p["size"] * 0.15: continue
                s = score(c, chars, q, F)
                if s > best + 1e-4: p, best, moved = q, s, True
        if not moved: break
    return p, best

def fit_line(chars, F, log):
    """글꼴 고르기: ① 모든 후보를 같은 높이·너비로 그려 겹침 → 위 6개만 ② 되풀이 맞추기 뒤 겹침으로 1등을 정한다."""
    t0 = time.time(); coarse = []
    for c in CANDS:
        try: p = init_params(c, chars, F)
        except Exception: p = None
        if p is None: continue
        coarse.append((score(c, chars, p, F), c, p))
    coarse.sort(key=lambda x: -x[0])
    fine = []
    for s0, c, p in coarse[:6]:
        p2, s2, hist, n = optimize(c, chars, F, p)
        fine.append(dict(c=c, p=p2, s=s2, s0=s0, hist=hist, n=n))
    fine.sort(key=lambda x: -x["s"])
    w = fine[0]
    p3, s3 = refine_glyphs(w["c"], chars, F, w["p"])
    # 글자 자리를 옮긴 뒤 크기·자간 등을 한 번 더 되풀이
    p4, s4, hist2, n2 = optimize(w["c"], chars, F, p3, rounds=20)
    w.update(p=p4, s_final=s4, hist=w["hist"] + hist2[1:], n=w["n"] + n2)
    log.append(f"글꼴 고르기 {len(coarse)}개 {time.time()-t0:.1f}초")
    return w, fine, coarse

def fit_outline(fill_r, U):
    """테두리 두께: 그린 채움을 w만큼 키운 모양이 원본(채움+테두리)과 가장 많이 겹치는 w."""
    if U is None or not U.any(): return None, 0
    d = cv2.distanceTransform((~fill_r).astype(np.uint8), cv2.DIST_L2, 5)
    best = (0, 0.0)
    for w in np.arange(0.5, 16.01, 0.5):
        s = iou(U, fill_r | (d <= w + 0.5))
        if s > best[0]: best = (s, float(w))
    return best[1], best[0]

# ---------- 색 ----------
def core_of(m, frac=0.45):
    if not m.any(): return m
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    th = max(1.0, frac * float(dt.max()))
    c = m & (dt >= th)
    return c if c.sum() >= 3 else m

def glyph_assign(F, idm):
    """원본 글자 픽셀마다 「가장 가까운 재현 글자」 번호."""
    src = (idm >= 0)
    if not src.any(): return np.full(F.shape, -1, np.int16)
    _, lbl = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(src); table = np.zeros(lbl.max() + 1, np.int16) - 1
    table[lbl[ys, xs]] = idm[ys, xs]
    out = table[lbl]; out[~F] = -1
    return out

def colors(C, F, gmap, chars):
    """글자마다 안쪽 색 → 이웃 글자와 ΔE 15 아래면 한 덩어리. 덩어리마다 위·아래 색이 다르면 그라데이션."""
    per = []
    for i, ch in enumerate(chars):
        if ch == " ": continue
        m = gmap == i
        if m.sum() < 4: continue
        cm = core_of(m)
        per.append(dict(i=i, bgr=np.median(C[cm], 0), m=m))
    spans = []
    for g in per:
        if spans and dE(spans[-1]["bgr"], g["bgr"]) < 15:
            s = spans[-1]; s["gl"].append(g); s["m"] = s["m"] | g["m"]
            s["bgr"] = np.median(C[core_of(s["m"])], 0)
        else: spans.append(dict(gl=[g], m=g["m"].copy(), bgr=g["bgr"]))
    out = []
    for s in spans:
        m = s["m"]; cm = core_of(m); ys = np.where(m)[0]
        y0, y1 = np.percentile(ys, 20), np.percentile(ys, 80)
        top = cm & (np.arange(m.shape[0])[:, None] <= y0); bot = cm & (np.arange(m.shape[0])[:, None] >= y1)
        grad = None
        if top.sum() >= 4 and bot.sum() >= 4:
            ct, cb = np.median(C[top], 0), np.median(C[bot], 0)
            bands = [np.median(C[cm & (np.arange(m.shape[0])[:, None] >= a) & (np.arange(m.shape[0])[:, None] < b)], 0)
                     for a, b in zip(np.percentile(ys, [0, 25, 50, 75]), list(np.percentile(ys, [25, 50, 75])) + [ys.max() + 1])
                     if (cm & (np.arange(m.shape[0])[:, None] >= a) & (np.arange(m.shape[0])[:, None] < b)).sum() >= 2]
            mono = len(bands) == 4 and all(dE(bands[0], bands[k + 1]) >= dE(bands[0], bands[k]) - 3 for k in range(3))
            if dE(ct, cb) > 15 and mono: grad = dict(dir="위→아래", start=hexc(ct), end=hexc(cb), dE=round(dE(ct, cb), 1))
        i0, i1 = s["gl"][0]["i"], s["gl"][-1]["i"]
        out.append(dict(color=hexc(np.median(C[cm], 0)), grad=grad, i0=i0, i1=i1, chars="".join(chars[i0:i1 + 1]), _m=m))
    return out

# ---------- 고친 글자 ----------
def load_fix(p):
    fx = {}
    if p and os.path.exists(p):
        for ln in open(p, encoding="utf-8-sig"):
            a = ln.rstrip("\n").split("\t")
            if len(a) >= 3 and a[0] != "video_id" and a[2].strip(): fx[(a[0].strip(), a[1].strip())] = a[2].strip()
    return fx

# ---------- 재현 HTML(SVG) ----------
def svg_doc(im, L, bgfile, mode="color", shift=None):
    """mode=color: 배경+그림자+테두리+채움 / mode=mask: 검은 바탕에 채움만 흰색(재현 채움 모양 재기용)"""
    H, W = im.shape[:2]; shift = shift or {}
    defs, body, faces = [], [], {}
    for li, l in enumerate(L):
        c = l["_c"]; p = l["_p"]; fam = "f%d" % (abs(hash((c[1], c[2]))) % 10 ** 6); faces[fam] = c
        X0, Y0 = l["_crop"][:2]; sx, sy = shift.get(li, (0, 0))
        chars = l["_chars"]; pen = p["x0"]; xs, ys = [], []
        for i, ch in enumerate(chars):
            _, _, _, adv = glyph(c, p["size"], ch)
            xs.append((X0 + pen + p["dx"][i] + sx) / p["hs"]); ys.append(Y0 + p["by"] + p["dy"][i] + sy)
            pen += adv * p["hs"] + p["ls"]
        e = p["e"]
        tr = f'matrix({p["hs"]:.4f} 0 0 1 0 0)'
        if abs(l.get("tilt_deg") or 0) > 1.5:
            tr = f'rotate({l["tilt_deg"]} {xs[0]*p["hs"]:.1f} {ys[0]:.1f}) ' + tr
        common = (f'x="{" ".join(f"{v:.2f}" for v in xs)}" y="{" ".join(f"{v:.2f}" for v in ys)}" font-family="{fam}" '
                  f'font-size="{p["size"]:.2f}" xml:space="preserve" transform="{tr}" stroke-linejoin="round"')
        txt = html.escape("".join(chars))
        if mode == "mask":
            sw = f' stroke="#fff" stroke-width="{2*e:.2f}"' if e > 0.05 else ""
            body.append(f'<text {common} fill="#fff"{sw}>{txt}</text>'); continue
        if l.get("shadow"):
            s = l["shadow"]; ow = l.get("_ow") or 0
            body.append(f'<g transform="translate({s["dx"]} {s["dy"]})"><text {common} fill="{s["color"]}" stroke="{s["color"]}" stroke-width="{2*(ow+e):.2f}">{txt}</text></g>')
        if l.get("_ow"):
            oc = l["_oc"]
            body.append(f'<text {common} fill="{oc}" stroke="{oc}" stroke-width="{2*(l["_ow"]+e):.2f}">{txt}</text>')
        tsp = []; done = 0
        for j, s in enumerate(l["_spans"]):
            col = s["color"]
            if s["grad"]:
                gid = f"g{li}_{j}"; iy0, iy1 = l["ink"][1], l["ink"][3]
                defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="{iy0}" x2="0" y2="{iy1}">'
                            f'<stop offset="0.15" stop-color="{s["grad"]["start"]}"/><stop offset="0.85" stop-color="{s["grad"]["end"]}"/></linearGradient>')
                col = f"url(#{gid})"
            a, b = (done, s["i1"] + 1) if j < len(l["_spans"]) - 1 else (done, len(chars))
            if j == 0: a = 0
            sw = f' stroke="{col}" stroke-width="{2*e:.2f}"' if e > 0.05 else ""
            tsp.append(f'<tspan fill="{col}"{sw}>{html.escape("".join(chars[a:b]))}</tspan>'); done = b
        body.append(f'<text {common}>{"".join(tsp)}</text>')
    ff = "".join("@font-face{font-family:%s;src:url('file:///%s');}" % (k, c[1]) for k, c in faces.items())
    ffv = "".join(f"text[font-family={k}]{{font-variation-settings:'wght' {c[2]};}}" for k, c in faces.items() if c[2])
    bg = f'<image href="{bgfile}" x="0" y="0" width="{W}" height="{H}"/>' if mode == "color" else f'<rect width="{W}" height="{H}" fill="#000"/>'
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{ff}{ffv}html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#000}}</style></head>'
            f'<body><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{"".join(defs)}</defs>{bg}{"".join(body)}</svg></body></html>')

# ---------- 원본·재현 견주기 ----------
def glyph_boxes(m, gmap, chars):
    out = {}
    for i, ch in enumerate(chars):
        if ch == " ": continue
        b = bbox(m & (gmap == i))
        if b: out[i] = b
    return out

def f1_exact(a, b):
    """봐주기 없는 겹침 F1 = 2·|A∩B| / (|A|+|B|). 화소가 모두 같아야 1.00."""
    n = int(a.sum()) + int(b.sum())
    return float(2 * (a & b).sum() / n) if n else 0.0

def f1_tol(a, b):
    k = np.ones((3, 3), np.uint8)
    da = cv2.dilate(a.astype(np.uint8), k) > 0; db = cv2.dilate(b.astype(np.uint8), k) > 0
    P = (b & da).sum() / b.sum() if b.sum() else 0; R = (a & db).sum() / a.sum() if a.sum() else 0
    return float(2 * P * R / (P + R)) if P + R else 0.0

def measure_pair(l, im, rep, repmask_full):
    """한 줄: 원본 잰 값 · 재현 잰 값 · 차이(px)."""
    X0, Y0, X1, Y1 = l["_crop"]; F = l["_F"]; chars = l["_chars"]
    Rm = repmask_full[Y0:Y1, X0:X1].copy()
    fb = bbox(F); mg = max(3, int((fb[3] - fb[1]) * 0.2))   # 이웃 줄 글자가 섞이지 않게 이 줄 높이 근처만
    Rm[:max(0, fb[1] - mg)] = False; Rm[fb[3] + mg:] = False
    model, idm = raster(layout(l["_c"], chars, l["_p"]), F.shape, l["_p"]["e"], ids=True)
    sx, sy = l.get("_shift", (0, 0))
    if sx or sy: model = np.roll(np.roll(model, sy, 0), sx, 1); idm = np.roll(np.roll(idm, sy, 0), sx, 1)
    Rm &= grow(model, 4.0)   # 이 줄을 그린 자리 근처만(이웃 줄 글자 빼기)
    gF = glyph_assign(F, idm); gR = glyph_assign(Rm, idm)
    bo, br = glyph_boxes(F, gF, chars), glyph_boxes(Rm, gR, chars)
    rows = []
    for i in sorted(set(bo) & set(br)):
        o, r = bo[i], br[i]
        rows.append(dict(ch=chars[i], o=[o[0] + X0, o[2] + X0, o[1] + Y0, o[3] + Y0], r=[r[0] + X0, r[2] + X0, r[1] + Y0, r[3] + Y0],
                         d=[r[0] - o[0], r[2] - o[2], r[1] - o[1], r[3] - o[3]],
                         iou=round(iou(F & (gF == i), Rm & (gR == i)), 2)))
    bF, bR = bbox(F), bbox(Rm)
    def gaps(bx):
        ks = sorted(bx); g = [bx[b][0] - bx[a][2] for a, b in zip(ks, ks[1:]) if chars[a] != " " and b == a + 1]
        return float(np.mean(g)) if g else None
    sw_o, sw_r = T.stroke_w(F), T.stroke_w(Rm) if Rm.any() else None
    res = dict(
        f1=round(f1_tol(F, Rm), 3), iou=round(iou(F, Rm), 3),
        top=[bF[1] + Y0, bR[1] + Y0 if bR else None], bottom=[bF[3] + Y0, bR[3] + Y0 if bR else None],
        left=[bF[0] + X0, bR[0] + X0 if bR else None], right=[bF[2] + X0, bR[2] + X0 if bR else None],
        ink_h=[bF[3] - bF[1], (bR[3] - bR[1]) if bR else None],
        gap=[round(gaps(bo), 2) if gaps(bo) is not None else None, round(gaps(br), 2) if gaps(br) is not None else None],
        stroke=[round(sw_o, 2) if sw_o else None, round(sw_r, 2) if sw_r else None],
        glyphs=rows)
    ed = [abs(v) for r in rows for v in r["d"]]
    res["edge_mean"] = round(float(np.mean(ed)), 2) if ed else None
    res["edge_max"] = int(max(ed)) if ed else None
    res["suspect"] = [r["ch"] for r in rows if r["iou"] < 0.45]
    # 색: 원본 안쪽 픽셀 자리에서 원본·재현 색
    cols = []
    C = im[Y0:Y1, X0:X1].astype(np.float32); CR = rep[Y0:Y1, X0:X1].astype(np.float32)
    for s in l["_spans"]:
        cm = core_of(s["_m"]) & core_of(Rm)
        if cm.sum() < 3: cm = core_of(s["_m"])
        co, cr = np.median(C[cm], 0), np.median(CR[cm], 0)
        cols.append(dict(what=f'채움 「{s["chars"]}」', o=hexc(co), r=hexc(cr), dE=round(dE(co, cr), 1)))
        if s["grad"]:
            ys = np.where(cm)[0]
            for nm, sel in (("위쪽", ys <= np.percentile(ys, 20)), ("아래쪽", ys >= np.percentile(ys, 80))):
                yy = np.zeros_like(cm); idx = np.where(cm); keep = sel
                yy[idx[0][keep], idx[1][keep]] = True
                if yy.sum() >= 3:
                    a, b = np.median(C[yy], 0), np.median(CR[yy], 0)
                    cols.append(dict(what=f'그라데이션 {nm}', o=hexc(a), r=hexc(b), dE=round(dE(a, b), 1)))
    if l.get("_ow") and l.get("_Ocore") is not None and l["_Ocore"].sum() >= 3:
        oc = l["_Ocore"]; a, b = np.median(C[oc], 0), np.median(CR[oc], 0)
        cols.append(dict(what="테두리", o=hexc(a), r=hexc(b), dE=round(dE(a, b), 1)))
    res["colors"] = cols
    fills = [c["dE"] for c in cols if c["what"].startswith("채움")]
    res["fill_dE"] = round(max(fills), 1) if fills else None
    line_d = max(abs(res["top"][1] - res["top"][0]), abs(res["bottom"][1] - res["bottom"][0])) if bR else 99
    res["line_d"] = int(line_d)
    em = res["edge_mean"] if res["edge_mean"] is not None else 99; fd = res["fill_dE"] if res["fill_dE"] is not None else 99
    res["verdict"] = ("같음" if res["f1"] >= 0.9 and em <= 1.5 and line_d <= 2 and fd <= 10 else
                      "거의 같음" if res["f1"] >= 0.8 and em <= 3 and line_d <= 4 and fd <= 20 else "다름")
    return res

CRIT = "같음 = 모양 겹침(1px 봐줌) 0.90 이상 · 글자 끝 어긋남 평균 1.5px 이하 · 줄 위·아래 끝 2px 이하 · 채움 색 차이(ΔE) 10 이하 / 거의 같음 = 0.80 · 3px · 4px · 20"

def diff_image(im, rep, masks):
    """차이 그림: 흐린 회색 원본 위에 빨강 = 원본에만 글자, 파랑 = 재현에만 글자, 노랑 = 둘 다 글자인데 색이 다름(ΔE>20)."""
    g = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    out = (g.astype(np.float32) * 0.35 + 255 * 0.5).astype(np.uint8)
    O, R = masks
    out[O & ~R] = (40, 40, 230); out[R & ~O] = (230, 120, 30)
    both = O & R
    if both.any():
        la, lb = lab(im[both].astype(np.float32)), lab(rep[both].astype(np.float32))
        d = np.linalg.norm(la - lb, axis=1); sel = np.zeros_like(both); sel[both] = d > 20
        out[sel] = (0, 210, 240); out[both & ~sel] = (170, 170, 170)
    return out

# ---------- 한 장 ----------
def run_one(vid, path, out, fixes, chrome_rounds=3):
    log = []
    im, lines = T.analyze(vid, path, out)
    H, W = im.shape[:2]
    L = []
    for r in lines:
        if "_fit" not in r: continue
        read = r.get("ocr_first") or r["text"]
        r["read_text"] = r["text"]
        fx = fixes.get((vid, read)) or fixes.get((vid, r["text"]))
        if fx: r["text"] = fx; r["read_fixed"] = True
        X0, Y0, X1, Y1 = r["_crop"]
        F = np.zeros((Y1 - Y0, X1 - X0), bool)
        ix0, iy0, ix1, iy1 = r["ink"]; fm = r["_fill_mask"]
        F[iy0 - Y0:iy0 - Y0 + fm.shape[0], ix0 - X0:ix0 - X0 + fm.shape[1]] = fm
        r["_F"] = F; r["_chars"] = list(r["text"])
        w, fine, coarse = fit_line(r["_chars"], F, log)
        r["_c"], r["_p"] = w["c"], w["p"]
        r["font2"] = dict(best=w["c"][0], file=os.path.basename(w["c"][1]), weight=w["c"][2], score=round(w["s"], 3),
                          score_after_glyphs=round(w["s_final"], 3),
                          second=(dict(name=fine[1]["c"][0], score=round(fine[1]["s"], 3)) if len(fine) > 1 else None),
                          top=[dict(name=f["c"][0], score=round(f["s"], 3), first=round(f["s0"], 3)) for f in fine],
                          tried=len(coarse), rounds=w["n"], hist=w["hist"])
        p = w["p"]
        r["fit2"] = dict(size_px=round(p["size"], 2), size_1080=round(p["size"] * 1920 / H, 1), ls_px=round(p["ls"], 2), ls_em=round(p["ls"] / p["size"], 3),
                         hscale=round(p["hs"], 3), bold_px=round(p["e"], 2),
                         glyph_dx=[round(v, 1) for v in p["dx"]], glyph_dy=[round(v, 1) for v in p["dy"]])
        fill_r = raster(layout(w["c"], r["_chars"], p), F.shape, p["e"])
        # 테두리
        r["_ow"] = None; r["_Ocore"] = None
        if r.get("outline"):
            U = r["_uni"]
            ow, os_ = fit_outline(fill_r, U)
            O = U & ~grow(F, 1.0)
            if O.sum() >= 5:
                dto = cv2.distanceTransform(O.astype(np.uint8), cv2.DIST_L2, 5)
                Oc = O & (dto >= max(1.0, 0.45 * float(dto.max())))
                C = im[Y0:Y1, X0:X1].astype(np.float32)
                oc = np.median(C[Oc if Oc.sum() >= 3 else O], 0)
                if ow < 1.0 or dE(oc, T._hex2bgr(r["bg_color"])) < 12 or (r["outline"].get("width_px") or 0) <= 0:
                    r["outline2"] = dict(width_px=0, color=None, note="테두리 없음(너비 1px 아래이거나 바탕과 같은 색)")
                    O = None
            if O is not None and O.sum() >= 5:
                r["_ow"] = ow; r["_oc"] = hexc(oc); r["_Ocore"] = Oc if Oc.sum() >= 3 else O
                r["outline2"] = dict(width_px=ow, color=hexc(oc), match=round(os_, 3), width_first=r["outline"].get("width_px"))
        # 색
        _, idm = raster(layout(w["c"], r["_chars"], p), F.shape, p["e"], ids=True)
        gmap = glyph_assign(F, idm)
        r["_spans"] = colors(im[Y0:Y1, X0:X1].astype(np.float32), F, gmap, r["_chars"])
        if not r["_spans"]:
            r["_spans"] = [dict(color=r["fill"][0]["color"] if r.get("fill") else "#FFFFFF", grad=None, i0=0, i1=len(r["_chars"]) - 1, chars=r["text"], _m=F)]
        L.append(r)
    L.sort(key=lambda r: r["ink"][1])
    G = os.path.join(out, "그림"); os.makedirs(G, exist_ok=True)
    imwrite(os.path.join(G, f"{vid}_원본.png"), im)
    # 배경: 글자(채움+테두리+그림자) 자리를 지워 메운다
    mask = np.zeros((H, W), np.uint8)
    for r in lines:
        X0, Y0, X1, Y1 = r["_crop"]; u = r["_uni"].astype(np.uint8) * 255
        sh = r.get("shadow")
        if sh: u = np.maximum(u, np.roll(np.roll(u, sh["dy"], 0), sh["dx"], 1))
        mask[Y0:Y1, X0:X1] = np.maximum(mask[Y0:Y1, X0:X1], u)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    bgim = cv2.inpaint(im, mask, 5, cv2.INPAINT_TELEA)
    imwrite(os.path.join(G, f"{vid}_배경.png"), bgim)
    RD = os.path.join(out, "재현"); os.makedirs(RD, exist_ok=True)
    hf, hm = os.path.join(RD, f"{vid}.html"), os.path.join(RD, f"{vid}_mask.html")
    png, pngm = os.path.join(G, f"{vid}_재현.png"), os.path.join(G, f"{vid}_재현채움.png")
    bgurl = f"../그림/{vid}_배경.png"
    # Chrome으로 그려 재고, 줄마다 남은 자리 어긋남을 고쳐 다시 그린다 — 더 안 줄면 멈춤
    shift = {}; best = None; hist = []
    for rd in range(chrome_rounds):
        open(hf, "w", encoding="utf-8").write(svg_doc(im, L, bgurl, "color", shift)); T.chrome_shot(hf, png, W, H)
        open(hm, "w", encoding="utf-8").write(svg_doc(im, L, bgurl, "mask", shift)); T.chrome_shot(hm, pngm, W, H)
        rep, rm = imread(png), imread(pngm)
        RM = rm.max(2) > 127
        for li, l in enumerate(L): l["_shift"] = shift.get(li, (0, 0))
        ms =[measure_pair(l, im, rep, RM) for l in L]
        tot = sum(m["iou"] for m in ms) / max(1, len(ms)); hist.append(round(tot, 4))
        if best is None or tot > best[0] + 1e-4: best = (tot, dict(shift), ms, rep, RM)
        else: break
        new = {}
        for li, m in enumerate(ms):
            ds = [g["d"] for g in m["glyphs"]]
            if not ds: continue
            dx = -float(np.median([(d[0] + d[1]) / 2 for d in ds])); dy = -float(np.median([(d[2] + d[3]) / 2 for d in ds]))
            sx, sy = shift.get(li, (0, 0)); new[li] = (sx + round(dx), sy + round(dy))
        if new == shift: break
        shift = new
    tot, shift, ms, rep, RM = best
    if hist[-1] < tot - 1e-4:   # 마지막에 그린 것이 더 나쁘면 가장 좋았던 것으로 다시
        open(hf, "w", encoding="utf-8").write(svg_doc(im, L, bgurl, "color", shift)); T.chrome_shot(hf, png, W, H)
        open(hm, "w", encoding="utf-8").write(svg_doc(im, L, bgurl, "mask", shift)); T.chrome_shot(hm, pngm, W, H)
    # 차이 그림
    O = np.zeros((H, W), bool)
    for l in L:
        X0, Y0, X1, Y1 = l["_crop"]; O[Y0:Y1, X0:X1] |= l["_F"]
    imwrite(os.path.join(G, f"{vid}_차이.png"), diff_image(im, rep, (O, RM)))
    out_lines = []
    for l, m in zip(L, ms):
        d = {k: v for k, v in l.items() if not k.startswith("_")}
        d["spans2"] = [{k: v for k, v in s.items() if k != "_m"} for s in l["_spans"]]
        d["cmp2"] = m; d["chrome_shift"] = shift.get(L.index(l), (0, 0))
        out_lines.append(d)
    for a, b in zip(out_lines, out_lines[1:]):   # 행간: 같은 자리 무리 안 이웃 줄의 아래 끝 사이
        if a["role"] == b["role"]:
            o = b["cmp2"]["bottom"][0] - a["cmp2"]["bottom"][0]; r_ = (b["cmp2"]["bottom"][1] or 0) - (a["cmp2"]["bottom"][1] or 0)
            b["lead2"] = dict(o=o, r=r_, d=r_ - o)
    val = dict(video_id=vid, canvas=[W, H], src=path.replace("\\", "/"), lines=out_lines, chrome_rounds=hist, log=log)
    json.dump(val, open(os.path.join(out, "값", f"{vid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return val

def free_mb():
    import ctypes
    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
    m = MS(); m.l = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.avail / 2 ** 20

def wait_mem(need_mb=None):
    need_mb = need_mb or int(os.environ.get("TT_MEM_MB", "3072"))   # Central 승인 때만 낮춤(예: 2048)
    """남은 메모리가 need_mb 밑이면 기다린다(Central 2026-11-24: 3GB 밑이면 기다렸다 다시)."""
    n = 0
    while free_mb() < need_mb:
        if n % 6 == 0: print(f"  메모리 기다림 — 남은 {free_mb():.0f}MB < {need_mb}MB", flush=True)
        time.sleep(10); n += 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True); ap.add_argument("--img-dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--fix"); ap.add_argument("--skip-done", action="store_true"); ap.add_argument("--limit", type=int); ap.add_argument("--only"); ap.add_argument("--org", default="thumbtitle")
    a = ap.parse_args()
    for d in ("값", "그림", "재현"): os.makedirs(os.path.join(a.out, d), exist_ok=True)
    fixes = load_fix(a.fix or os.path.join(a.out, "고친글자.tsv"))
    ids = []
    with open(a.ids, encoding="utf-8-sig") as fh:
        for i, line in enumerate(fh):
            v = line.split("\t")[0].strip()
            if v and not (i == 0 and v == "video_id"): ids.append(v)
    if a.only: ids = [v for v in ids if v in a.only.split(",")]
    if a.skip_done: ids = [v for v in ids if not os.path.exists(os.path.join(a.out, "값", f"{v}.json"))]
    ids = ids[: a.limit or None]
    print(f"후보 글꼴 {len(CANDS)}개 · 고친 글자 {len(fixes)}줄 · {len(ids)}장", flush=True)
    t0 = time.time(); n_ok = 0
    for n, vid in enumerate(ids, 1):
        cand = glob.glob(os.path.join(a.img_dir, vid + ".jpg")) + glob.glob(os.path.join(a.img_dir, "*", vid + ".jpg"))
        if not cand: print(f"{n}/{len(ids)} {vid}: 그림 없음", flush=True); continue
        wait_mem()
        try:
            v = run_one(vid, cand[0], a.out, fixes); n_ok += 1
            print(f"{n}/{len(ids)} {vid} ({time.time()-t0:.0f}초, 남은 메모리 {free_mb():.0f}MB): " + " | ".join(
                f"{l['text'][:8]} {l['font2']['best']} {l['cmp2']['verdict']} 겹침{l['cmp2']['f1']}" for l in v["lines"]), flush=True)
        except Exception as e:
            import traceback; traceback.print_exc(); print(f"{n}/{len(ids)} {vid}: 오류 — {e}", flush=True)
    print(f"끝 — {n_ok}장 {time.time()-t0:.0f}초", flush=True)

if __name__ == "__main__":
    if "--org" not in sys.argv: sys.argv += ["--org", "thumbtitle"]
    from tt_typo import gate
    gate("tt-typo2", "보통", 1800)
    main()
