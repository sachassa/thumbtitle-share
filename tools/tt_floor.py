# tt_floor — 「일치(JPEG 바닥)」 판정. 2판(docs/검수기준.md 5번: 획·기울기 바닥 문턱 · 가장자리 날카로움(밝기) · 바닥 61번 · 가장 큰 값 문턱 — TitleMatch 합의, 운영자 확인 2026-11-25 「이대로 적용」) docs/검수기준.md (ThumbTitle·TitleMatch 합의, 운영자 확인 2026-11-25).
#   원본이 JPEG이면 정답 그림도 압축만으로 값이 흔들린다(조니 뎁: 정답을 압축해도 138항목 중 102~109개 다름, 실측).
#   그래서 재현 R을 원본 jpg와 같은 양자화 표·색 줄임으로, 압축 칸(8x8) 자리를 16가지로 옮겨 압축한 R'ₖ 를 R과 견줘
#   「압축만으로 생기는 차이(바닥)」를 장마다 잰다. 판정 비교(원본 대 R)는 압축하지 않는다.
#   종류(줄 값·자간·색·글자 상자·글자 모양)마다 원본 대 R 의 평균·가장 큰 값이 둘 다 문턱(16번 바닥의 평균+3×표준편차) 이하이고,
#   그 밖 항목(획·기울기·테두리·글자 수·색 나뉨)은 완전히 같으면 「일치(JPEG 바닥)」.
#   장마다 틀린 그림 시험(0.05px 옮김 · 흐림 더함)이 떨어지는지, 바닥에 안 쓴 칸 자리의 정답이 붙는지도 함께 잰다 — 안 맞으면 「판정 못 함」.
#   글자 자르는 자리·색 기준은 진짜 원본에서 한 번 정한 것을 모든 견줌에 같이 씀(바닥이 부풀지 않게, 실측).
#   바탕: TitleMatch tm_floor_judge.py · tm_floor_test.py(넘겨받음 2026-11-25).
import io
import numpy as np, cv2
from PIL import Image, JpegImagePlugin

CHECK = [(2, 4), (6, 6), (1, 1)]   # 바닥에 안 쓰는 칸 자리 — 정답이 붙는지 시험용
PHASES = [(x, y) for y in range(8) for x in range(8) if (x, y) not in CHECK]   # 칸 자리 64가지 다(시험용 3개 뺌) = 61번 — 16번으로는 정답이 문턱을 살짝 넘는 장이 나옴(4-dMi, 실측)
KINDS = ["줄 값(px)", "자간(px)", "색(RGB 채널 차)", "글자 상자(px)", "글자 모양(1-겹침)", "가장자리 흐림(px)",
         "획 굵기(px)", "기울기", "가장자리 날카로움(밝기)"]
OTHER = "그 밖(테두리·글자 수·색 나뉨)"


def jpeg_phase(r, src, dx, dy):
    a = np.clip(np.round(r), 0, 255).astype(np.uint8)
    a = np.pad(a, ((dy, 0), (dx, 0), (0, 0)), mode="edge")
    b = io.BytesIO(); Image.fromarray(a).save(b, "JPEG", qtables=src.quantization, subsampling=JpegImagePlugin.get_sampling(src))
    return np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGB"))[dy:, dx:].copy()


def items(lines):
    out = {}
    for li, L in enumerate(lines):
        for k, v in L["items"].items():
            key = "%d줄|%s" % (li + 1, k)
            if v["ok"]: out[key] = 0.0
            elif isinstance(v["d"], (int, float)): out[key] = abs(float(v["d"]))
            elif isinstance(v["d"], str) and v["d"].startswith("RGB차"): out[key] = float(max(abs(int(t)) for t in v["d"][4:].split(",")))
            else: out[key] = 1e9
        for gi, g in enumerate(L["glyphs"]):
            key = "%d줄|글자%d(%s)" % (li + 1, gi + 1, g["ch"])
            out[key + " 상자"] = float(max(abs(x) for x in g["d_box"])) if g["d_box"] else 1e9
            out[key + " 모양(1-겹침)"] = round(1.0 - g["f1"], 4)
    return out


def kind(key):
    k = key.split("|")[1]
    if k.startswith("획"): return "획 굵기(px)"
    if k.startswith("기울기"): return "기울기"
    if k.startswith("날카로움"): return "가장자리 날카로움(밝기)"
    if k.startswith("글자") and "상자" in k: return "글자 상자(px)"
    if k.startswith("글자") and "모양" in k: return "글자 모양(1-겹침)"
    if k.startswith("자간"): return "자간(px)"
    if k.startswith("가장자리"): return "가장자리 흐림(px)"
    if "색" in k and "나뉨" not in k: return "색(RGB 채널 차)"
    if k.startswith(("줄 ", "기준선", "글자 높이", "글자 너비", "행간")): return "줄 값(px)"
    return OTHER


def stats(it):
    """종류별 평균·가장 큰 값(1e9 = 못 잼/글자 다름은 따로 셈)."""
    s = {}
    for k, v in it.items():
        s.setdefault(kind(k), []).append(v)
    return {kd: dict(mean=float(np.mean([x for x in vs if x < 1e8] or [0.0])), max=float(max([x for x in vs if x < 1e8] or [0.0])),
                     bad=sum(1 for x in vs if x >= 1e8), nz=sum(1 for x in vs if x > 0)) for kd, vs in s.items()}


def verdict(st, thr):
    """st = 견줄 그림의 종류별 값, thr = 문턱. 돌려줌: (통과?, 넘은 곳 목록)"""
    over = []
    o = st.get(OTHER, dict(nz=0, bad=0))
    if o["nz"] or o["bad"]: over.append(f"{OTHER} {o['nz'] + o['bad']}개 다름(완전히 같아야 함)")
    for kd in KINDS:
        if kd not in st: continue
        a = st[kd]
        if a["bad"]: over.append(f"{kd} 못 잰 글자 {a['bad']}개")
        if a["mean"] > thr[kd]["mean"] + 1e-9: over.append(f"{kd} 평균 {a['mean']:.4g} > 문턱 {thr[kd]['mean']:.4g}")
        if a["max"] > thr[kd]["max"] + 1e-9: over.append(f"{kd} 가장 큰 값 {a['max']:.4g} > 문턱 {thr[kd]['max']:.4g}")
    return not over, over


def subshift(img, dx):
    """그림을 가로로 dx px 옮김(소수, Lanczos)."""
    return np.clip(cv2.warpAffine(img.astype(np.float32), np.float32([[1, 0, dx], [0, 1, 0]]), (img.shape[1], img.shape[0]),
                                  flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE), 0, 255).round().astype(np.uint8)


def _Y(img):
    return cv2.cvtColor(np.ascontiguousarray(img).astype(np.uint8), cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)


def sharp_sel(o, regs):
    """가장자리 날카로움을 잴 자리 — 진짜 원본에서 한 번: 5x5 밝기 차 > 60 이고 3x3 안에서 기울기가 가장 큰 화소(경계 능선)."""
    y = _Y(o); g = np.hypot(cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3))
    c = cv2.dilate(y, np.ones((5, 5), np.uint8)) - cv2.erode(y, np.ones((5, 5), np.uint8))
    ridge = (g >= cv2.dilate(g, np.ones((3, 3), np.uint8)) - 1e-3) & (c > 60)
    return [(rg["band"], ridge[rg["band"][0]:rg["band"][1]]) for rg in regs]


def sharp(img, sel):
    """줄마다 가장자리 날카로움 = 경계 능선 화소의 (밝기 기울기 ÷ 5x5 밝기 차) 중앙값. 밝기(Y)만 — JPEG 색 줄임(4:2:0)의 영향을 안 받음."""
    y = _Y(img); g = np.hypot(cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3)) / 8
    c = cv2.dilate(y, np.ones((5, 5), np.uint8)) - cv2.erode(y, np.ones((5, 5), np.uint8))
    return [float(np.median(g[y0:y1][m] / np.maximum(c[y0:y1][m], 1))) if m.any() else None for (y0, y1), m in sel]


def thin_wrong(folder, vid, delta=-0.10):
    """틀린 그림 「덧굵기 −0.10px」: 정밀 맞춤 저장값(값/<id>_정밀.json)으로 굵기만 바꿔 임시 폴더에서 다시 그림.
    저장값 그대로(delta=0) 그리면 재현과 화소 0개 다름(실측 2026-11-25, 조니 뎁·NEON). 정밀 기록이 없으면 None."""
    import json, os, shutil, tempfile, tt_refine as RF
    pj = os.path.join(folder, "값", vid + "_정밀.json")
    if not os.path.exists(pj) or not os.path.exists(os.path.join(folder, "그림", vid + "_재현_크롬.png")): return None
    saved = {L["text"]: L["P"] for L in json.load(open(pj, encoding="utf-8"))["lines"]}
    d = tempfile.mkdtemp(prefix="tt_thin_"); os.makedirs(d + "/값"); os.makedirs(d + "/그림")
    fit0 = RF.Line.fit
    try:
        for f in (vid + ".json", vid + "_정밀.json"): shutil.copy(os.path.join(folder, "값", f), os.path.join(d, "값", f))
        for f in ("_원본.png", "_배경.png", "_재현_크롬.png"): shutil.copy(os.path.join(folder, "그림", vid + f), os.path.join(d, "그림", vid + f))
        shutil.copy(os.path.join(folder, "그림", vid + "_재현_크롬.png"), os.path.join(d, "그림", vid + "_재현.png")); os.utime(os.path.join(d, "그림", vid + "_재현.png"), (0, 0))
        def fit(self, log):
            P = dict(saved[self.ln["text"]]); P["pens"] = [tuple(p) for p in P["pens"]]; P["e"] = float(P["e"]) + delta; self.P = P; self.glyphs = []
        RF.Line.fit = fit
        RF.run(d, vid, [])
        return np.asarray(Image.open(os.path.join(d, "그림", vid + "_재현.png")).convert("RGB")).copy()
    except Exception as e:
        print("  덧굵기 틀린 그림 못 만듦:", e); return None
    finally:
        RF.Line.fit = fit0; shutil.rmtree(d, ignore_errors=True)


def judge(V, o, r, regs, texts, params, src_path, strict_ok, log=print, extra_wrongs=None):
    """V = tt_verify 모듈. 돌려줌 dict(판정, 바닥…) — 원본이 jpg가 아니면(src_path 없음) 바닥 0 = 완전히 같아야 일치."""
    if strict_ok:
        return {"판정": "100% 일치", "match": True, "까닭": "모든 항목이 완전히 같음"}
    if not src_path:
        return {"판정": "일치 안 됨", "match": False, "까닭": "원본 JPEG를 못 찾음(또는 JPEG 아님) → 바닥 0, 완전히 같아야 일치"}
    src = Image.open(src_path)
    if src.format != "JPEG" or not getattr(src, "quantization", None):
        return {"판정": "일치 안 됨", "match": False, "까닭": "원본이 JPEG 아님 → 바닥 0, 완전히 같아야 일치"}
    sel = sharp_sel(o, regs)
    meas = lambda img: (V.measure_image(img, regs, texts, params), sharp(img, sel))
    mr = meas(r)
    def cmp2(ma, mb):
        lines, _, _ = V.compare(ma[0], mb[0], texts); it = items(lines)
        for li, (a, b) in enumerate(zip(ma[1], mb[1])):
            it["%d줄|날카로움" % (li + 1)] = round(abs(a - b), 4) if (a is not None and b is not None) else (0.0 if a == b else 1e9)
        return it
    def cmp(a_img, ma=None):
        return cmp2(ma if ma is not None else meas(a_img), mr)
    act = cmp(o, meas(o))
    fl = []
    for dx, dy in PHASES:
        fl.append(stats(cmp(jpeg_phase(r, src, dx, dy))))
    thr = {}
    for kd in KINDS:
        ms = [f[kd]["mean"] for f in fl if kd in f]; xs = [f[kd]["max"] for f in fl if kd in f]
        if not ms: continue
        # 평균은 평균+3σ. 가장 큰 값은 평균+3σ 와 「바닥에서 실제로 나온 가장 큰 값」 중 큰 쪽 — 값이 0.01 단위라 3σ 가 실제 나온 값보다 낮을 수 있음(4-dMi 글자 상자: 61번 중 0.13 한 번, 평균+3σ 0.1293, 실측)
        thr[kd] = dict(mean=float(np.mean(ms) + 3 * np.std(ms)), max=float(max(np.mean(xs) + 3 * np.std(xs), max(xs))))
    st = stats(act); ok, over = verdict(st, thr)
    # 규칙 시험: 바닥에 안 쓴 칸 자리 정답은 붙어야, 틀린 그림(0.05px 옮김·흐림 더함)은 떨어져야
    fake = jpeg_phase(r, src, *CHECK[0]); mf = meas(fake)
    rv = [verdict(stats(cmp(jpeg_phase(r, src, dx, dy))), thr) for dx, dy in CHECK]
    right = [v[0] for v in rv]
    def wrong(img):
        return verdict(stats(cmp2(mf, meas(img))), thr)
    wv = {"0.05px 옮김": wrong(subshift(r, 0.05)), "흐림 더함(σ0.5)": wrong(cv2.GaussianBlur(r, (0, 0), 0.5))}
    for k_, img_ in (extra_wrongs or {}).items(): wv[k_] = wrong(img_)
    wrongs = {k: v[0] for k, v in wv.items()}
    sound = all(right) and not any(wrongs.values())   # 틀린 그림: 0.05px 옮김 · 흐림 σ0.5 · 덧굵기 −0.10px(만들 수 있을 때)
    same = float((jpeg_phase(r, src, 0, 0) == o).all(2).mean())
    res = {"판정": ("일치(JPEG 바닥)" if ok else "일치 안 됨") if sound else "판정 못 함", "match": bool(ok and sound),
           "까닭": ("모든 종류가 문턱 이하, 그 밖 항목 완전히 같음" if ok else " · ".join(over)) if sound else
                  f"규칙 시험이 안 맞음(정답 붙음 {sum(right)}/{len(right)}, 틀린 그림 떨어짐 {sum(not v for v in wrongs.values())}/{len(wrongs)}) — 이 장은 바닥으로 가를 수 없음",
           "바닥 횟수": len(PHASES), "문턱": {k: {a: round(b, 4) for a, b in v.items()} for k, v in thr.items()},
           "원본 대 재현": {k: {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()} for k, v in st.items()},
           "넘은 곳": over, "규칙 시험": {"정답(바닥에 안 쓴 칸 자리) 붙음": f"{sum(right)}/{len(right)}", "틀린 그림 떨어짐": {k: (not v) for k, v in wrongs.items()},
                                "정답이 넘은 곳": [v[1] for v in rv], "틀린 그림이 넘은 곳": {k: v[1] for k, v in wv.items()}},
           "압축본과 원본 같은 화소 비율": round(same, 4), "원본 jpg": src_path}
    log(f"  바닥 판정: {res['판정']} — {res['까닭']}")
    return res
