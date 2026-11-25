# -*- coding: utf-8 -*-
"""tt_verify.py — 타이틀 재현 독립 검수기 (만든 쪽 코드와 따로 짠 두 번째 의견)

원본 썸네일과 우리 재현 그림을 **같은 코드·같은 값**으로 재고, 허용 범위 없이
(소수 둘째 자리까지 같아야 같음, 색은 #RRGGBB 문자열이 같아야 같음, 겹침 F1 은 1.0 이어야 같음)
비교한다.

쓰는 법
  python tt_verify.py <결과 폴더> [--only id,id]      → 값/<vid>_검수.json
  python tt_verify.py <결과 폴더> --cross <vid>        → 위 + 만든 쪽 주장과 내 측정이 다른 곳(producer_disagree)
  python tt_verify.py <결과 폴더> --self <vid>         → 원본 대 원본(자기 시험). 파일을 쓰지 않고 요약만 찍는다

만든 쪽 결과 JSON(값/<vid>.json)에서 가져오는 것은 줄 글자(lines[i].text)와
줄의 대략 범위(lines[i].ink, 없으면 grid 의 kind=="줄" 항목의 o 위/아래)뿐이다.
--cross 에서만 만든 쪽 주장값을 읽는다(비교 출력용).
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

METHOD = ("줄마다 원본 여백 줄(글자 위아래 빈 띠)의 색 무리(k-means 4)를 배경, 글자 띠 안에서 배경과 먼 색 무리를 글자색으로 "
          "원본에서 한 번 정하고, 두 그림에 같은 색 중심으로 덮임 정도 cov=d배경/(d글자+d배경)을 계산, cov>=0.5 를 글자 마스크로 씀. "
          "가장자리 소수점 = 마스크 바깥 이웃 칸의 cov. 글자 나누기 = 연결 성분 → x 겹침 묶기 → 글자 수에 맞춰 좁은 틈 합치기/넓은 묶음 쪼개기. "
          "획 = 거리변환 능선 중앙값×2-1, 기울기 = 밀기(shear) 0.01 단위 세로 투영 최대, 색 = 안쪽(2칸 깎음) 중앙값. "
          "판정은 허용 범위 없음(소수 2자리 같음·hex 같음·F1==1.0).")

BG_K = 4            # 배경 색 무리 수
TEXT_MIN_DIST = 60  # 배경 중심에서 이만큼(RGB 거리) 멀어야 글자 후보
MERGE_CENTER = 45   # 글자색 중심끼리 이보다 가까우면 하나로


def r2(v):
    return None if v is None else round(float(v) + 0.0, 2)


def hexc(rgb):
    r, g, b = [int(np.clip(round(float(c)), 0, 255)) for c in rgb]
    return "#%02X%02X%02X" % (r, g, b)


def load_json(p, tries=5):
    for i in range(tries):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            if i == tries - 1:
                raise
            time.sleep(3)


def load_img(p, tries=5):
    for i in range(tries):
        if os.path.exists(p):
            a = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
            if a is not None:
                return cv2.cvtColor(a, cv2.COLOR_BGR2RGB).astype(np.float32)
        if i < tries - 1:
            time.sleep(3)
    raise FileNotFoundError(p)


def free_mem_gb():
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1024 ** 3
    except Exception:
        return 99.0


# ---------------------------------------------------------------- 줄 범위(대략)
def line_regions_from_result(res, H):
    """만든 쪽 결과에서 글자와 줄의 대략 위/아래만 꺼낸다(크기·색 등 측정값은 쓰지 않음)."""
    texts, rough, xs = [], [], []
    grid = res.get("grid") or []
    for i, ln in enumerate(res["lines"]):
        texts.append(ln.get("text", ""))
        if ln.get("ink"):
            x0, y0, x1, y1 = ln["ink"]
            rough.append((float(y0), float(y1))); xs.append((float(x0), float(x1)))
            continue
        # 줄 잉크가 없으면 글자 자리 표(원본 쪽 글자 왼·오른)에서 가로 범위를 꺼낸다 — 같은 높이에 나뉜 줄(「바가지 관광지」·「TOP7」)을
        # 좌우로 가르려면 꼭 있어야 함. 없으면 「TOP7」 4글자를 두 줄 전체 폭에 나눠 0점이 남(2026-11-25 실측)
        gx = [g["o"] for g in grid if g.get("kind") == "글자" and g.get("line") == i and g.get("axis") == "x"]
        xs.append((min(gx), max(gx)) if gx else None)
        ys = [g["o"] for g in grid if g.get("kind") == "줄" and g.get("line") == i
              and ("위" in g.get("name", "") or "아래" in g.get("name", ""))]
        rough.append((min(ys), max(ys)))
    # 띠 = 대략 범위 + 위아래 여백(이웃 줄과 겹치지 않게 가운데서 자름)
    # 같은 높이에 나란히 놓인 줄(예: 「의리와」·「260」)은 위아래로 못 나누므로 좌우로 나눈다(가운데서 자름).
    regs = []
    ov = lambda a, b: min(a[1], b[1]) > max(a[0], b[0])
    for i, (t, b) in enumerate(rough):
        h = b - t
        pad = max(8.0, 0.3 * h)
        lo = t - pad
        hi = b + pad
        xa, xb = 0, None
        for j, (tj, bj) in enumerate(rough):
            if j == i:
                continue
            if ov((t, b), (tj, bj)) and xs[i] and xs[j]:
                if xs[j][1] <= xs[i][0]:
                    xa = max(xa, int(np.floor((xs[j][1] + xs[i][0]) / 2)))
                elif xs[j][0] >= xs[i][1]:
                    xb = min(xb if xb is not None else 10**9, int(np.ceil((xs[i][1] + xs[j][0]) / 2)))
                continue
            if bj <= t:
                lo = max(lo, (bj + t) / 2)
            elif tj >= b:
                hi = min(hi, (b + tj) / 2)
        if xs[i]:   # 줄의 가로 범위를 알면 그 바깥(여백 pad)은 이 줄 것이 아님 — 줄 밖 사진 조각을 범위로 뺌
            xa = max(xa, int(np.floor(xs[i][0] - pad)))
            xb = min(xb if xb is not None else 10**9, int(np.ceil(xs[i][1] + pad)))
        regs.append({"band": (int(max(0, np.floor(lo))), int(min(H, np.ceil(hi)))),
                     "core": (int(np.floor(t)), int(np.ceil(b))), "xr": (xa, xb), "has_ink": bool(xs[i])})
    return regs, texts


# ---------------------------------------------------------------- 색 기준(원본에서 한 번만)
def _kmeans(x, k):
    x = np.ascontiguousarray(x, np.float32)
    k = max(1, min(k, len(x)))
    cv2.setRNGSeed(12345)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _, lab, cen = cv2.kmeans(x, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return lab.ravel(), cen


def _mind(px, centers):
    d = np.sqrt(((px[..., None, :] - centers[None, None, :, :]) ** 2).sum(-1))
    return d.min(-1), d.argmin(-1)


def derive_params(orig, reg, text, _narrow=False):
    """원본 한 장에서 이 줄의 배경 색 중심·글자 색 중심을 정한다. 두 그림에 똑같이 쓴다."""
    p = _derive_params(orig, reg, text)
    if len(p.get("text", [])) == 0 and not _narrow and not p.get("empty"):
        # 글자 색이 하나도 안 남음 = 여백(배경 색을 잡는 곳)에 제목 아닌 다른 글자가 들어가 글자 색이 배경으로 잡힘.
        # 여백을 글자 높이 0.1(최소 4px)로 좁혀 한 번 더 잼(2026-11-25 「제이블랙」 편 첫 줄 위 흰 출처 글자 — 첫 줄 글자 0개로 잼, 실측)
        c0, c1 = reg["core"]; y0, y1 = reg["band"]; pd = max(4, int(0.1 * (c1 - c0)))
        reg2 = dict(reg, band=(max(y0, c0 - pd), min(y1, c1 + pd)))
        p2 = _derive_params(orig, reg2, text)
        if len(p2.get("text", [])):
            print(f"  [검수] 「{text}」 여백에 다른 글자가 섞여 글자 색이 안 잡힘 → 여백을 {pd}px로 좁혀 다시 잼", flush=True)
            reg["band"] = reg2["band"]
            return p2
    return p


def _derive_params(orig, reg, text):
    y0, y1 = reg["band"]
    c0, c1 = reg["core"]
    xa, xb = reg.get("xr", (0, None))
    band = orig[y0:y1, xa:xb]
    rows = np.arange(y0, y1)
    in_core = (rows >= c0) & (rows < c1)
    marg = band[~in_core].reshape(-1, 3)
    core = band[in_core].reshape(-1, 3)
    if len(marg) < 50:  # 여백이 거의 없으면 띠 끝 두 줄을 쓴다
        marg = np.concatenate([band[:2].reshape(-1, 3), band[-2:].reshape(-1, 3)])
    if len(marg) == 0 or len(core) == 0:  # 띠가 그림 밖·빈 띠 — 잴 수 없음(멈추지 않고 「못 잼」으로 남김)
        print(f"  [검수] 「{text}」 띠 비어 있음 band={reg['band']} core={reg['core']} — 이 줄 못 잼", flush=True)
        return {"bg": np.zeros((1, 3), np.float32), "text": np.zeros((0, 3), np.float32), "outline_idx": None, "bounds": None, "empty": True}
    _, bgc = _kmeans(marg[::3], BG_K)
    dmin, _ = _mind(core[None], bgc)
    cand = core[dmin[0] > TEXT_MIN_DIST]
    if len(cand) < 20:
        return {"bg": bgc, "text": np.zeros((0, 3), np.float32), "outline_idx": None, "bounds": None}
    _, tc = _kmeans(cand[::2], 4)
    # 가까운 중심 합치기
    tc = [c for c in tc]
    merged = True
    while merged and len(tc) > 1:
        merged = False
        for a in range(len(tc)):
            for b in range(a + 1, len(tc)):
                if np.linalg.norm(tc[a] - tc[b]) < MERGE_CENTER:
                    tc[a] = (tc[a] + tc[b]) / 2
                    tc.pop(b)
                    merged = True
                    break
            if merged:
                break
    tc = np.array(tc, np.float32)
    # 작은 무리·여백에도 흔한 무리(사진 색) 버리기
    _, lab = _mind(cand[None], tc)
    lab = lab[0]
    keep = []
    for j in range(len(tc)):
        n_core = (lab == j).sum()
        if n_core < 0.03 * len(cand):
            continue
        dm = np.sqrt(((marg - tc[j]) ** 2).sum(-1))
        dens_m = (dm < 25).sum() / max(1, len(marg))
        dens_c = n_core / max(1, len(core))
        if dens_m > 0.3 * dens_c:
            continue
        keep.append(j)
    tc = tc[keep] if keep else tc[:0]
    p = {"bg": bgc, "text": tc, "outline_idx": None}
    p["outline_idx"] = _find_outline(orig, reg, p)
    cov, _ = coverage(orig, reg, p)
    p["bounds"] = derive_cuts(ink_mask(_fill_only(cov, reg, p, orig), reg), reg, text)
    return p


def _pure_text(p):
    """글자색 무리 가운데 「다른 글자색과 배경색이 섞인 색」(가장자리 반쯤 칠한 화소가 모인 무리)을 뺀 순수 글자색과 배경색 목록."""
    T = [np.asarray(c, np.float32) for c in p["text"]]; B = [np.asarray(c, np.float32) for c in p["bg"]]
    keep = []
    for i, t in enumerate(T):
        blend = False
        for j, t2 in enumerate(T):
            if j == i: continue
            for b in B:
                d = t2 - b; a = float(((t - b) * d).sum() / max(float((d * d).sum()), 1.0))
                if 0.1 < a < 0.9 and float(np.linalg.norm(t - (b + a * d))) < 25: blend = True
        if not blend: keep.append(t)
    return (keep or T), B


def coverage(img, reg, p):
    y0, y1 = reg["band"]
    band = img[y0:y1]
    if len(p["text"]) == 0:
        z = np.zeros(band.shape[:2], np.float32)
        return z, z.astype(np.int32)
    dt, ti = _mind(band, p["text"])
    if p.get("bgimg") is not None:
        # 화소마다 「그 자리 배경색 → 글자색」 곧은 줄 위 어디쯤인지(선형 진하기 0~1). 배경색 = 글자를 지우고 메운 배경 그림의 같은 자리.
        # 줄 위아래 띠 색 몇 개로 배경을 정하면 단색이 아닌 배경에서 가장자리를 잘못 가름(운영자 2026-11-25 「배경이 단색이 아닌 경우 잘못할 수도」).
        # 원본·재현 모두 같은 배경 그림·같은 글자색으로 재므로 같은 기준. 글자색에서 가장자리 섞인 색 무리는 뺌(_pure_text).
        X = band.astype(np.float32); Bg = p["bgimg"][y0:y1].astype(np.float32); Tp, _ = _pure_text(p)
        best = np.full(X.shape[:2], 1e18, np.float32); cov = np.zeros(X.shape[:2], np.float32)
        # (시험 2026-11-25: 뒤 색 후보에 다른 글자색(검은 테두리 등)을 더해 봤으나 글자 나누기가 무너져 여러 줄이 0이 됨 → 뺌.
        #  테두리 있는 줄은 아래에서 예전 방식으로 잰다)
        for t in Tp:
            d = t[None, None, :] - Bg; dd = np.maximum((d * d).sum(2), 1.0)
            a = np.clip(((X - Bg) * d).sum(2) / dd, 0, 1)
            res = ((X - (Bg + a[..., None] * d)) ** 2).sum(2)
            m = res < best; best[m] = res[m]; cov[m] = a[m]
        # 글자색과 배경색이 거의 같은 화소(차이 30 미만)는 진하기를 잴 수 없음 → 예전 방식
        db, _ = _mind(band, p["bg"]); old = db / np.maximum(db + dt, 1e-6)
        weak = np.min(np.stack([np.sqrt(((t[None, None, :] - Bg) ** 2).sum(2)) for t in Tp]), 0) < 30
        cov[weak] = old[weak]
    else:
        db, _ = _mind(band, p["bg"])
        cov = db / np.maximum(db + dt, 1e-6)
    # (2026-11-25 시험: 섞인 색을 빼고 선형으로 재는 방식 _pure_text 를 넣어 봤으나 영상마다 들쭉날쭉 — 「전세계가 빚더미인데」 0.903→0.518 —
    #  검증이 안 되어 판정에는 쓰지 않음. 함수는 시험용으로 남김)
    xa, xb = reg.get("xr", (0, None))
    if xa or xb is not None:  # 나란히 놓인 이웃 줄 쪽 열은 이 줄 것이 아님
        keep = np.zeros(cov.shape[1], bool); keep[xa:xb] = True
        cov[:, ~keep] = 0
    return cov.astype(np.float32), ti.astype(np.int32)


def _fill_only(cov, reg, p, img):
    """글자 나누기용 마스크: 테두리 무리가 있으면 테두리를 뺀 채움만 쓴다(테두리가 어두운 배경과 이어져 글자가 한 덩어리로 붙는 것 막기)."""
    binm = cov >= 0.5
    if p.get("outline_idx") is None:
        return binm
    _, ti = coverage(img, reg, p)
    return binm & (ti != p["outline_idx"])


def _find_outline(orig, reg, p):
    """글자색 무리가 둘 이상이고 그중 하나가 테두리(바깥 경계를 거의 다 차지)면 그 번호."""
    if len(p["text"]) < 2:
        return None
    cov, ti = coverage(orig, reg, p)
    m = (cov >= 0.5).astype(np.uint8)
    edge = m & (1 - cv2.erode(m, np.ones((3, 3), np.uint8)))
    n_edge = edge.sum()
    if n_edge < 30:
        return None
    shares = [((ti == j) & (edge > 0)).sum() / n_edge for j in range(len(p["text"]))]
    for j in range(len(p["text"])):
        inner = ((ti != j) & (m > 0)).sum()
        # 바깥 경계를 거의 다(0.7) 차지하거나, 절반 넘게 차지하면서 다른 어느 무리보다 3배 넘게 많으면 테두리
        # (글자 밑 사진 색 무리가 경계 일부를 나눠 가져 0.7 에 못 미친 롱폼 사고, 2026-11-24)
        others = max([shares[k] for k in range(len(shares)) if k != j] or [0])
        if (shares[j] > 0.7 or (shares[j] > 0.5 and shares[j] > 3 * others)) and inner > 0.2 * m.sum():
            return int(j)
    return None


# ---------------------------------------------------------------- 글자 나누기
def ink_mask(binm, reg):
    """잡티 빼기: 작은 성분(높이²의 1% 미만), 띠 위/아래 끝에 닿은 성분(사진 조각), 중심이 글자 띠 밖인 성분."""
    hh = reg["core"][1] - reg["core"][0]
    c0, c1 = reg["core"]
    y0 = reg["band"][0]
    Hb, Wb = binm.shape
    n, lab, st, cen = cv2.connectedComponentsWithStats(binm.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < max(4, 0.01 * hh * hh):
            continue
        # 띠 끝에 닿은 성분 = 사진 조각. 다만 띠 위 끝이 그림 맨 위(y0=0)면 글자가 그림 끝에 붙은 것이라 버리지 않는다
        # (롱폼 「캐나다 이웃 부대찌개 반응」 테두리가 그림 맨 위에 닿아 글자 0개로 잰 사고, 2026-11-24)
        if (y == 0 and y0 > 0) or y + h >= Hb:
            continue
        if not (c0 - 2 <= cen[i][1] + y0 <= c1 + 2):
            continue
        keep[i] = True
    # 줄 양끝에서 넓은 틈(줄 높이의 0.3 넘게 — 낱말 사이 틈은 0.15 안팎)으로 떨어진 작은 묶음(전체 잉크의 25% 미만)은 줄 밖 사진 조각으로 뺀다
    # (롱폼 왼쪽 끝 흰 옷 조각이 「캐나다」로 세어져 글자 나누기가 밀린 사고, 2026-11-24)
    ids = [i for i in range(1, n) if keep[i]]
    # 줄의 가로 범위를 알면(has_ink) 이 규칙을 쓰지 않음 — 낱말 사이가 넓은 글자(조니 뎁 「억」)를 조각으로 잘못 빼던 것(2026-11-25)
    if len(ids) > 1 and not reg.get("has_ink"):
        spans = sorted((st[i][0], st[i][0] + st[i][2], st[i][4], i) for i in ids)
        groups, cur = [], [spans[0]]
        for sp in spans[1:]:
            if sp[0] - max(c[1] for c in cur) > 0.3 * hh: groups.append(cur); cur = [sp]
            else: cur.append(sp)
        groups.append(cur)
        tot = sum(sp[2] for sp in spans)
        while len(groups) > 1 and sum(sp[2] for sp in groups[0]) < 0.25 * tot:
            for sp in groups.pop(0): keep[sp[3]] = False
        while len(groups) > 1 and sum(sp[2] for sp in groups[-1]) < 0.25 * tot:
            for sp in groups.pop(): keep[sp[3]] = False
    return keep[lab]


def _char_w(ch):
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F:
        return 1.0
    if ch in "!|.,:;'`":
        return 0.3
    if ch in "?-~":
        return 0.5
    if ch.isdigit() or ch.isupper():
        return 0.65
    if ch.isalpha():
        return 0.55
    return 0.8


def _dp_cuts(proj, a, b, ws, hh, lam=3.0):
    """[a,b) 안을 글자 n개로 자를 자리(n-1개). 비용 = 잘린 열의 잉크/높이 + lam*((폭-기대폭)/기대폭)^2."""
    n = len(ws)
    if n <= 1:
        return []
    ws = np.array(ws, float)
    e = ws / ws.sum() * (b - a)
    xs = np.arange(a + 1, b)
    if len(xs) < n:   # 자를 폭이 글자 수보다 좁음(글자 범위를 못 잡은 줄) — 고르게 나눔(2026-11-25 「바가지 관광지 TOP7」 색 겹침 오류)
        return [int(round(a + (b - a) * k / n)) for k in range(1, n)]
    c = proj[xs] / hh
    D = c + lam * (((xs - a) - e[0]) / e[0]) ** 2
    back = []
    for k in range(1, n - 1):
        W = xs[None, :] - xs[:, None]  # [y, x] 폭
        M = D[:, None] + lam * ((W - e[k]) / e[k]) ** 2
        M[W <= 0] = np.inf
        arg = M.argmin(0)
        D = c + M[arg, np.arange(len(xs))]
        back.append(arg)
    fin = D + lam * (((b - xs) - e[-1]) / e[-1]) ** 2
    j = int(fin.argmin())
    cuts = [j]
    for arg in reversed(back):
        j = int(arg[j])
        cuts.append(j)
    return [int(xs[j]) for j in reversed(cuts)]


def derive_cuts(ink, reg, text):
    """원본 잉크로 글자 경계 x 를 정한다(두 그림에 같은 경계를 쓴다).
    돌려줌: bounds = [x_0, x_1, ..., x_n] — 글자 k = 열 [x_k, x_{k+1}). 글자 수를 모르면 None."""
    hh = reg["core"][1] - reg["core"][0]
    words = [w for w in (text or "").split(" ") if w]
    if not words or not ink.any():
        return None
    proj = ink.sum(0).astype(float)
    cols = np.where(proj > 0)[0]
    # 잉크 덩어리(빈칸 0.35h 이상으로 떨어진 것)
    blocks, s0, prev = [], cols[0], cols[0]
    for x in cols[1:]:
        if x - prev - 1 >= 0.35 * hh:
            blocks.append([s0, prev + 1])
            s0 = x
        prev = x
    blocks.append([s0, prev + 1])
    exp_w = sum(_char_w(ch) for ch in "".join(words)) * hh
    # 글에 맞는 연속 덩어리 고르기(폭이 기대폭에 가장 가까운 것, 비슷하면 왼쪽)
    best, sel = None, None
    for i in range(len(blocks)):
        for j in range(i, len(blocks)):
            w = blocks[j][1] - blocks[i][0]
            sc = abs(np.log(max(w, 1) / exp_w))
            if best is None or sc < best - 0.05:
                best, sel = sc, (i, j)
    i, j = sel
    a, b = blocks[i][0], blocks[j][1]
    # 낱말 나누기: 고른 범위 안 빈 열 묶음 중 가장 넓은 (낱말수-1)개
    runs, x = [], a
    while x < b:
        if proj[x] == 0:
            y = x
            while y < b and proj[y] == 0:
                y += 1
            runs.append((y - x, x, y))
            x = y
        else:
            x += 1
    sep = sorted(sorted(runs, reverse=True)[:len(words) - 1], key=lambda r: r[1])
    if len(sep) != len(words) - 1:
        return None
    spans, st = [], a
    for _, x0, x1 in sep:
        spans.append((st, x0))
        st = x1
    spans.append((st, b))
    bounds = []
    for (wa, wb), w in zip(spans, words):
        inner = _dp_cuts(proj, wa, wb, [_char_w(ch) for ch in w], hh)
        if bounds:
            bounds[-1] = (bounds[-1] + wa) // 2  # 낱말 사이는 빈칸 가운데에서 자름
        else:
            bounds.append(wa)
        bounds += inner
        bounds.append(wb)
    # 바깥 경계: 이웃 덩어리와의 가운데까지(없으면 높이 0.5 만큼)
    left = (blocks[i - 1][1] + a) // 2 if i > 0 else max(0, a - int(0.5 * hh))
    right = (b + blocks[j + 1][0]) // 2 if j + 1 < len(blocks) else min(ink.shape[1], b + int(0.5 * hh))
    bounds[0], bounds[-1] = left, right
    return [int(v) for v in bounds]


def segment(ink, bounds):
    gm = []
    for k in range(len(bounds) - 1):
        m = ink.copy()
        m[:, :bounds[k]] = False
        m[:, bounds[k + 1]:] = False
        gm.append(m)
    return gm


# ---------------------------------------------------------------- 한 장 재기
def _edges(gmask, part, axis):
    """gmask(bool) 의 앞/뒤 경계를 소수점으로: 바깥 이웃 칸의 부분 덮임(part)만큼 늘린다."""
    prof = gmask.any(axis=1 - axis) if axis == 1 else gmask.any(axis=1)
    idx = np.where(prof)[0]
    a, b = int(idx.min()), int(idx.max())
    pp = part.max(axis=1 - axis) if axis == 1 else part.max(axis=1)
    lo = a - (float(pp[a - 1]) if a - 1 >= 0 else 0.0)
    hi = b + 1 + (float(pp[b + 1]) if b + 1 < len(pp) else 0.0)
    return lo, hi


def _stroke(m):
    if m.sum() < 10:
        return None
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    ridge = (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8))) & (dt >= 1)
    if not ridge.any():
        return None
    return 2 * float(np.median(dt[ridge])) - 1


def _slant(m):
    ys, xs = np.nonzero(m)
    if len(xs) < 20:
        return None
    yc = (ys.min() + ys.max()) / 2
    W = m.shape[1]
    best, bs = -1, 0.0
    for k in range(-40, 41):
        s = k / 100
        x2 = np.round(xs - s * (ys - yc)).astype(np.int64)
        x2 = x2 - x2.min()
        h = np.bincount(x2, minlength=1).astype(np.float64)
        sc = float((h * h).sum())
        if sc > best + 1e-9 or (abs(sc - best) <= 1e-9 and abs(s) < abs(bs)):
            best, bs = sc, s
    return -bs + 0.0  # +면 위쪽이 오른쪽으로 기움


def _med_color(img_band, m):
    if m.sum() == 0:
        return None
    return hexc(np.median(img_band[m], axis=0))


def measure_image(img, line_regions, texts, params_list):
    """한 장을 잰다. params_list 는 원본에서 정한 색 기준(두 그림에 같은 것)."""
    out = []
    for reg, text, p in zip(line_regions, texts, params_list):
        y0, y1 = reg["band"]
        band = img[y0:y1]
        cov, ti = coverage(img, reg, p)
        binm = (cov >= 0.5)
        ink = ink_mask(_fill_only(cov, reg, p, img), reg)
        n_expect = len(text.replace(" ", "")) if text else 0
        gm = segment(ink, p["bounds"]) if p.get("bounds") else []
        allg = np.zeros_like(binm)
        for m in gm:
            allg |= m
        part = np.where(binm, 0.0, cov) * (cv2.dilate(allg.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        L = {"n_glyph": len(gm), "glyphs": [], "masks": gm, "band": (y0, y1)}
        if not gm:
            out.append(L)
            continue
        for m in gm:
            if not m.any():
                L["glyphs"].append({"box": None})
                continue
            pm = part * (cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            l, r = _edges(m, pm, 1)
            t, b = _edges(m, pm, 0)
            L["glyphs"].append({"box": [l, t + y0, r, b + y0]})
        if not allg.any():  # 글자 조각이 모두 비었음 — 이 줄 못 잼(멈추지 않음)
            out.append(L)
            continue
        top, bot = _edges(allg, part, 0)
        L["top"], L["bottom"] = top + y0, bot + y0
        bx = [g["box"] for g in L["glyphs"] if g["box"]]
        L["baseline"] = float(np.median([q[3] for q in bx]))
        L["glyph_h"] = float(np.median([q[3] - q[1] for q in bx]))
        L["glyph_w"] = float(np.mean([q[2] - q[0] for q in bx]))
        # 틈(낱말 사이 빈칸은 글자 수가 맞을 때만 구분)
        gaps = [(L["glyphs"][i + 1]["box"][0] - L["glyphs"][i]["box"][2])
                if (L["glyphs"][i + 1]["box"] and L["glyphs"][i]["box"]) else None for i in range(len(gm) - 1)]
        word = [False] * len(gaps)
        if n_expect == len(gm) and text:
            k = 0
            chars = list(text)
            for ci, ch in enumerate(chars):
                if ch == " ":
                    continue
                if k < len(gaps) and ci + 1 < len(chars) and chars[ci + 1] == " ":
                    word[k] = True
                k += 1
        L["gaps"], L["gap_is_word"] = gaps, word
        inner = [g for g, w in zip(gaps, word) if not w and g is not None]
        L["spacing_mean"] = float(np.mean(inner)) if inner else None
        # 채움/테두리 나누기
        oi = p["outline_idx"]
        fill = allg & (ti != oi) if oi is not None else allg.copy()
        outl = allg & (ti == oi) if oi is not None else np.zeros_like(allg)
        L["stroke"] = _stroke(fill)
        L["slant"] = _slant(allg)
        er = cv2.erode(fill.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0
        # 색 덩어리: 글자마다 가장 많은 글자색 번호 → 이어진 같은 번호 = 한 덩어리
        cid = []
        for m in gm:
            v = ti[m & fill]
            cid.append(int(np.bincount(v).argmax()) if len(v) else -1)
        runs = []
        for gi, c in enumerate(cid):
            if runs and runs[-1]["cid"] == c:
                runs[-1]["g"].append(gi)
            else:
                runs.append({"cid": c, "g": [gi]})
        for R in runs:
            rm = np.zeros_like(binm)
            for gi in R["g"]:
                rm |= gm[gi]
            rm &= er
            R["fill"] = _med_color(band, rm)
            ys = np.nonzero(rm.any(1))[0]
            if len(ys):
                h = ys.max() - ys.min() + 1
                tb = rm.copy()
                tb[ys.min() + max(1, int(0.2 * h)):] = False
                bb = rm.copy()
                bb[:ys.max() + 1 - max(1, int(0.2 * h))] = False
                R["grad_top"], R["grad_bot"] = _med_color(band, tb), _med_color(band, bb)
            else:
                R["grad_top"] = R["grad_bot"] = None
        L["runs"] = runs
        if outl.any():
            dtu = cv2.distanceTransform(allg.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            fe = fill & ~(cv2.erode(fill.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            L["outline_px"] = float(np.median(dtu[fe])) if fe.any() else None
            oer = cv2.erode(outl.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            L["outline_color"] = _med_color(band, oer if oer.any() else outl)
        else:
            L["outline_px"], L["outline_color"] = None, None
        out.append(L)
    for i, L in enumerate(out):
        if i + 1 < len(out) and "top" in L and "top" in out[i + 1]:
            L["line_gap_next"] = out[i + 1]["top"] - L["bottom"]
        else:
            L["line_gap_next"] = None
    return out


# ---------------------------------------------------------------- 비교(허용 범위 없음)
def _item(o, r):
    if isinstance(o, str) or isinstance(r, str) or o is None or r is None:
        ok = (o == r)
        d = None if ok else ("다름" if (o is not None and r is not None) else "한쪽 없음")
        if isinstance(o, str) and isinstance(r, str) and o.startswith("#") and r.startswith("#") and not ok:
            a = [int(o[k:k + 2], 16) for k in (1, 3, 5)]
            b = [int(r[k:k + 2], 16) for k in (1, 3, 5)]
            d = "RGB차 " + ",".join("%+d" % (y - x) for x, y in zip(a, b))
        return {"o": o, "r": r, "d": d, "ok": bool(ok)}
    o2, rr = r2(o), r2(r)
    return {"o": o2, "r": rr, "d": r2(rr - o2), "ok": bool(o2 == rr)}


def _f1(a, b):
    s = a.sum() + b.sum()
    return 1.0 if s == 0 else float(2 * (a & b).sum() / s)


def _match(go, gr):
    if len(go) == len(gr) or any(g["box"] is None for g in go + gr):
        return list(range(len(go)))
    res, used = [], set()
    for g in go:
        best, bj = 0.0, None
        for j, h in enumerate(gr):
            if j in used:
                continue
            ix = min(g["box"][2], h["box"][2]) - max(g["box"][0], h["box"][0])
            if ix > best:
                best, bj = ix, j
        if bj is not None:
            used.add(bj)
        res.append(bj)
    return res


def compare(mo, mr, texts):
    lines, n_items, n_diff = [], 0, 0
    for li, (A, B, text) in enumerate(zip(mo, mr, texts)):
        items = {}
        items["글자 수"] = _item(A["n_glyph"], B["n_glyph"])
        for k, name in [("top", "줄 위"), ("bottom", "줄 아래"), ("baseline", "기준선(글자 아래 중앙값)"),
                        ("glyph_h", "글자 높이(중앙값)"), ("glyph_w", "글자 너비(평균)"),
                        ("spacing_mean", "자간 평균(낱말 사이 뺌)"), ("line_gap_next", "행간(다음 줄 위 - 이 줄 아래)"),
                        ("stroke", "획 굵기"), ("slant", "기울기(가로밀림/높이)"),
                        ("outline_color", "테두리 색"), ("outline_px", "테두리 굵기")]:
            items[name] = _item(A.get(k), B.get(k))
        ga, gb = A.get("gaps", []), B.get("gaps", [])
        for i in range(max(len(ga), len(gb))):
            items["자간 %d" % (i + 1)] = _item(ga[i] if i < len(ga) else None, gb[i] if i < len(gb) else None)
        ra, rb = A.get("runs", []), B.get("runs", [])
        items["색 덩어리 나뉨"] = _item(str([R["g"] for R in ra]), str([R["g"] for R in rb]))
        for i in range(max(len(ra), len(rb))):
            Ra = ra[i] if i < len(ra) else {}
            Rb = rb[i] if i < len(rb) else {}
            items["채움색 %d" % (i + 1)] = _item(Ra.get("fill"), Rb.get("fill"))
            items["위쪽 색 %d" % (i + 1)] = _item(Ra.get("grad_top"), Rb.get("grad_top"))
            items["아래쪽 색 %d" % (i + 1)] = _item(Ra.get("grad_bot"), Rb.get("grad_bot"))
        chars = list(text.replace(" ", "")) if text else []
        glyphs = []
        mt = _match(A["glyphs"], B["glyphs"])
        for gi, (g, j) in enumerate(zip(A["glyphs"], mt)):
            ch = chars[gi] if len(chars) == A["n_glyph"] else "?"
            ob = [r2(v) for v in g["box"]] if g["box"] else None
            h = B["glyphs"][j] if j is not None else {"box": None}
            rb_ = [r2(v) for v in h["box"]] if h["box"] else None
            f1 = _f1(A["masks"][gi], B["masks"][j]) if j is not None else 0.0
            ok = ob is not None and ob == rb_ and f1 == 1.0
            db = [r2(y - x) for x, y in zip(ob, rb_)] if (ob and rb_) else None
            glyphs.append({"ch": ch, "o_box": ob, "r_box": rb_, "d_box": db, "f1": round(f1, 4), "ok": ok})
        extra = len(B["glyphs"]) - sum(1 for j in mt if j is not None)
        if extra:
            items["재현에만 있는 글자 묶음"] = _item(0, extra)
        n_items += len(items) + len(glyphs)
        n_diff += sum(1 for v in items.values() if not v["ok"]) + sum(1 for g in glyphs if not g["ok"])
        lines.append({"text": text, "items": items, "glyphs": glyphs})
    return lines, n_items, n_diff


def find_source_jpeg(folder, vid, o):
    """원본.png와 화소가 똑같은 유튜브 원본 jpg를 찾는다(위 폴더들의 thumbs*/ 아래). 없으면 None."""
    from glob import glob
    d = os.path.abspath(folder)
    for _ in range(4):
        for p in glob(os.path.join(d, "thumbs*", "*", vid + ".jpg")):
            a = load_img(p, tries=1)
            if a.shape == o.shape and np.array_equal(a, o):
                return p
        d = os.path.dirname(d)
    return None


def jpeg_like(r, src):
    """재현 그림을 원본 jpg와 같은 압축 표·색 줄임 방식으로 한 번 압축했다 푼다(원본이 겪은 압축을 똑같이 겪게)."""
    import io
    from PIL import Image, JpegImagePlugin
    s = Image.open(src)
    b = io.BytesIO()
    Image.fromarray(np.clip(r, 0, 255).astype(np.uint8)).save(
        b, "JPEG", qtables=s.quantization, subsampling=JpegImagePlugin.get_sampling(s))
    return np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGB")).astype(np.float32)


def run_one(folder, vid, self_test=False):
    if free_mem_gb() < 1.5:
        raise SystemExit("남은 메모리 %.2fGB < 1.5GB — 멈춤" % free_mem_gb())
    res = load_json(os.path.join(folder, "값", vid + ".json"))
    o = load_img(os.path.join(folder, "그림", vid + "_원본.png"))
    regs, texts = line_regions_from_result(res, o.shape[0])
    params = [derive_params(o, r, t) for r, t in zip(regs, texts)]
    bgp = os.path.join(folder, "그림", vid + "_배경.png")
    if os.path.exists(bgp) and not os.environ.get("TT_OLDCOV"):
        bgi = load_img(bgp)
        if bgi.shape == o.shape:
            # 줄마다 원본만 보고 정한다: 글자 바로 바깥(2~4px) 원본 색이 메운 배경과 같으면(차 평균 12 미만) 글자 뒤 = 배경 → 자리별 배경 기준.
            # 다르면(테두리·그림자가 둘러 있음, 「(...)」 등) 글자 뒤가 배경이 아니므로 예전 기준. 재현 쪽 숫자는 보지 않는다.
            for rg, p_ in zip(regs, params):
                y0_, y1_ = rg["band"]; c0, _ = coverage(o, rg, p_); a_ = (c0 >= 0.5).astype(np.uint8)
                ring = (cv2.dilate(a_, np.ones((9, 9), np.uint8)) > 0) & ~(cv2.dilate(a_, np.ones((5, 5), np.uint8)) > 0)
                dif = float(np.abs(o[y0_:y1_].astype(np.float32) - bgi[y0_:y1_].astype(np.float32)).sum(2)[ring].mean()) if ring.any() else 999.0
                p_["bg_ring_diff"] = round(dif, 1)
                if dif < 12: p_["bgimg"] = bgi
    mo = measure_image(o, regs, texts, params)
    if self_test:
        r = o.copy()
    else:
        r = load_img(os.path.join(folder, "그림", vid + "_재현.png"))
        if r.shape != o.shape:
            raise SystemExit("크기 다름 %s %s" % (o.shape, r.shape))
        # 재현은 압축하지 않고 그대로 견준다(운영자 2026-11-24 「압축 안 하면 되잖아」, 2026-11-25 「압축을 왜 하지 안 하기로 했는데」).
        # 11-25에 넣었던 「원본 jpg 표로 재현을 다시 압축」 단계는 뺌. 시험으로만 켤 때: TT_JPEG=1
        src = find_source_jpeg(folder, vid, o) if os.environ.get("TT_JPEG") else None
        if src:
            r = jpeg_like(r, src)
    mr = measure_image(r, regs, texts, params)
    lines, n_items, n_diff = compare(mo, mr, texts)
    out = {"video_id": vid, "method": METHOD,
           "params": [{"bg": [hexc(c) for c in p["bg"]], "text": [hexc(c) for c in p["text"]],
                       "outline_idx": p["outline_idx"], "bg_ring_diff": p.get("bg_ring_diff"), "per_pixel_bg": p.get("bgimg") is not None, "band": list(rg["band"]), "glyph_bounds_x": p.get("bounds")} for p, rg in zip(params, regs)],
           "jpeg": (None if self_test else (os.path.basename(src) if src else None)),
           "lines": lines, "all_ok": n_diff == 0, "n_items": n_items, "n_diff": n_diff}
    return out, mo, mr


# ---------------------------------------------------------------- 만든 쪽 주장과 맞대기
def cross(folder, vid, out):
    res = load_json(os.path.join(folder, "값", vid + ".json"))
    sp = os.path.join(folder, "값", vid + "_실측.json")
    sil = load_json(sp) if os.path.exists(sp) else None
    dis = []

    def add(line, what, side, claim, mine):
        if claim is None or mine is None:
            return
        if isinstance(claim, str) or isinstance(mine, str):
            same = str(claim).upper() == str(mine).upper()
            d = None
        else:
            same = r2(claim) == r2(mine)
            d = r2(r2(mine) - r2(claim))
        if not same:
            dis.append({"line": line + 1, "what": what, "side": side, "producer": claim, "mine": mine, "mine_minus_producer": d})

    L = out["lines"]
    for g in res.get("grid") or []:
        li = g.get("line")
        if li is None or li >= len(L):
            continue
        it = L[li]["items"]
        if g.get("kind") == "줄":
            key = "줄 위" if g["name"].endswith("위") else "줄 아래" if g["name"].endswith("아래") else "기준선(글자 아래 중앙값)"
            add(li, g["name"], "o", g.get("o"), it[key]["o"])
            add(li, g["name"], "r", g.get("r"), it[key]["r"])
        elif g.get("kind") == "글자":
            gi = g.get("g")
            gl = L[li]["glyphs"]
            if gi is None or gi >= len(gl):
                continue
            nm = g["name"]
            k = 0 if nm.endswith("왼") else 2 if nm.endswith("오른") else 1 if nm.endswith("위") else 3
            if gl[gi].get("o_box"): add(li, nm, "o", g.get("o"), gl[gi]["o_box"][k])   # 원본 글자 상자가 없으면(못 나눔) 건너뜀
            if gl[gi]["r_box"]:
                add(li, nm, "r", g.get("r"), gl[gi]["r_box"][k])
    for c in res.get("colors") or []:
        li = c.get("line")
        if li is None or li >= len(L):
            continue
        fills = [(k, v) for k, v in L[li]["items"].items() if k.startswith("채움색")]
        # 만든 쪽 색 덩어리 글자와 내 덩어리 순서를 맞춤: 줄 안 순서대로
        idx = [x for x in res["colors"] if x.get("line") == li].index(c)
        if idx < len(fills):
            add(li, c["what"], "o", c.get("o"), fills[idx][1]["o"])
            add(li, c["what"], "r", c.get("r"), fills[idx][1]["r"])
        if c.get("dE") == 0.0 and idx < len(fills) and not fills[idx][1]["ok"]:
            dis.append({"line": li + 1, "what": c["what"] + " — 만든 쪽은 ΔE 0(같음)이라 했으나 내 측정은 다름",
                        "side": "o/r", "producer": [c.get("o"), c.get("r")],
                        "mine": [fills[idx][1]["o"], fills[idx][1]["r"]], "mine_minus_producer": None})
    if sil:
        mp = {"글자 높이": "글자 높이(중앙값)", "글자 너비(평균)": "글자 너비(평균)",
              "자간(글자 사이 빈칸 평균)": "자간 평균(낱말 사이 뺌)", "행간(다음 줄과 빈칸)": "행간(다음 줄 위 - 이 줄 아래)",
              "획 굵기": "획 굵기", "기울기": "기울기(가로밀림/높이)"}
        for li, sl in enumerate(sil.get("lines", [])):
            if li >= len(L):
                break
            for pk, mk in mp.items():
                if pk in sl and mk in L[li]["items"]:
                    add(li, "실측 " + pk, "o", sl[pk].get("o"), L[li]["items"][mk]["o"])
                    add(li, "실측 " + pk, "r", sl[pk].get("r"), L[li]["items"][mk]["r"])
                    if sl[pk].get("ok") is True and not L[li]["items"][mk]["ok"]:
                        dis.append({"line": li + 1, "what": "실측 " + pk + " — 만든 쪽은 같음(ok)이라 했으나 내 측정은 다름",
                                    "side": "ok", "producer": True, "mine": L[li]["items"][mk], "mine_minus_producer": None})
    if res.get("passed") is True and not out["all_ok"]:
        dis.append({"line": None, "what": "만든 쪽 passed=True 이나 내 검수는 다른 항목 %d개" % out["n_diff"],
                    "side": "전체", "producer": True, "mine": False, "mine_minus_producer": None})
    return dis


def summary(out, top=12):
    print("%s  항목 %d  다름 %d  all_ok=%s" % (out["video_id"], out["n_items"], out["n_diff"], out["all_ok"]))
    for i, L in enumerate(out["lines"]):
        bad = [(k, v) for k, v in L["items"].items() if not v["ok"]]
        gb = [g for g in L["glyphs"] if not g["ok"]]
        f1s = [g["f1"] for g in L["glyphs"]]
        print(" %d줄 「%s」 항목다름 %d/%d  글자다름 %d/%d  F1최소 %s" % (
            i + 1, L["text"], len(bad), len(L["items"]), len(gb), len(L["glyphs"]), min(f1s) if f1s else None))
        for k, v in bad[:top]:
            print("    %s: o=%s r=%s d=%s" % (k, v["o"], v["r"], v["d"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--only")
    ap.add_argument("--cross")
    ap.add_argument("--self")
    a = ap.parse_args()
    vd = os.path.join(a.folder, "값")
    if a.self:
        out, _, _ = run_one(a.folder, a.self, self_test=True)
        summary(out)
        return
    if a.cross:
        vids = [a.cross]
    elif a.only:
        vids = a.only.split(",")
    else:
        vids = sorted(f[:-5] for f in os.listdir(vd) if f.endswith(".json")
                      and f not in ("눈확인.json", "글자고르기.json") and not f.endswith(("_실측.json", "_검수.json")))
    for vid in vids:
        out, _, _ = run_one(a.folder, vid)
        if a.cross:
            out["producer_disagree"] = cross(a.folder, vid, out)
        p = os.path.join(vd, vid + "_검수.json")
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)
        summary(out)
        if a.cross:
            print(" producer_disagree %d건" % len(out["producer_disagree"]))


if __name__ == "__main__":
    main()
