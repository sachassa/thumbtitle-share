# tt_glyphrank — 글꼴 후보 고르기를 「글자 대 글자」 모양으로 한다(운영자 2026-11-25 「근데 왜 대충 겹쳐?」 · 「매번 이미지 안 만들어도 되는 거 아니야」).
#   ① 원본 줄을 글자마다 나눈다(빠른 58개 글꼴 맞춤의 글자 자리로 원본 화소를 가장 가까운 글자에 붙임)
#   ② 글자마다 잉크 상자로 잘라 64×64로 맞춘다(크기·가로 비율·자간·자리가 빠짐 → 글꼴 모양만 남음)
#   ③ 글꼴마다 같은 글자를 같은 방법으로 만든 모양과 견줌(봐주기 없는 F1). 글꼴 글자 모양은 한 번 그리면
#      tt_config.GLYPH_CACHE(기본 <data_dir>/fonts/_글자모양/) 에 저장해 두고 다음 줄·다음 영상에서 다시 그리지 않는다.
#   점수 = 글자마다 F1의 평균. 이것은 줄 세우기일 뿐 — 「찾음」은 그대로 자세히 맞춘 뒤 글자마다 1.00이어야 한다.
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_typo2 as T2
from tt_typo import cv2

N = 64; SIZE = 160
CACHE = T2.T.CFG.GLYPH_CACHE
_MEM = {}

def norm(m):
    ys, xs = np.nonzero(m)
    if len(xs) < 3: return None
    c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8) * 255
    return cv2.resize(c, (N, N), interpolation=cv2.INTER_AREA) > 127

def _key(c): return f"{c[1]}|{c[2]}"

# 저장: 글자마다 파일 하나(<글자 코드>.npz = 글꼴 열쇠 목록 + 64×64 모양 비트). 한 줄에 필요한 글자 파일 몇 개만 읽으면 된다.
# (전에는 글꼴마다 파일 하나라 한 줄에 1,600여 개 파일을 열어 10초 넘게 걸림 — 실측 2026-11-25)
_DIRTY = set()
def _char_table(ch):
    if ch not in _MEM:
        d = {}; p = os.path.join(CACHE, f"{ord(ch):x}.npz")
        if os.path.exists(p):
            try:
                z = np.load(p, allow_pickle=False); ks = z["keys"]; bits = z["bits"]; ok = z["ok"]
                for k, b, o in zip(ks, bits, ok): d[str(k)] = np.unpackbits(b)[:N * N].reshape(N, N).astype(bool) if o else None
            except Exception: d = {}
        _MEM[ch] = d
    return _MEM[ch]

def _save():
    os.makedirs(CACHE, exist_ok=True)
    for ch in list(_DIRTY):
        d = _MEM[ch]; ks = list(d.keys())
        bits = np.stack([np.packbits(d[k].ravel()) if d[k] is not None else np.zeros(N * N // 8, np.uint8) for k in ks]) if ks else np.zeros((0, N * N // 8), np.uint8)
        np.savez(os.path.join(CACHE, f"{ord(ch):x}.npz"), keys=np.array(ks), bits=bits, ok=np.array([d[k] is not None for k in ks]))
    _DIRTY.clear()

def font_shapes(c, chars):
    """글꼴 c 의 글자 모양 {글자: 64×64 bool 또는 None}과 새로 그린 글자 수. 없는 글자만 새로 그려 둔다."""
    k = _key(c); out = {}; new = 0
    for ch in dict.fromkeys(chars):
        if not ch.strip(): continue
        t = _char_table(ch)
        if k not in t:
            try:
                g = T2.glyph(c, SIZE, ch)[0]; t[k] = None if g is None else norm(g > 127)
            except Exception: t[k] = None
            _DIRTY.add(ch); new += 1
        out[ch] = t[k]
    return out, new

def orig_shapes(chars, F, ref):
    """원본 줄을 글자마다 나눠 64×64 모양으로. ref = (글꼴, 맞춘 값) — 글자 자리만 빌림."""
    c, p = ref
    _, idm = T2.raster(T2.layout(c, chars, p), F.shape, p["e"], ids=True)
    gmap = T2.glyph_assign(F, idm)
    # 글자(한글·영문·숫자)만 견준다 — 따옴표·말줄임표·물음표 같은 부호는 작고 모양이 비슷해 글꼴을 가르지 못하고,
    # 원본에서 나눌 때 자주 어긋나 0점이 나와 평균을 끌어내림(2026-11-25 「배구 일본반응」 「…”」, 실측)
    return {i: norm(gmap == i) for i, ch in enumerate(chars) if ch.isalnum()}

def rank(chars, F, cands, ref, log=None):
    """[(점수, (이름, 경로, 굵기))] 높은 순."""
    t0 = time.time(); O = orig_shapes(chars, F, ref); n_new = 0
    out = []
    for j, c in enumerate(cands):
        cc = tuple(c[:3])
        S, nw = font_shapes(cc, chars); n_new += 1 if nw else 0
        v = []
        for i, o in O.items():
            s = S.get(chars[i])
            v.append(0.0 if (o is None or s is None) else T2.f1_exact(o, s))
        out.append((float(np.mean(v)) if v else 0.0, cc))
        if j % 50 == 49: T2._FC.clear(); T2._GC.clear()
    T2._FC.clear(); T2._GC.clear(); _save()
    out.sort(key=lambda x: -x[0])
    if log is not None: log.append(f"글자 모양 견주기: {len(cands)}개 {time.time() - t0:.1f}초(새로 그린 글꼴 {n_new}개, 나머지는 저장한 모양)")
    return out

if __name__ == "__main__":   # 시험: python tt_glyphrank.py <채움.npy> "<글자>"
    import tt_fontid as FID
    F = np.load(sys.argv[1]); chars = list(sys.argv[2]); lg = []
    w = T2.fit_line(chars, F, lg)[0]
    cands = [c for c in FID.pool_fonts() if FID.covers(c[3], chars)]
    for _ in range(2):
        r = rank(chars, F, cands, (w["c"], w["p"]), lg); print(lg[-1])
    for s, c in r[:15]: print(round(s, 3), c[0])
