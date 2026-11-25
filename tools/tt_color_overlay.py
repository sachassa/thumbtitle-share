# tt_color_overlay — 원본 글자와 재현 글자를 서로 다른 색으로 칠해 한 장에 겹친다(운영자 2026-11-24 「컬러 다르게 하고 겹치면 되지 않아, 테두리·컬러」).
#   python -I -X utf8 tt_color_overlay.py <결과 폴더> [--only id,id]  → 그림/<id>_색겹침.png
# 글자 떼기는 독립 검수 도구(tt_verify)와 같은 방법·같은 기준(원본에서 정한 색 기준을 두 그림에 똑같이)으로 한다.
#   채움:  원본에만 = 자홍 · 재현에만 = 초록 · 둘 다 = 흰색
#   테두리: 원본에만 = 주황 · 재현에만 = 파랑 · 둘 다 = 회색
# 바탕은 원본을 어둡게(30%) 깔아 자리만 보이게 한다. 화면 확인용 그림이며 판정에는 쓰지 않는다(판정 = 검수 표).
import glob, os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_verify as V

C = dict(fo=(255, 0, 255), fr=(0, 255, 0), fb=(255, 255, 255), oo=(0, 140, 255), orr=(255, 80, 0), ob=(150, 150, 150))   # BGR

def make(folder, vid):
    res = V.load_json(os.path.join(folder, "값", vid + ".json"))
    o = V.load_img(os.path.join(folder, "그림", vid + "_원본.png")); r = V.load_img(os.path.join(folder, "그림", vid + "_재현.png"))
    regs, texts = V.line_regions_from_result(res, o.shape[0])
    out = (o.astype(np.float32) * 0.3).astype(np.uint8)
    for reg, t in zip(regs, texts):
        p = V.derive_params(o, reg, t)
        if len(p["text"]) == 0: continue
        y0, y1 = reg["band"]
        co, tio = V.coverage(o, reg, p); cr, tir = V.coverage(r, reg, p)
        mo, mr = V.ink_mask(co >= 0.5, reg), V.ink_mask(cr >= 0.5, reg)   # 검수와 같은 잡티·사진 조각 빼기
        oi = p.get("outline_idx")
        if oi is None: oi = V._find_outline(o, reg, p)
        olo = mo & (tio == oi) if oi is not None else np.zeros_like(mo)
        olr = mr & (tir == oi) if oi is not None else np.zeros_like(mr)
        fo, fr = mo & ~olo, mr & ~olr
        b = out[y0:y1]
        for m, c in ((olo & ~olr, "oo"), (olr & ~olo, "orr"), (olo & olr, "ob"), (fo & ~fr, "fo"), (fr & ~fo, "fr"), (fo & fr, "fb")):
            b[m] = C[c]
    cv2.imencode(".png", out)[1].tofile(os.path.join(folder, "그림", vid + "_색겹침.png"))

if __name__ == "__main__":
    folder = sys.argv[1]; only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    for p in sorted(glob.glob(os.path.join(folder, "값", "*.json"))):
        b = os.path.basename(p)[:-5]
        if b in ("눈확인", "글자고르기") or b.endswith("_실측") or b.endswith("_검수"): continue
        if only and b not in only: continue
        if not os.path.exists(os.path.join(folder, "그림", b + "_재현.png")): continue
        try: make(folder, b); print(b, "색겹침 만듦")
        except Exception as ex: print(b, "색겹침 실패:", ex)
