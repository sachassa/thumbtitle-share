# tt_refine — 재현 도구(tt_typo3)가 끝난 뒤, 효과가 확인된 두 방법으로 제목을 다시 그린다(운영자 2026-11-25 「아는 방법 먼저 넣고 돌림」).
#   ① 진하기로 굵기 맞추기: 흑백(있다/없다)이 아니라 원본 화소의 진하기(배경→글자색 사이 0~1)를 재서, 8배로 그려 줄인 글자의 진하기와
#      같아지도록 굵기(덧굵기/깎기)·크기·가로·세로·글자 자리(1/8px)를 맞춘다. (조니 뎁·부대찌개 롱폼에서 0.99대, 실측 2026-11-25)
#   ② 테두리 8방향: 테두리·그림자를 굵기 숫자 하나로 그리지 않고, 글자 바깥 거리(0.5px 간격)·8방향마다 원본 진하기를 재서 그대로 그린다.
#   그리기는 파이썬(PIL, 8배) — 비교와 그리기가 같은 그리개. 결과: 그림/<id>_재현.png (Chrome 판은 <id>_재현_크롬.png 로 남김),
#   값/<id>_정밀.json. 검수(tt_verify)가 Chrome 판보다 나쁘면 되돌린다(--keep-better).
#   python tt_refine.py <결과 폴더> <영상 id> [--keep-better]
import json, os, shutil, subprocess, sys, time
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_fontid as FID

SS = 8
hexrgb = lambda h: np.array([int(h[j:j + 2], 16) for j in (1, 3, 5)], np.float32)
DIRS = ["오른쪽", "오른아래", "아래", "왼아래", "왼쪽", "왼위", "위", "오른위"]


class Line:
    def __init__(self, ln, font, O, B, X, Y):
        self.ln = ln; self.O = O; self.B = B; self.X = X; self.Y = Y; self.H, self.W = O.shape[:2]
        self.path, self.wght = font[1], font[2]
        text = ln["text"]; idx = [i for i, ch in enumerate(text) if ch.strip()]
        G = ln["glyphs"]; assert len(G) == len(idx), f"글자 수 다름 {len(G)} != {len(idx)}"
        cols = ["#FFFFFF"] * len(text)
        for s in ln.get("spans") or []:
            for i in range(s["i0"], min(len(text) - 1, s["i1"]) + 1): cols[i] = s["color"]
        self.chars = [g["ch"] for g in G]; self.cols = [cols[i] for i in idx]
        self.P = dict(sz=float(ln["size_px"]), e=float(ln.get("bold_px") or 0.0), sh=float(ln.get("slant") or 0.0), kx=1.0, ky=1.0,
                      sx=[float(g["sx"]) for g in G], sy=[float(g["sy"]) for g in G], pens=[(g["x"] - X, g["y"] - Y) for g in G])
        self._f = {}; self._g = {}

    def font(self, sz):
        k = round(sz * SS, 2)
        if k not in self._f:
            ft = ImageFont.truetype(self.path, k)
            if self.wght:
                try: ft.set_variation_by_axes([self.wght])
                except Exception: pass
            self._f[k] = ft
        return self._f[k]

    def glyph(self, ch, sz, hs, vs, e, sh):
        k = (ch, round(sz, 3), round(hs, 4), round(vs, 4), round(e, 3), round(sh, 4))
        if k in self._g: return self._g[k]
        if len(self._g) > 3000: self._g.clear()
        ft = self.font(sz); l, t, rr, b = ft.getbbox(ch, anchor="ls"); pad = int(np.ceil(abs(e) * SS)) + 3
        im = Image.new("L", (rr - l + 2 * pad, b - t + 2 * pad), 0); ImageDraw.Draw(im).text((pad - l, pad - t), ch, font=ft, fill=255, anchor="ls")
        g = np.asarray(im, np.float32)
        if abs(hs - 1) > 1e-4 or abs(vs - 1) > 1e-4: g = cv2.resize(g, (max(1, int(round(g.shape[1] * hs))), max(1, int(round(g.shape[0] * vs)))), interpolation=cv2.INTER_LINEAR)
        ox, oy = (l - pad) * hs, (t - pad) * vs
        if abs(sh) > 1e-3:   # 기울임: 기준선에서 위로 갈수록 오른쪽으로(tt_typo2.layout 과 같음)
            h, w = g.shape; o0, o1 = -sh * oy, -sh * (oy + h - 1); lo, hi = min(o0, o1), max(o0, o1)
            g = cv2.warpAffine(g, np.float32([[1, -sh, -sh * oy - lo], [0, 1, 0]]), (w + int(np.ceil(hi - lo)) + 2, h), flags=cv2.INTER_LINEAR); ox += lo
        if abs(e) > 1e-3:
            m = (g > 127).astype(np.uint8)
            if e > 0: d = cv2.distanceTransform(1 - m, cv2.DIST_L2, 5); g = np.where(d <= e * SS, 255, 0).astype(np.float32)
            else: d = cv2.distanceTransform(m, cv2.DIST_L2, 5); g = np.where(d > -e * SS, 255, 0).astype(np.float32)
        self._g[k] = (g, ox, oy); return self._g[k]

    def covs(self, P):
        out = []
        for i, ch in enumerate(self.chars):
            g, ox, oy = self.glyph(ch, P["sz"], P["sx"][i] * P["kx"], P["sy"][i] * P["ky"], P["e"], P["sh"])
            x = int(round(P["pens"][i][0] * SS + ox)); y = int(round(P["pens"][i][1] * SS + oy)); h, w = g.shape
            bx, by = x // SS, y // SS; px_, py_ = x - bx * SS, y - by * SS
            hh = -(-(py_ + h) // SS) * SS; ww = -(-(px_ + w) // SS) * SS
            loc = np.zeros((hh, ww), np.float32); loc[py_:py_ + h, px_:px_ + w] = g
            blk = loc.reshape(hh // SS, SS, ww // SS, SS).mean((1, 3)) / 255.0
            cov = np.zeros((self.H, self.W), np.float32)
            a0, b0, a1, b1 = max(0, by), max(0, bx), min(self.H, by + blk.shape[0]), min(self.W, bx + blk.shape[1])
            if a1 > a0 and b1 > b0: cov[a0:a1, b0:b1] = blk[a0 - by:a1 - by, b0 - bx:b1 - bx]
            out.append(cov)
        return out

    def measure(self, back):
        """원본 진하기: 화소마다 그 자리 글자의 색 쪽으로 (원본-뒤)를 (글자색-뒤) 위에 투영. back = 글자 바로 뒤 색(테두리 있으면 테두리 색)."""
        C0 = self.covs(self.P)
        D = np.stack([cv2.distanceTransform((c < 0.5).astype(np.uint8), cv2.DIST_L2, 5) for c in C0])
        self.own = D.argmin(0); self.near = D.min(0) < 6
        Bk = self.B if back is None else np.zeros_like(self.B) + back
        CL = np.stack([hexrgb(c) for c in self.cols])[self.own]
        dv = CL - Bk; self.A = np.clip(((self.O - Bk) * dv).sum(2) / np.maximum((dv * dv).sum(2), 1.0), 0, 1)

    def render(self, P):
        R = np.zeros((self.H, self.W), np.float32)
        for c in self.covs(P): R = np.maximum(R, c)
        return R

    def err(self, P): return float(((self.render(P) - self.A) ** 2)[self.near].mean())

    def fit(self, log):
        P = self.P; best = self.err(P); e0 = P["e"]; t0 = time.time()
        for step in (1.0, 0.5, 0.25, 0.125):
            for _ in range(5):
                moved = False
                for k, st in (("e", step * 0.2), ("sz", step * 0.5), ("kx", step * 0.01), ("ky", step * 0.01)):
                    for d in (st, -st):
                        Q = dict(P); Q[k] = P[k] + d; s = self.err(Q)
                        if s < best - 1e-7: P, best, moved = Q, s, True
                for i in range(len(self.chars)):
                    for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
                        ps = list(P["pens"]); ps[i] = (ps[i][0] + dx, ps[i][1] + dy); Q = dict(P, pens=ps); s = self.err(Q)
                        if s < best - 1e-7: P, best, moved = Q, s, True
                if not moved: break
        # 2단계: 검수와 같은 기준(자리마다 배경색 → 글자색 진하기를 0.5에서 가름)으로 원본·재현 글자 모양이 화소까지 같아지게,
        # 「다른 화소 수」를 줄이도록 굵기·크기·가로·세로·글자 자리를 더 잘게 움직인다(운영자 2026-11-25 「고치고 해봐」 — 가장자리 1화소 차이 실측)
        M0 = (self.A >= 0.5) & self.near
        def berr(Q): return int(((self.render(Q) >= 0.5) != M0)[self.near].sum())
        bb = berr(P); b0 = bb
        for step in (0.25, 0.125, 0.0625):
            for _ in range(6):
                moved = False
                for k, st in (("e", step * 0.2), ("sz", step * 0.4), ("kx", step * 0.004), ("ky", step * 0.004)):
                    for d in (st, -st):
                        Q = dict(P); Q[k] = P[k] + d; s = berr(Q)
                        if s < bb: P, bb, moved = Q, s, True
                for i in range(len(self.chars)):
                    for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
                        ps = list(P["pens"]); ps[i] = (ps[i][0] + dx, ps[i][1] + dy); Q = dict(P, pens=ps); s = berr(Q)
                        if s < bb: P, bb, moved = Q, s, True
                if not moved: break
        log.append(f"「{self.ln['text']}」 모양 맞춤(0.5에서 가른 글자 모양): 다른 화소 {b0} → {bb}")
        self.P = P
        R = self.render(P) >= 0.5; M = (self.A >= 0.5) & self.near
        gl = []
        for i, ch in enumerate(self.chars):
            a = M & (self.own == i); b = R & (self.own == i); n = a.sum() + b.sum(); gl.append((ch, round(float(2 * (a & b).sum() / n), 4) if n else 0.0))
        self.glyphs = gl
        log.append(f"「{self.ln['text']}」 진하기 맞춤 {time.time() - t0:.0f}초: 덧굵기 {e0:+.2f}→{P['e']:+.3f}px · 크기 {P['sz']:.2f} · 가로 ×{P['kx']:.3f} · 세로 ×{P['ky']:.3f} · 진하기 오차 {best:.5f} · 글자 겹침 최소 {min(v for _, v in gl):.4f}")


def run(out, vid, log):
    V = json.load(open(os.path.join(out, "값", f"{vid}.json"), encoding="utf-8"))
    G = os.path.join(out, "그림")
    orig = np.asarray(Image.open(f"{G}/{vid}_원본.png").convert("RGB")).astype(np.float32)
    bg = np.asarray(Image.open(f"{G}/{vid}_배경.png").convert("RGB")).astype(np.float32)
    chrome = f"{G}/{vid}_재현_크롬.png"
    # 재현 도구가 새로 그렸으면(재현.png 가 정밀 기록보다 새것) 그것을 Chrome 판으로 둔다 — 옛 Chrome 판 위에 다시 그리지 않게
    pj = os.path.join(out, "값", f"{vid}_정밀.json")
    if not os.path.exists(chrome) or not os.path.exists(pj) or os.path.getmtime(f"{G}/{vid}_재현.png") > os.path.getmtime(pj):
        shutil.copy(f"{G}/{vid}_재현.png", chrome)
    old = np.asarray(Image.open(chrome).convert("RGB")).astype(np.float32)
    Hh, Ww = orig.shape[:2]; rep = old.copy(); drawn = np.zeros((Hh, Ww), bool)
    pool = {c[0]: c for c in FID.pool_fonts()}; info = []
    # 이름으로 못 찾으면 파일 이름으로 — 같은 파일이 여러 이름(「HFC:배민 도현체(산돌 1등)」·「도현」·「배달의민족 도현 Regular」)으로 들어 있고
    # HFC 이름은 이 목록에 없음(2026-11-25 「제이블랙」 편 첫 줄이 정밀 맞춤 없이 넘어감, 실측)
    pool_f = {}
    for c in FID.pool_fonts(): pool_f.setdefault(os.path.basename(c[1]), c)
    for ln in V["lines"]:
        f = ln.get("font") or {}; font = pool.get(f.get("best")) or pool_f.get(f.get("file") or "")
        if not font or not ln.get("glyphs"): log.append(f"「{ln['text']}」 글꼴 파일 없음 — Chrome 판 그대로"); continue
        ow = float(ln.get("outline_px") or 0); has_out = ow > 0 or bool(ln.get("shadow"))
        xs = [g["x"] for g in ln["glyphs"]]; ys = [g["y"] for g in ln["glyphs"]]; sz = float(ln["size_px"]); pad = int(ow + 16)
        X = max(0, int(min(xs) - pad)); Y = max(0, int(min(ys) - sz * 1.2 - pad)); X1 = min(Ww, int(max(xs) + sz * 1.5 + pad)); Y1 = min(Hh, int(max(ys) + sz * 0.4 + pad))
        L = Line(ln, font, orig[Y:Y1, X:X1], bg[Y:Y1, X:X1], X, Y)
        back = hexrgb(ln["outline_color"]) if (ow > 0 and ln.get("outline_color")) else None
        L.measure(back); L.fit(log); L.measure(back)
        U = L.render(L.P)
        O, Bg, h, w = L.O, L.B, L.H, L.W
        reg = rep[Y:Y1, X:X1].copy()
        oldt = (np.abs(old[Y:Y1, X:X1] - Bg).sum(2) > 30)
        dist_out = cv2.distanceTransform((U < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        oline = np.zeros((h, w), np.float32); prof_out = None; oc = None
        if has_out:
            ring = (dist_out > 1) & (dist_out <= 4)
            oc = np.median(O[ring], 0) if ring.sum() > 10 else (back if back is not None else np.zeros(3, np.float32))
            dv = oc - Bg; aO = np.clip(((O - Bg) * dv).sum(2) / np.maximum((dv * dv).sum(2), 1.0), 0, 1)
            gy, gx = np.gradient(cv2.GaussianBlur(dist_out, (0, 0), 1.0)); ang = (np.degrees(np.arctan2(gy, gx)) + 360) % 360
            bin_ = ((ang + 22.5) // 45).astype(int) % 8
            other = cv2.dilate(drawn[Y:Y1, X:X1].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0   # 앞 줄 자리는 잴 때 뺌
            dk = np.arange(0.0, 16.01, 0.5); prof = np.zeros((8, len(dk)), np.float32)
            for b_ in range(8):
                for j, k2 in enumerate(dk):
                    if k2 == 0: prof[b_, j] = 1.0; continue
                    band = (dist_out > k2 - 0.5) & (dist_out <= k2) & (bin_ == b_) & ~other
                    allb = (dist_out > k2 - 0.5) & (dist_out <= k2) & ~other
                    prof[b_, j] = float(np.median(aO[band])) if band.sum() > 150 else (float(np.median(aO[allb])) if allb.sum() > 20 else 0.0)
            for b_ in range(8):
                m = bin_ == b_; oline[m] = np.interp(dist_out[m], dk, prof[b_])
            oline = np.maximum(cv2.GaussianBlur(oline, (0, 0), 0.5), U); prof_out = prof
        clear = ((cv2.dilate(oldt.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & (dist_out < max(18, ow + 12))) | (oline > 0.02)
        clear &= ~drawn[Y:Y1, X:X1]
        reg[clear] = Bg[clear]
        if has_out: reg = reg * (1 - oline[..., None]) + oc * oline[..., None]
        for i, c in enumerate(L.covs(L.P)): reg = reg * (1 - c[..., None]) + hexrgb(L.cols[i]) * c[..., None]
        dm = drawn[Y:Y1, X:X1] & (U < 0.02) & (oline < 0.02); reg[dm] = rep[Y:Y1, X:X1][dm]
        rep[Y:Y1, X:X1] = reg; drawn[Y:Y1, X:X1] |= (oline > 0.3) | (U > 0.3)
        info.append(dict(text=ln["text"], font=font[0], at=[X, Y], P={k: v for k, v in L.P.items()}, glyphs=L.glyphs,
                         outline_color=("#%02X%02X%02X" % tuple(int(v) for v in oc)) if oc is not None else None,
                         outline_profile=prof_out.round(3).tolist() if prof_out is not None else None))
        if prof_out is not None:
            log.append(f"「{ln['text']}」 테두리 8방향(7·9·11px): " + " · ".join(f"{DIRS[b_]} {prof_out[b_, 14]:.2f}/{prof_out[b_, 18]:.2f}/{prof_out[b_, 22]:.2f}" for b_ in range(8)))
    Image.fromarray(np.clip(rep, 0, 255).astype(np.uint8)).save(f"{G}/{vid}_재현.png")
    json.dump(dict(lines=info, log=log), open(os.path.join(out, "값", f"{vid}_정밀.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)


def verify(out, vid):
    """독립 검수 숫자(겹침 최소·평균) — tt_verify 를 따로 돌려 결과 파일에서 읽음."""
    py = sys.executable; here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([py, "-I", "-X", "utf8", os.path.join(here, "tt_verify.py"), out, "--only", vid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    v = json.load(open(os.path.join(out, "값", f"{vid}_검수.json"), encoding="utf-8"))
    return v


if __name__ == "__main__":
    out, vid = sys.argv[1], sys.argv[2]; log = []; t0 = time.time()
    run(out, vid, log)
    for x in log: print(x, flush=True)
    print(f"끝 {time.time() - t0:.0f}초", flush=True)
