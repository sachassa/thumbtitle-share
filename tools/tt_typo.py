# tt_typo — 썸네일 그림 안의 글자(타이틀)를 재고, 잰 값으로 SVG/HTML로 다시 만들어 원본과 견준다. 이 PC 안에서만(외부 AI·웹 없음).
#   python tt_typo.py --ids 목록.tsv --img-dir <썸네일 폴더(영상ID.jpg 또는 채널ID/영상ID.jpg)> --out <결과 폴더> [--limit N] [--no-gate]
#   돌리는 파이썬: SETUP.md 대로 만든 venv (RapidOCR·OpenCV·Pillow·fontTools). Chrome으로 재현본을 찍는다. 폴더 자리는 tt_config.py.
# 결과: <out>/값/<id>.json(잰 값), <out>/그림/<id>_원본.png·_재현.png·_배경.png, <out>/재현/<id>.html, <out>/비교.html
# 재는 것: 줄마다 글자·글자 수·자리(%)·정렬·기울기, 글자 높이·글꼴 크기(px, 1080x1920 기준), 획 두께, 자간·행간,
#   채움 색(낱말 구간마다)·그라데이션, 테두리 두께·색, 그림자 자리·색, 글자 뒤 띠·상자, 가장 가까운 글꼴(이 PC 글꼴 가운데)과 맞는 정도.
import argparse, csv, glob, html, json, math, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_config as CFG
try:
    from gate import gate   # 무거운 일 문지기(만든 사람 PC에만 있음) — 없으면 건너뜀
except ImportError:
    def gate(*a, **k):
        if "--no-gate" in sys.argv: sys.argv.remove("--no-gate")

FONT_DIRS = ["C:/Windows/Fonts", os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"), CFG.FONT_BASE, CFG.FONT_EXTRA]
CANDS = [  # (보이는 이름, 파일, 가변 굵기 또는 None)
    ("맑은 고딕 Bold", "malgunbd.ttf", None), ("맑은 고딕", "malgun.ttf", None),
    ("나눔고딕 ExtraBold", "NanumGothicExtraBold.ttf", None), ("나눔고딕 Bold", "NanumGothicBold.ttf", None),
    ("나눔명조 ExtraBold", "NanumMyeongjoExtraBold.ttf", None), ("KoPub돋움 Bold", "KoPubDotumBold.ttf", None),
    ("KoPub바탕 Bold", "KoPubBatangBold.ttf", None), ("Black Han Sans(검은고딕)", "BlackHanSans-Regular.ttf", None),
    ("도현", "DoHyeon-Regular.ttf", None), ("주아", "Jua-Regular.ttf", None),
    ("Noto Sans KR 500", "NotoSansKR-VF.ttf", 500), ("Noto Sans KR 700", "NotoSansKR-VF.ttf", 700),
    ("Noto Sans KR 900", "NotoSansKR-VF.ttf", 900), ("은돋움", "UnDotum.ttf", None),
]
OCR_KO = CFG.OCR_KO
CHROME = next((p for p in ([CFG.CHROME] if CFG.CHROME else []) + ["C:/Program Files/Google/Chrome/Application/chrome.exe",
                           "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                           os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe")] if os.path.exists(p)), None)

def font_path(f):
    for d in FONT_DIRS:
        p = os.path.join(d, f)
        if os.path.exists(p): return p.replace("\\", "/")
    return None

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"): os.environ.setdefault(_k, "1")   # 한 갈래(Central 2026-11-24)
import numpy as np, cv2
cv2.setNumThreads(1)
from PIL import Image, ImageDraw, ImageFont

def imread(p):   # 한글 경로도 되게
    if not os.path.exists(p): return None
    return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
def imwrite(p, im): cv2.imencode(os.path.splitext(p)[1], im)[1].tofile(p)

_OCR = None
def ocr(im):
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1, rec_model_path=os.path.join(OCR_KO, "korean_PP-OCRv4_rec_mobile.onnx"), rec_keys_path=os.path.join(OCR_KO, "korean_dict.txt"))
    res, _ = _OCR(im)
    return [(np.array(b, np.float32), t, float(s)) for b, t, s in (res or [])]

def hexc(bgr): b, g, r = [int(round(x)) for x in bgr]; return f"#{r:02X}{g:02X}{b:02X}"
def lab(bgr_arr): return cv2.cvtColor(np.uint8(np.clip(bgr_arr, 0, 255)).reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32) * [100 / 255, 1, 1] - [0, 128, 128]
def dE(a, b): return float(np.linalg.norm(lab(np.array([a]))[0] - lab(np.array([b]))[0]))

def crop916(im):
    """가로 그림 가운데 9:16 을 잘라 쓴다 — 단 양옆이 정말 빈 띠(쇼츠 표지를 16:9 로 받아 생긴 검은·한 색 띠)일 때만.
    진짜 롱폼 표지는 그대로 둔다(2026-11-24 롱폼 시험: 「캐나다 이웃 부대찌개 반응」 1280px 줄을 가운데 405px만 잘라 읽기·글꼴 찾기가 다 틀림)."""
    h, w = im.shape[:2]
    if w > h:
        cw = int(round(h * 9 / 16)); x0 = (w - cw) // 2
        side = np.concatenate([im[:, :max(1, x0 - 2)].reshape(-1, 3), im[:, x0 + cw + 2:].reshape(-1, 3)]).astype(np.float32)
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32); lap = np.abs(cv2.Laplacian(g, cv2.CV_32F))
        sharp_side = float(np.concatenate([lap[:, :max(1, x0 - 2)].ravel(), lap[:, x0 + cw + 2:].ravel()]).mean())
        sharp_mid = float(lap[:, x0:x0 + cw].mean()) or 1.0
        # 양옆이 한 색 띠이거나 흐린 띠(선명도가 가운데의 0.3배 미만) → 쇼츠 표지. 실측 6장: 쇼츠 0.055~0.068 · 롱폼 0.745~0.96
        if len(side) and (float(side.std(0).mean()) < 12 or sharp_side / sharp_mid < 0.3):
            return im[:, x0:x0 + cw].copy()
    return im.copy()

# ---------- 글자 렌더(PIL) — 글꼴 맞추기와 기준선 계산 ----------
_FC = {}
def pil_font(name_file_w, size):
    _, f, w = name_file_w; key = (f, w, int(size))
    if key not in _FC:
        ft = ImageFont.truetype(font_path(f), max(4, int(size)))
        if w:
            try: ft.set_variation_by_axes([w])
            except Exception: pass
        _FC[key] = ft
    return _FC[key]

def render_mask(cand, text, size, ls):
    """글자를 한 자씩 놓아(자간 ls) 그린 흑백 그림과, 기준선 왼쪽 원점에 대한 잉크 상자."""
    ft = pil_font(cand, size)
    adv = [ft.getlength(ch) for ch in text]
    W = int(sum(adv) + ls * len(text) + size * 2) + 10; H = int(size * 2.2) + 10
    img = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(img)
    x = size * 0.5; base = size * 1.4
    for ch, a in zip(text, adv):
        dr.text((x, base), ch, font=ft, fill=255, anchor="ls"); x += a + ls
    m = np.array(img) > 127
    ys, xs = np.where(m)
    if not len(xs): return None, None
    box = (xs.min() - size * 0.5, ys.min() - base, xs.max() + 1 - size * 0.5, ys.max() + 1 - base)  # 원점 기준
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1], box

def stroke_w(mask):
    if mask.sum() < 20: return None
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    mx = cv2.dilate(dt, np.ones((3, 3), np.uint8))
    ridge = (dt > 0.5) & (dt >= mx - 1e-3)
    return float(2 * np.median(dt[ridge])) if ridge.any() else None

def iou(a, b):
    if a is None or b is None: return 0.0
    b2 = cv2.resize(b.astype(np.uint8), (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    u = (a | b2).sum(); return float((a & b2).sum() / u) if u else 0.0

def fit_font(text, fill_mask):
    """이 PC 글꼴마다 같은 잉크 높이·너비로 그려 모양 겹침(IoU)을 견준다."""
    t = text.replace(" ", " ")
    ys, xs = np.where(fill_mask)
    ink = fill_mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]; ih, iw = ink.shape
    out = []
    for cand in CANDS:
        if not font_path(cand[1]): continue
        m0, b0 = render_mask(cand, t, 100, 0)
        if m0 is None: continue
        size = 100 * ih / m0.shape[0]
        m1, _ = render_mask(cand, t, size, 0)
        if m1 is None: continue
        ls = (iw - m1.shape[1]) / max(1, len(t) - 1)
        ls = max(-size * 0.3, min(size * 0.6, ls))
        m2, b2 = render_mask(cand, t, size, ls)
        if m2 is None: continue
        sw_r = stroke_w(m2)
        out.append(dict(name=cand[0], file=cand[1], weight=cand[2], size=size, ls=ls, iou=iou(ink, m2), box=b2,
                        rw=m2.shape[1], rh=m2.shape[0], stroke_r=sw_r))
    out.sort(key=lambda x: -x["iou"])
    return out

def add_spaces(text, fill_mask, fit):
    """글자 읽기가 빼먹은 띄어쓰기를 잉크 빈틈으로 되살린다: 맞춘 글꼴로 글자마다 자리를 내고, 큰 빈틈에 가장 가까운 글자 사이에 넣는다."""
    if " " in text or len(text) < 3: return text
    col = fill_mask.any(0); ih = fill_mask.shape[0]
    gaps, run = [], None
    for x, c in enumerate(col):
        if not c:
            if run is None: run = x
        elif run is not None:
            if run > 0: gaps.append((run, x))
            run = None
    if not gaps: return text
    widths = [b - a for a, b in gaps]
    big = [g for g, w in zip(gaps, widths) if w > max(0.17 * ih, 2.2 * float(np.median(widths)))]
    if not big: return text
    cand = next(c for c in CANDS if c[0] == fit["name"])
    ft = pil_font(cand, fit["size"]); ls = fit["ls"]
    adv = [ft.getlength(ch) for ch in text]
    scale = fill_mask.shape[1] / fit["rw"]
    bounds = []; x = 0
    for k in range(1, len(text)):
        x += adv[k - 1] + ls; bounds.append((k, (x - ls / 2 - (fit["box"][0] + fit["size"] * 0)) * scale))
    ins = set()
    for a, b in big:
        c = (a + b) / 2
        k = min(bounds, key=lambda kb: abs(kb[1] - c))[0]; ins.add(k)
    return "".join((" " if k in ins else "") + ch for k, ch in enumerate(text))

def reread(fill_mask, text, sc):
    """자신 없는 줄: 글자 모양만 검은 글자·흰 바탕으로 떼어 다시 읽는다."""
    m = np.pad(fill_mask, 12)
    im = np.where(m, 0, 255).astype(np.uint8)
    f = 64 / max(1, fill_mask.shape[0]); im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    best = (text, sc)
    for _, t, s2 in ocr(im):
        if s2 > best[1] + 0.03 and t.strip(): best = (t.strip(), s2)
    return best

def reread_variants(im, quad, text, sc):
    """자신 없는 줄: 줄만 잘라 원본·뒤집기·최대 채널 뒤집기·회색 뒤집기 × 1·2배로 다시 읽는다.
    점수 = 평균 자신감 × (읽은 글자 수 / 줄 너비로 어림한 글자 수, 1 넘으면 1). 조각은 왼쪽부터 잇는다."""
    x0, y0 = quad.min(0).astype(int); x1, y1 = quad.max(0).astype(int)
    h = max(1, y1 - y0); pad = int(h * 0.3)
    c = im[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    if c.size == 0: return text, sc
    expect = max(1.0, (x1 - x0) / (h * 0.95))
    def score(t, cf): return cf * min(1.0, len(t.replace(" ", "")) / expect)
    best = (text, sc, score(text, sc))
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
    var = [c, 255 - c, cv2.cvtColor(255 - c.max(2), cv2.COLOR_GRAY2BGR), cv2.cvtColor(255 - g, cv2.COLOR_GRAY2BGR)]
    for v in var:
        for f in (1, 2):
            x = cv2.resize(v, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC) if f > 1 else v
            r = ocr(x)
            if not r: continue
            r.sort(key=lambda z: (round(z[0][:, 1].mean() / (h * f * 0.8)), z[0][:, 0].mean()))
            t = " ".join(z[1].strip() for z in r if z[1].strip()); cf = float(np.mean([z[2] for z in r]))
            sc2 = score(t, cf)
            if sc2 > best[2] + 0.02: best = (t, cf, sc2)
    return best[0], best[1]

# ---------- 한 줄 재기 ----------
def measure_line(img, quad, text):
    H, W = img.shape[:2]
    x0, y0 = quad[:, 0].min(), quad[:, 1].min(); x1, y1 = quad[:, 0].max(), quad[:, 1].max()
    h = y1 - y0; pad = int(max(4, h * 0.35))
    X0, Y0, X1, Y1 = int(max(0, x0 - pad)), int(max(0, y0 - pad)), int(min(W, x1 + pad)), int(min(H, y1 + pad))
    C = img[Y0:Y1, X0:X1].astype(np.float32); ch, cw = C.shape[:2]
    inner = np.zeros((ch, cw), bool); inner[int(y0 - Y0):int(y1 - Y0), int(x0 - X0):int(x1 - X0)] = True
    ring = np.zeros((ch, cw), bool); ring[:2] = ring[-2:] = True; ring[:, :2] = ring[:, -2:] = True
    L = lab(C.reshape(-1, 3)).reshape(ch, cw, 3)
    # 덩어리 4개로 나눠 상자 안에 몰린 덩어리 = 글자(채움·테두리)
    K = 4
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, lab_, cen = cv2.kmeans(L.reshape(-1, 3).astype(np.float32), K, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lab_ = lab_.reshape(ch, cw)
    # 위아래 이웃 줄이 섞이지 않게: 줄 상자 위아래로는 조금만(mg), 좌우로는 여백 전체를 본다
    mg = max(2, int(h * 0.08))
    nearH = np.zeros((ch, cw), bool); nearH[max(0, int(y0 - Y0) - mg):int(y1 - Y0) + mg, :] = True
    box_ok = np.zeros((ch, cw), bool)
    box_ok[max(0, int(y0 - Y0) - mg):int(y1 - Y0) + mg, max(0, int(x0 - X0) - mg):int(x1 - X0) + mg] = True
    info = []
    for k in range(K):
        m0 = lab_ == k
        if m0.sum() == 0: continue
        ringH = ring & nearH; onring = (m0 & ringH).sum() / max(1, ringH.sum())
        mh = m0 & nearH; nh = mh.sum()
        inside = (mh & inner).sum() / nh if nh else 0; cover = (m0 & inner).sum() / inner.sum()
        info.append(dict(k=k, m=m0 & box_ok, n=nh, inside=inside, cover=cover, ring=onring, bgr=C[m0 & box_ok].mean(0) if (m0 & box_ok).any() else C[m0].mean(0)))
    bg = max(info, key=lambda d: d["ring"])
    textc = [d for d in info if d is not bg and d["inside"] > 0.8 and d["cover"] > 0.03 and d["ring"] < 0.15]
    if not textc:
        textc = [max((d for d in info if d is not bg), key=lambda d: d["inside"], default=bg)]
    # 테두리: 글자 덩어리 가운데 「바깥(배경)과 맞닿는 비율」이 뚜렷하게 높은 것
    textm = np.zeros((ch, cw), bool)
    for d in textc: textm |= d["m"]
    outside = ~textm
    near_out = cv2.dilate(outside.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    for d in textc:
        edge = d["m"] & (cv2.dilate((~d["m"]).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        d["touch"] = (edge & near_out).sum() / max(1, edge.sum())
        d["dt"] = float(cv2.distanceTransform(d["m"].astype(np.uint8), cv2.DIST_L2, 3)[d["m"]].mean())
    outline = None
    if len(textc) >= 2:
        s = sorted(textc, key=lambda d: -d["touch"])
        if s[0]["touch"] - s[1]["touch"] > 0.3: outline = s[0]
    fills = [d for d in textc if d is not outline]
    fill = np.zeros((ch, cw), bool)
    for d in fills: fill |= d["m"]
    fill = cv2.morphologyEx(fill.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    _dt = cv2.distanceTransform(fill.astype(np.uint8), cv2.DIST_L2, 3)
    core = fill & (_dt >= max(1.0, float(np.percentile(_dt[fill], 60)) if fill.any() else 1.0))   # 획 안쪽: 색 재기용
    if fill.sum() < 15: return None
    # 배경이 테두리 색과 같으면(검은 띠 위 검은 테두리) 테두리를 따로 못 본다 — 그대로 적는다
    R = dict(text=text, box_px=[int(x0), int(y0), int(x1), int(y1)])
    ys, xs = np.where(fill)
    R["ink"] = [int(xs.min() + X0), int(ys.min() + Y0), int(xs.max() + 1 + X0), int(ys.max() + 1 + Y0)]
    ih = ys.max() + 1 - ys.min()
    R["ink_h_px"] = int(ih); R["ink_h_pct"] = round(ih / H * 100, 2)
    R["bg_color"] = hexc(bg["bgr"]); R["bg_flat"] = bool(np.std(L[ring], 0).mean() < 6)
    # 글자 뒤 띠: 줄 높이 띠를 그림 가로 전체로 봐서 한 색이면 띠
    band = img[int(y0):int(y1)].reshape(-1, 3).astype(np.float32)
    bandL = lab(band); R["back"] = ("가로 띠" if np.linalg.norm(bandL - lab(np.array([bg["bgr"]]))[0], axis=1).__lt__(12).mean() > 0.55
                                   else "상자" if R["bg_flat"] else "없음(그림 위)")
    # 채움 색: 열마다 평균 색 → 색이 바뀌는 곳에서 구간을 나눈다
    cols = []
    for x in range(cw):
        m = fill[:, x]
        cols.append(L[m, x].mean(0) if m.sum() >= 2 else None)
    segs = []; cur = None
    for x, c in enumerate(cols):
        if c is None: continue
        if cur and np.linalg.norm(c - cur["c"]) > 28 and x - cur["x1"] <= cw:
            # 잠깐 튀는 열은 무시: 다음 4열도 다르면 끊음
            nxt = [cols[j] for j in range(x, min(cw, x + 4)) if cols[j] is not None]
            if all(np.linalg.norm(n - cur["c"]) > 28 for n in nxt): segs.append(cur); cur = None
        if cur is None: cur = dict(x0=x, x1=x, c=c.copy(), n=1)
        else: cur["x1"] = x; cur["n"] += 1; cur["c"] = cur["c"] + (c - cur["c"]) / cur["n"]
    if cur: segs.append(cur)
    segs = [s for s in segs if s["x1"] - s["x0"] >= max(3, ih * 0.3)] or segs
    spans = []
    tx0, tx1 = xs.min(), xs.max() + 1
    for s in segs:
        m = fill.copy(); m[:, :s["x0"]] = False; m[:, s["x1"] + 1:] = False
        yy, _ = np.where(m)
        top = C[m & (np.arange(ch)[:, None] < np.percentile(yy, 30))]; bot = C[m & (np.arange(ch)[:, None] > np.percentile(yy, 70))]
        mc = m & core
        allc = (np.median(C[mc], 0) if mc.sum() >= 5 else C[m].mean(0)); grad = None
        if len(top) and len(bot) and dE(top.mean(0), bot.mean(0)) > 18:
            grad = dict(dir="위→아래", start=hexc(top.mean(0)), end=hexc(bot.mean(0)))
        a = (s["x0"] - tx0) / (tx1 - tx0); b = (s["x1"] + 1 - tx0) / (tx1 - tx0)
        spans.append(dict(color=hexc(allc), grad=grad, from_pct=round(max(0, a) * 100), to_pct=round(min(1, b) * 100)))
    # 이웃 구간이 같은 색이면 합친다
    merged = []
    for s in spans:
        if merged and not s["grad"] and not merged[-1]["grad"] and dE(np.array(_hex2bgr(s["color"])), np.array(_hex2bgr(merged[-1]["color"]))) < 20:
            merged[-1]["to_pct"] = s["to_pct"]
        else: merged.append(s)
    n = len(text)
    for s in merged:
        s["chars"] = text[int(round(s["from_pct"] / 100 * n)):int(round(s["to_pct"] / 100 * n))]
    R["fill"] = merged
    R["stroke_px"] = round(stroke_w(fill) or 0, 2)
    # 테두리 두께
    if outline is not None:
        uni = fill | outline["m"]
        dto = cv2.distanceTransform((~fill).astype(np.uint8), cv2.DIST_L2, 3)
        oedge = uni & (cv2.dilate((~uni).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        R["outline"] = dict(color=hexc(outline["bgr"]), width_px=round(float(np.median(dto[oedge])), 2) if oedge.any() else None)
    else:
        R["outline"] = None
        uni = fill
    # 그림자: 글자 바깥의 어두운 덩어리가 글자 모양을 어느 쪽으로 밀어 놓은 꼴인지
    dark = (~uni) & (np.linalg.norm(L - lab(np.array([bg["bgr"]]))[0], axis=2) > 25) & (L[..., 0] < 35) & inner
    R["shadow"] = None
    if dark.sum() > uni.sum() * 0.05:
        best = (0, 0, 0)
        for dy in range(-1, 9):
            for dx in range(-8, 9):
                if dx == 0 and dy == 0: continue
                sh = np.roll(np.roll(uni, dy, 0), dx, 1) & ~uni
                if sh.sum() == 0: continue
                sc = (sh & dark).sum() / sh.sum()
                if sc > best[0]: best = (sc, dx, dy)
        if best[0] > 0.55 and (abs(best[1]) + abs(best[2])) >= 2:
            R["shadow"] = dict(dx=best[1], dy=best[2], color=hexc(C[dark].mean(0)), match=round(best[0], 2))
    ang = math.degrees(math.atan2(quad[1, 1] - quad[0, 1], quad[1, 0] - quad[0, 0]))
    R["tilt_deg"] = round(ang, 1)
    R["_fill_mask"] = fill[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    R["_crop"] = (X0, Y0, X1, Y1); R["_uni"] = uni
    return R

def _hex2bgr(h): return [int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)]

def role_of(y_mid, H):
    r = y_mid / H
    return "위 제목" if r < 0.33 else "아래 글(자막)" if r > 0.55 else "가운데 글"

# ---------- 한 장 ----------
DROPS = []
def merge_row(items):
    """같은 줄에 붙어 있는 글자 인식 상자를 하나로 합친다: 세로로 60% 넘게 겹치고, 높이 비가 0.75~1.33이고, 가로 틈이 높이보다 좁을 때.
    (2026-11-25 「한국이 미국 야구 다 망쳐놨다」 셋째 줄을 「필수…야구장에」·「역대급으로…상황」 두 상자로 읽어 뒤쪽이 버려지고,
    앞쪽에 정답 줄 26자를 다 맞추느라 글자 겹침 0.0 — 실측)"""
    its = [[np.asarray(q, np.float32), t, s_] for q, t, s_ in items]
    changed = True
    while changed:
        changed = False
        its.sort(key=lambda z: float(z[0][:, 0].min()))
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                a, b = its[i][0], its[j][0]
                ay0, ay1 = a[:, 1].min(), a[:, 1].max(); by0, by1 = b[:, 1].min(), b[:, 1].max()
                ha, hb = ay1 - ay0, by1 - by0
                if min(ha, hb) <= 0 or not (0.75 <= ha / hb <= 1.33): continue
                ov = min(ay1, by1) - max(ay0, by0)
                if ov < 0.6 * min(ha, hb): continue
                gap = b[:, 0].min() - a[:, 0].max()
                if gap > max(ha, hb) or gap < -0.5 * max(ha, hb): continue
                x0 = min(a[:, 0].min(), b[:, 0].min()); x1 = max(a[:, 0].max(), b[:, 0].max())
                y0 = min(ay0, by0); y1 = max(ay1, by1)
                q = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float32)
                DROPS.append((f"{its[i][1]} + {its[j][1]}", "@넓힘 같은 줄에 붙은 두 글자 인식 상자를 하나로 합침"))
                its[i] = [q, (its[i][1].strip() + " " + its[j][1].strip()).strip(), min(its[i][2], its[j][2])]
                del its[j]; changed = True; break
            if changed: break
    return [(q, t, s_) for q, t, s_ in its]

def analyze(vid, path, outdir, keep_small=False):
    DROPS.clear()
    raw = imread(path)
    im = crop916(raw); H, W = im.shape[:2]
    lines = []   # 줄 찾기에서 버린 글과 까닭(tt_typo3가 로그에 남김 — 2026-11-25 「배구 일본반응」 노란 둘째 줄이 말없이 빠짐)
    for quad, text, sc in merge_row(ocr(im)):
        text = text.strip()
        if not text or sc < 0.5: DROPS.append((text, f"글자 인식 믿음 {sc:.2f}")); continue
        if (quad[:, 1].max() - quad[:, 1].min()) < H * (0.008 if keep_small else 0.022): DROPS.append((text, "아주 작음")); continue   # 아주 작은 글은 뺀다(keep_small = 출처 같은 작은 글도 남김, tt_typo3)
        R = measure_line(im, quad, text)
        if R is None: DROPS.append((text, "글자 재기 실패")); continue
        # 글자 인식 상자가 줄 끝을 놓쳐(따옴표·말줄임표 등) 잉크가 자른 범위의 왼·오른 끝에 닿으면, 그쪽으로 글자 높이만큼 넓혀 다시 잰다(4번까지)
        # (2026-11-25 「배구 일본반응」 「“어디서도 연락 안 왔는데…”」의 앞 따옴표 반쪽·끝 「…”」가 잘려 글자 자리가 모두 밀림 — 눈으로 봄)
        for _ in range(4):
            cx0, cy0, cx1, cy1 = R["_crop"]; ix0, iy0, ix1, iy1 = R["ink"]
            hq = float(quad[:, 1].max() - quad[:, 1].min())
            # 글자 덩어리는 인식 상자 ± mg 안에서만 잡히므로(measure_line box_ok) 그 경계에 닿았는지를 본다
            mg_ = max(2, int(hq * 0.08)); qx0_, qx1_ = float(quad[:, 0].min()), float(quad[:, 0].max())
            gl = ix0 <= qx0_ - mg_ + 2 and qx0_ - mg_ > 0; gr = ix1 >= qx1_ + mg_ - 3 and qx1_ + mg_ < W
            if not (gl or gr): break
            q2 = quad.astype(np.float32).copy()
            if gl: q2[:, 0] = np.where(q2[:, 0] <= q2[:, 0].mean(), np.maximum(0, q2[:, 0] - hq), q2[:, 0])
            if gr: q2[:, 0] = np.where(q2[:, 0] > q2[:, 0].mean(), np.minimum(W - 1, q2[:, 0] + hq), q2[:, 0])
            R2 = measure_line(im, q2, text)
            if R2 is None: break
            DROPS.append((text, f"@넓힘 줄 끝이 잘려 {'왼' if gl else ''}{'오른' if gr else ''}쪽으로 넓힘(잉크 {R['ink'][0]}~{R['ink'][2]} → {R2['ink'][0]}~{R2['ink'][2]})"))
            quad, R = q2, R2
        ocr_first = text
        if sc < 0.93:
            t2, s2 = reread_variants(im, quad, text, sc)
            if t2 != text:
                R2 = measure_line(im, quad, t2)
                if R2 is not None: R, text, sc = R2, t2, s2
        R["ocr_conf"] = round(sc, 2); R["role"] = role_of((quad[:, 1].min() + quad[:, 1].max()) / 2, H)
        if ocr_first != text: R["ocr_first"] = ocr_first
        fits = fit_font(text, R["_fill_mask"])
        if fits:
            t3 = add_spaces(text, R["_fill_mask"], fits[0])
            if t3 != text:
                R2 = measure_line(im, quad, t3)
                if R2 is not None:
                    for k in ("ocr_conf", "role", "ocr_first"):
                        if k in R: R2[k] = R[k]
                    R, text = R2, t3; R["spaces_added"] = True
                    fits = fit_font(text, R["_fill_mask"])
        if fits:
            b = fits[0]; R["font"] = dict(best=b["name"], file=b["file"], weight=b["weight"], match=round(b["iou"], 2),
                                         next=[f"{f['name']} {f['iou']:.2f}" for f in fits[1:3]])
            R["font_size_px"] = round(b["size"], 1); R["font_size_pct"] = round(b["size"] / H * 100, 2)
            R["font_size_1080"] = round(b["size"] * 1920 / H, 1)
            R["letter_spacing_px"] = round(b["ls"], 2); R["letter_spacing_em"] = round(b["ls"] / b["size"], 3)
            R["_fit"] = b
            if b["stroke_r"] and R["stroke_px"]:
                R["bold_extra_px"] = round(max(0.0, (R["stroke_px"] - b["stroke_r"]) / 2), 2)
        x0, y0, x1, y1 = R["ink"]
        R["pos"] = dict(left_pct=round(x0 / W * 100, 1), top_pct=round(y0 / H * 100, 1), cx_pct=round((x0 + x1) / 2 / W * 100, 1),
                        width_pct=round((x1 - x0) / W * 100, 1))
        R["chars"] = len(text.replace(" ", ""))
        lines.append(R)
    lines.sort(key=lambda r: r["ink"][1])
    # 같은 자리 무리(위 제목 등)의 행간·정렬
    groups = {}
    for r in lines: groups.setdefault(r["role"], []).append(r)
    for g, rs in groups.items():
        for a, b in zip(rs, rs[1:]):
            if "_fit" in a and "_fit" in b:
                base_a = a["ink"][3] - a["_fit"]["box"][3]; base_b = b["ink"][3] - b["_fit"]["box"][3]
                b["line_gap_px"] = int(b["ink"][1] - a["ink"][3])
                b["line_height_ratio"] = round((base_b - base_a) / ((a["_fit"]["size"] + b["_fit"]["size"]) / 2), 2)
        if len(rs) >= 2:
            L_ = np.std([r["ink"][0] for r in rs]); Cc = np.std([(r["ink"][0] + r["ink"][2]) / 2 for r in rs]); Rr = np.std([r["ink"][2] for r in rs])
            al = ["왼쪽", "가운데", "오른쪽"][int(np.argmin([L_, Cc, Rr]))]
        else:
            cx = (rs[0]["ink"][0] + rs[0]["ink"][2]) / 2 / W
            al = "가운데" if abs(cx - 0.5) < 0.06 else "왼쪽" if cx < 0.5 else "오른쪽"
        for r in rs: r["align"] = al
    return im, lines

# ---------- 재현 ----------
def build_svg(vid, im, lines, bgfile, fix=None):
    H, W = im.shape[:2]; fix = fix or {}
    defs, body, faces = [], [], {}
    for i, r in enumerate(lines):
        if "_fit" not in r: continue
        b = r["_fit"]; fam = f"f{abs(hash((b['file'], b['weight']))) % 10**6}"
        faces[fam] = (font_path(b["file"]), b["weight"])
        dx, dy, sc = fix.get(i, (0, 0, 1.0))
        size = b["size"] * sc
        x = r["ink"][0] - b["box"][0] * sc + dx; y = r["ink"][3] - b["box"][3] * sc + dy
        ls = b["ls"] * sc
        # 채움: 구간마다 tspan, 그라데이션이면 linearGradient
        tsp = []
        for j, s in enumerate(r["fill"]):
            col = s["color"]
            if s["grad"]:
                gid = f"g{i}_{j}"
                defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="{r["ink"][1]}" x2="0" y2="{r["ink"][3]}">'
                            f'<stop offset="0" stop-color="{s["grad"]["start"]}"/><stop offset="1" stop-color="{s["grad"]["end"]}"/></linearGradient>')
                col = f"url(#{gid})"
            tsp.append((s.get("chars") or "", col))
        if not any(t for t, _ in tsp): tsp = [(r["text"], r["fill"][0]["color"] if r["fill"] else "#FFFFFF")]
        # 구간 글자를 합친 것이 원문과 다르면(반올림) 원문을 마지막 구간에 맞춘다
        joined = "".join(t for t, _ in tsp)
        if joined != r["text"]:
            n = len(r["text"]); cut = 0; nt = []
            for k, (t, c) in enumerate(tsp):
                e = n if k == len(tsp) - 1 else min(n, cut + len(t)); nt.append((r["text"][cut:e], c)); cut = e
            tsp = nt
        spans = "".join(f'<tspan fill="{c}">{html.escape(t)}</tspan>' for t, c in tsp if t)
        common = f'x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size:.2f}" letter-spacing="{ls:.2f}" xml:space="preserve"'
        if r["tilt_deg"] and abs(r["tilt_deg"]) > 1.5:
            common += f' transform="rotate({r["tilt_deg"]} {x:.1f} {y:.1f})"'
        extra = r.get("bold_extra_px") or 0
        if r.get("shadow"):
            s = r["shadow"]; ow = (r["outline"] or {}).get("width_px") or 0
            body.append(f'<text {common} transform="translate({s["dx"]} {s["dy"]})" fill="{s["color"]}" stroke="{s["color"]}" stroke-width="{2*(ow+extra):.2f}" stroke-linejoin="round">{html.escape(r["text"])}</text>')
        if r.get("outline") and r["outline"].get("width_px"):
            o = r["outline"]
            body.append(f'<text {common} fill="{o["color"]}" stroke="{o["color"]}" stroke-width="{2*(o["width_px"]+extra):.2f}" stroke-linejoin="round">{html.escape(r["text"])}</text>')
        if extra > 0.3:
            body.append(f'<text {common} fill="none" stroke="{tsp[0][1]}" stroke-width="{2*extra:.2f}" stroke-linejoin="round">{spans}</text>')
        body.append(f'<text {common}>{spans}</text>')
    ff = "".join("@font-face{font-family:%s;src:url('file:///%s');}" % (k, p) for k, (p, w) in faces.items())
    ffv = "".join(f"text[font-family={k}]{{font-variation-settings:'wght' {w};}}" for k, (p, w) in faces.items() if w)
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{ff}{ffv}html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#000}}</style></head>'
            f'<body><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{"".join(defs)}</defs>'
            f'<image href="{bgfile}" x="0" y="0" width="{W}" height="{H}"/>{"".join(body)}</svg></body></html>')

def chrome_shot(htmlfile, png, W, H):
    prof = tempfile.mkdtemp(prefix="tt_chrome_", dir=CFG.TMP)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--renderer-process-limit=1", "--disable-extensions", "--js-flags=--max-old-space-size=128", "--hide-scrollbars", f"--user-data-dir={prof}", "--allow-file-access-from-files",
                    "--force-device-scale-factor=1", f"--window-size={W},{H}", "--virtual-time-budget=1500", f"--screenshot={png}",
                    "file:///" + os.path.abspath(htmlfile).replace("\\", "/")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

def text_mask(img, bg, region):
    X0, Y0, X1, Y1 = region
    d = np.abs(img[Y0:Y1, X0:X1].astype(np.int16) - bg[Y0:Y1, X0:X1].astype(np.int16)).max(2)
    return d > 45

def compare(im, rep, bgim, lines):
    out = []
    for i, r in enumerate(lines):
        if "_fit" not in r: out.append(None); continue
        X0, Y0, X1, Y1 = r["_crop"]; pad = int((Y1 - Y0) * 0.4)
        reg = (max(0, X0 - pad), max(0, Y0 - pad), min(im.shape[1], X1 + pad), min(im.shape[0], Y1 + pad))
        a = text_mask(im, bgim, reg); b = text_mask(rep, bgim, reg)
        k3 = np.ones((3, 3), np.uint8)
        da = cv2.dilate(a.astype(np.uint8), k3) > 0; db = cv2.dilate(b.astype(np.uint8), k3) > 0
        P = float((b & da).sum() / b.sum()) if b.sum() else 0; Rc = float((a & db).sum() / a.sum()) if a.sum() else 0
        io = 2 * P * Rc / (P + Rc) if P + Rc else 0   # 모양 겹침: 1픽셀 안 어긋남은 같은 것으로 본 겹침(F1)
        ya, xa = np.where(a); yb, xb = np.where(b)
        if len(xa) and len(xb):
            ddx = float(xa.mean() - xb.mean()); ddy = float(ya.mean() - yb.mean())
            sc = float((ya.max() - ya.min() + 1) / max(1, yb.max() - yb.min() + 1))
        else: ddx = ddy = 0; sc = 1
        # 색: 둘 다 글자인 곳의 평균 색 차이(Lab)
        both = a & b
        if both.sum() > 10:
            ca = im[reg[1]:reg[3], reg[0]:reg[2]][both].mean(0); cb = rep[reg[1]:reg[3], reg[0]:reg[2]][both].mean(0); de = dE(ca, cb)
        else: de = None
        verdict = "같음" if io >= 0.85 and (de or 99) < 12 else "거의 같음" if io >= 0.7 and (de or 99) < 22 else "다름"
        out.append(dict(iou=round(io, 2), dx=round(ddx, 1), dy=round(ddy, 1), size_ratio=round(sc, 3), dE=round(de, 1) if de is not None else None, verdict=verdict))
    return out

def why(r, c):
    if not c or c["verdict"] != "다름": return ""
    w = []
    if r.get("font", {}).get("match", 1) < 0.55: w.append(f"맞는 글꼴이 이 PC에 없는 듯(가장 가까운 {r['font']['best']} 겹침 {r['font']['match']})")
    if c["dE"] is not None and c["dE"] >= 22: w.append(f"색 차이 큼(ΔE {c['dE']})")
    if r["ocr_conf"] < 0.85: w.append(f"글자 읽기 자신 없음({r['ocr_conf']})")
    if r["back"] == "없음(그림 위)": w.append("그림 위 글자라 글자만 떼기 어려움")
    if abs(c["dx"]) > 3 or abs(c["dy"]) > 3: w.append(f"자리 어긋남({c['dx']},{c['dy']}px)")
    return " · ".join(w) or "잰 값 일부가 맞지 않음"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True); ap.add_argument("--img-dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int); ap.add_argument("--org", default="thumbtitle")
    a = ap.parse_args()
    for d in ("값", "그림", "재현"): os.makedirs(os.path.join(a.out, d), exist_ok=True)
    ids = []
    with open(a.ids, encoding="utf-8-sig") as fh:
        for i, line in enumerate(fh):
            v = line.split("\t")[0].strip()
            if v and not (i == 0 and v == "video_id"): ids.append(v)
    ids = ids[: a.limit or None]
    rows = []
    for n, vid in enumerate(ids, 1):
        cand = glob.glob(os.path.join(a.img_dir, vid + ".jpg")) + glob.glob(os.path.join(a.img_dir, "*", vid + ".jpg"))
        if not cand: print(f"{n}/{len(ids)} {vid}: 그림 없음", flush=True); continue
        try:
            im, lines = analyze(vid, cand[0], a.out)
            H, W = im.shape[:2]
            G = os.path.join(a.out, "그림")
            imwrite(os.path.join(G, f"{vid}_원본.png"), im)
            mask = np.zeros((H, W), np.uint8)
            for r in lines:
                X0, Y0, X1, Y1 = r["_crop"]
                u = r["_uni"].astype(np.uint8) * 255
                sh = r.get("shadow")
                if sh: u = np.maximum(u, np.roll(np.roll(u, sh["dy"], 0), sh["dx"], 1))
                mask[Y0:Y1, X0:X1] = np.maximum(mask[Y0:Y1, X0:X1], u)
            mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
            bgim = cv2.inpaint(im, mask, 5, cv2.INPAINT_TELEA)
            imwrite(os.path.join(G, f"{vid}_배경.png"), bgim)
            hf = os.path.join(a.out, "재현", f"{vid}.html"); png = os.path.join(G, f"{vid}_재현.png")
            bgurl = "../그림/" + f"{vid}_배경.png"
            open(hf, "w", encoding="utf-8").write(build_svg(vid, im, lines, bgurl)); chrome_shot(hf, png, W, H)
            rep = imread(png); cmp1 = compare(im, rep, bgim, lines)
            # 한 번 고치기: 자리·크기 어긋남을 되먹임
            fix = {i: (c["dx"], c["dy"], c["size_ratio"] if 0.85 < c["size_ratio"] < 1.15 else 1.0) for i, c in enumerate(cmp1) if c}
            open(hf, "w", encoding="utf-8").write(build_svg(vid, im, lines, bgurl, fix)); chrome_shot(hf, png, W, H)
            rep2 = imread(png); cmp2 = compare(im, rep2, bgim, lines)
            for r, c1, c2 in zip(lines, cmp1, cmp2):
                r["compare_first"] = c1; r["compare"] = c2; r["why"] = why(r, c2)
                for k in [k for k in r if k.startswith("_")]: r.pop(k)
            val = dict(video_id=vid, canvas=[W, H], src=cand[0].replace("\\", "/"), lines=lines)
            json.dump(val, open(os.path.join(a.out, "값", f"{vid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            rows.append(val)
            v = [l["compare"]["verdict"] for l in lines if l.get("compare")]
            print(f"{n}/{len(ids)} {vid}: 줄 {len(lines)} — " + ", ".join(f"{l['text'][:10]}={l['compare']['verdict'] if l.get('compare') else '-'}" for l in lines), flush=True)
        except Exception as e:
            import traceback; traceback.print_exc(); print(f"{n}/{len(ids)} {vid}: 오류 — {e}", flush=True)
    print(f"끝 — {len(rows)}장", flush=True)

if __name__ == "__main__":
    if "--org" not in sys.argv: sys.argv += ["--org", "thumbtitle"]
    gate("tt-typo", "보통", 1500)
    main()
