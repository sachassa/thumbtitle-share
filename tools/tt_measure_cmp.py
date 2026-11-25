# tt_measure_cmp — 원본과 재현 그림을 「같은 방법으로」 직접 재서 줄마다 항목별로 견준다(운영자 요청 2026-11-24
# 「그라데이션·자간·행간·폰트 사이즈 등 원본 조사한 것과 우리가 만든 것의 일치 여부를 실측으로 확인해 칸을 늘려 보여줘」).
#   python -I -X utf8 tt_measure_cmp.py <결과 폴더> [--only id,id]
# 결과: 값/<id>_실측.json = {"lines": [{"항목": {"o": 원본, "r": 재현, "d": 차이, "ok": 일치, "unit": 단위}}...]}
# 잰 것: 글자 높이 · 글자 너비(평균) · 자간(빈칸 평균) · 행간(다음 줄과 빈칸) · 획 굵기 · 기울기 · 글자 색 · 그라데이션(위/아래 색) · 테두리 두께
import glob, json, os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_typo2 as T2


def imread(p): return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
def hex2bgr(h): h = h.lstrip("#"); return np.array([int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)], np.float32)
def hexc(bgr): b, g, r = [int(round(float(x))) for x in bgr]; return f"#{r:02X}{g:02X}{b:02X}"
def lab(bgr): return cv2.cvtColor(np.asarray(bgr, np.float32).reshape(-1, 1, 3) / 255.0, cv2.COLOR_BGR2Lab).reshape(-1, 3)
def dE(a, b): return float(np.linalg.norm(lab(a)[0] - lab(b)[0]))

def color_mask(img, cols, th=30.0):
    L = lab(img.reshape(-1, 3).astype(np.float32)).reshape(img.shape[0], img.shape[1], 3)
    m = np.zeros(img.shape[:2], bool)
    for c in cols: m |= np.linalg.norm(L - lab(c)[0], axis=2) < th
    k, lb, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    return np.isin(lb, [i for i in range(1, k) if st[i, 4] >= 15])

def stroke(m):
    if m.sum() < 20: return None
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    return round(float(4 * dt[m].mean()), 2)   # 너비 w 인 획의 안쪽 거리 평균 ≈ w/4

def grad(img, m):
    """글자 안쪽(가장자리 2px 뺌) 위 1/4·아래 1/4 색."""
    mi = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    if mi.sum() < 40: mi = m
    ys = np.nonzero(mi)[0]
    if len(ys) < 20: return None
    y0, y1 = ys.min(), ys.max(); q = (y1 - y0) / 4
    top = img[mi & (np.arange(img.shape[0])[:, None] <= y0 + q)]; bot = img[mi & (np.arange(img.shape[0])[:, None] >= y1 - q)]
    if len(top) < 5 or len(bot) < 5: return None
    return np.median(top, 0), np.median(bot, 0), np.median(img[mi], 0)

def outline_w(img, m, oc):
    if oc is None or m.sum() < 20: return None
    near = cv2.dilate(m.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    om = color_mask(img, [oc], 30) & near & ~m
    per = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).sum() - m.sum()
    return round(float(om.sum() / max(1, per)), 2)

def item(o, r, unit, hexs=False):
    """일치 = 값이 똑같을 때만(운영자 2026-11-24 「100% 일치여야 일치지」). 허용 범위로 「일치」라 하지 않는다.
    px·굵기·기울기는 소수 둘째 자리까지, 색은 #RRGGBB 가 같아야 일치."""
    if o is None or r is None: return dict(o=o, r=r, d=None, ok=None, unit=unit)
    if hexs: d = round(dE(hex2bgr(o), hex2bgr(r)), 1); return dict(o=o, r=r, d=d, ok=(o.upper() == r.upper()), unit="ΔE")
    o2, r2 = round(float(o), 2), round(float(r), 2); d = round(r2 - o2, 2)
    return dict(o=o2, r=r2, d=d, ok=(d == 0), unit=unit)

def measure(out, vid):
    v = json.load(open(os.path.join(out, "값", f"{vid}.json"), encoding="utf-8"))
    O = imread(os.path.join(out, "그림", f"{vid}_원본.png")); R = imread(os.path.join(out, "그림", f"{vid}_재현.png"))
    H, W = O.shape[:2]; res = []
    by = {}
    for d in v["grid"]: by.setdefault(d["line"], []).append(d)
    top = {li: next(d for d in ds if d["kind"] == "줄" and d["name"].endswith(" 위")) for li, ds in by.items()}
    bot = {li: next(d for d in ds if d["kind"] == "줄" and d["name"].endswith(" 아래")) for li, ds in by.items()}
    for li, l in enumerate(v["lines"]):
        ds = by.get(li, []); row = {}
        if not ds: res.append(row); continue
        xs = [d["o"] for d in ds if d.get("axis") == "x"]
        y0, y1 = int(top[li]["o"]) - 3, int(bot[li]["o"]) + 4; x0, x1 = max(0, int(min(xs)) - 8), min(W, int(max(xs)) + 9)
        row["글자 높이"] = item(bot[li]["o"] - top[li]["o"], bot[li]["r"] - top[li]["r"], "px")
        Ls = {d["g"]: d for d in ds if d["kind"] == "글자" and d["name"].endswith(" 왼")}; Rs = {d["g"]: d for d in ds if d["kind"] == "글자" and d["name"].endswith(" 오른")}
        ks = sorted(set(Ls) & set(Rs))
        if ks:
            row["글자 너비(평균)"] = item(float(np.mean([Rs[k]["o"] - Ls[k]["o"] for k in ks])), float(np.mean([Rs[k]["r"] - Ls[k]["r"] for k in ks])), "px")
        gaps = [(Ls[b]["o"] - Rs[a]["o"], Ls[b]["r"] - Rs[a]["r"]) for a, b in zip(ks, ks[1:]) if not (Rs[a].get("touch") or Ls[b].get("touch"))]
        if gaps:
            row["자간(글자 사이 빈칸 평균)"] = item(float(np.mean([g[0] for g in gaps])), float(np.mean([g[1] for g in gaps])), "px")
            row["자간(가장 어긋난 빈칸)"] = dict(o=None, r=None, d=round(max(abs(g[1] - g[0]) for g in gaps), 2), ok=round(max(abs(g[1] - g[0]) for g in gaps), 2) == 0, unit="px")
        if li + 1 in top:
            row["행간(다음 줄과 빈칸)"] = item(top[li + 1]["o"] - bot[li]["o"], top[li + 1]["r"] - bot[li]["r"], "px")
        cols = [hex2bgr(s["color"]) for s in l.get("spans", []) if s.get("color")]
        for s in l.get("spans", []):
            if s.get("grad"): cols += [hex2bgr(s["grad"]["start"]), hex2bgr(s["grad"]["end"])]
        mo = color_mask(O[y0:y1, x0:x1], cols); mr = color_mask(R[y0:y1, x0:x1], cols)
        row["획 굵기"] = item(stroke(mo), stroke(mr), "px")
        so = T2.slant_of(mo) if mo.sum() > 50 else None; sr = T2.slant_of(mr) if mr.sum() > 50 else None
        row["기울기"] = item(so, sr, "(가로 밀림/높이)")
        # 그라데이션: 색 묶음마다 따로(두 색 줄을 섞어 재면 「그라데이션 있음」으로 잘못 나옴 — 03JG-F0BEdU)
        sp_ = [s for s in l.get("spans", []) if s.get("color")]
        for s in sp_:
            cs = [hex2bgr(s["color"])] + ([hex2bgr(s["grad"]["start"]), hex2bgr(s["grad"]["end"])] if s.get("grad") else [])
            so_ = color_mask(O[y0:y1, x0:x1], cs); sr_ = color_mask(R[y0:y1, x0:x1], cs)
            go, gr = grad(O[y0:y1, x0:x1], so_), grad(R[y0:y1, x0:x1], sr_)
            if not (go and gr): continue
            nm = f" 「{s.get('chars', '').strip()}」" if len(sp_) > 1 else ""
            row["그라데이션 위쪽 색" + nm] = item(hexc(go[0]), hexc(gr[0]), "ΔE", hexs=True)
            row["그라데이션 아래쪽 색" + nm] = item(hexc(go[1]), hexc(gr[1]), "ΔE", hexs=True)
            # 「그라데이션 있음?」(ΔE 8 넘으면 있음) 칸은 문턱값 판정이라 뺌 — 위쪽·아래쪽 색을 #RRGGBB로 바로 견준다
        oc = hex2bgr(l["outline_color"]) if l.get("outline_color") else None
        if oc is not None:
            row["테두리 두께"] = item(outline_w(O[y0:y1, x0:x1], mo, oc), outline_w(R[y0:y1, x0:x1], mr, oc), "px")
        res.append(row)
    json.dump(dict(video_id=vid, lines=res), open(os.path.join(out, "값", f"{vid}_실측.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res

if __name__ == "__main__":
    out = sys.argv[1]; only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    for p in sorted(glob.glob(os.path.join(out, "값", "*.json"))):
        b = os.path.basename(p)[:-5]
        if b.endswith("_실측") or b in ("눈확인", "글자고르기"): continue
        if only and b not in only: continue
        try:
            r = measure(out, b); print(b, "줄", len(r), "· 다름", sum(1 for row in r for x in row.values() if x.get("ok") is False))
        except Exception as ex: print(b, "실측 실패:", ex)
